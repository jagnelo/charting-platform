from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.strategy_lab_v2.api_contracts import ApiCursor
from app.strategy_lab_v2.api_resources import (
    ApiResourceType,
    ResourceCollection,
    ResourceDocument,
    ResourceIdentifier,
)
from app.strategy_lab_v2.api_router import (
    ResourceMutationServiceResult,
    SubmissionServiceResult,
    _json_value,
    _request_id,
    _safe_header_value,
    create_strategy_lab_router,
    serialize_resource,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.commands import (
    CommandEffect,
    ExecutionCommandDecision,
    ExecutionCommandKind,
    ExecutionCommandLedger,
    ExecutionCommandReceipt,
    ExecutionCommandResolution,
)
from app.strategy_lab_v2.resource_mutations import (
    ResourceMutationDecision,
    ResourceMutationResolution,
    create_resource_mutation_receipt,
)
from app.strategy_lab_v2.submissions import (
    SubmissionDecision,
    SubmissionResolution,
    create_submission_receipt,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
SNAPSHOT = content_digest({"snapshot": "one"})


def _document(resource_id: str = "trial-1") -> ResourceDocument:
    return ResourceDocument(
        ResourceIdentifier(
            ApiResourceType.TRIAL,
            resource_id,
            revision_digest=content_digest({"trial": resource_id}),
        ),
        attributes={"name": "mean-reversion", "ratio": Decimal("1.25")},
        relationships={
            "experiment": (ResourceIdentifier(ApiResourceType.EXPERIMENT, "experiment-1"),)
        },
        meta={"source": "test"},
    )


class FakeAdapter:
    def __init__(self) -> None:
        self.submissions: list[tuple[str, str, dict[str, Any]]] = []
        self.commands: list[tuple[str, str]] = []
        self.mutations: list[tuple[str, str, str]] = []
        self.document = _document()

    async def list_resources(self, **kwargs: Any) -> ResourceCollection:
        return ResourceCollection(
            request_id=kwargs["request_id"],
            resource_type=kwargs["resource_type"],
            snapshot_digest=SNAPSHOT,
            items=(self.document,),
            has_more=False,
        )

    async def get_resource(self, **kwargs: Any) -> ResourceDocument | None:
        if kwargs["resource_id"] == self.document.id:
            return self.document
        return None

    async def submit(self, **kwargs: Any) -> SubmissionServiceResult:
        request = kwargs["request"]
        payload = dict(kwargs["payload"])
        self.submissions.append((request.idempotency_key, request.operation, payload))
        receipt = create_submission_receipt(request, accepted_at=NOW)
        return SubmissionServiceResult(
            SubmissionResolution(SubmissionDecision.ACCEPT, request.fingerprint), receipt
        )

    async def create_resource(self, **kwargs: Any) -> ResourceMutationServiceResult:
        request = kwargs["request"]
        self.mutations.append(
            (request.resource_type.value, request.idempotency_key, request.payload_digest)
        )
        receipt = create_resource_mutation_receipt(
            request, self.document, accepted_at=NOW
        )
        return ResourceMutationServiceResult(
            ResourceMutationResolution(ResourceMutationDecision.ACCEPT, request.fingerprint),
            receipt,
        )

    async def command(self, **kwargs: Any) -> ExecutionCommandResolution:
        command = kwargs["command"]
        self.commands.append((kwargs["idempotency_key"], command.kind.value))
        receipt = ExecutionCommandReceipt(
            command_id=command.command_id,
            command_fingerprint=command.fingerprint,
            attempt_id=command.attempt_id,
            kind=command.kind,
            effect=(
                CommandEffect.CANCELLATION_REQUESTED
                if command.kind is ExecutionCommandKind.CANCEL
                else CommandEffect.RETRY_REQUESTED
            ),
            accepted_at=NOW,
        )
        return ExecutionCommandResolution(
            ExecutionCommandDecision.ACCEPT,
            ledger=ExecutionCommandLedger((receipt,)),
            command_fingerprint=command.fingerprint,
            receipt=receipt,
        )


class ConflictAdapter(FakeAdapter):
    async def submit(self, **kwargs: Any) -> SubmissionServiceResult:
        request = kwargs["request"]
        previous_request = type(request)(
            idempotency_key=request.idempotency_key,
            operation=request.operation,
            attempt_id=request.attempt_id,
            payload_digest=content_digest({"previous": True}),
            submitted_at=NOW,
        )
        previous_receipt = create_submission_receipt(previous_request, accepted_at=NOW)
        return SubmissionServiceResult(
            SubmissionResolution(
                SubmissionDecision.IDEMPOTENCY_CONFLICT,
                request.fingerprint,
                previous_receipt,
            ),
            previous_receipt,
        )


class ResourceConflictAdapter(FakeAdapter):
    async def create_resource(self, **kwargs: Any) -> ResourceMutationServiceResult:
        request = kwargs["request"]
        previous_request = type(request)(
            resource_type=request.resource_type,
            idempotency_key=request.idempotency_key,
            payload={"attributes": {"previous": True}},
            requested_at=NOW,
        )
        previous_receipt = create_resource_mutation_receipt(
            previous_request, self.document, accepted_at=NOW
        )
        resolution = ResourceMutationResolution(
            ResourceMutationDecision.IDEMPOTENCY_CONFLICT,
            request.fingerprint,
            previous_receipt,
        )
        return ResourceMutationServiceResult(resolution, previous_receipt)


class RequestDriftAdapter(FakeAdapter):
    async def list_resources(self, **kwargs: Any) -> ResourceCollection:
        collection = await super().list_resources(**kwargs)
        return ResourceCollection(
            request_id="different-request",
            resource_type=collection.resource_type,
            snapshot_digest=collection.snapshot_digest,
            items=collection.items,
            has_more=collection.has_more,
            next_cursor=collection.next_cursor,
        )


class SnapshotDriftAdapter(FakeAdapter):
    async def list_resources(self, **kwargs: Any) -> ResourceCollection:
        collection = await super().list_resources(**kwargs)
        return ResourceCollection(
            request_id=collection.request_id,
            resource_type=collection.resource_type,
            snapshot_digest=content_digest({"snapshot": "different"}),
            items=collection.items,
            has_more=collection.has_more,
            next_cursor=collection.next_cursor,
        )


def _client(adapter: FakeAdapter) -> TestClient:
    async def get_adapter() -> FakeAdapter:
        return adapter

    async def get_principal() -> str:
        return "user-1"

    app = FastAPI()
    app.include_router(
        create_strategy_lab_router(
            adapter_dependency=get_adapter,
            principal_dependency=get_principal,
            request_id_factory=lambda: "request-generated",
            clock=lambda: NOW,
        ),
        prefix="/api/v1",
    )
    return TestClient(app)


def test_resource_serialization_preserves_decimal_as_exact_string() -> None:
    serialized = serialize_resource(_document())
    assert serialized["attributes"]["ratio"] == "1.25"
    assert serialized["relationships"]["experiment"]["data"] == [
        {"type": "experiments", "id": "experiment-1"}
    ]
    assert serialized["meta"]["schema_version"] == 1


def test_api_json_serialization_handles_dates_and_rejects_unsafe_scalars() -> None:
    assert _json_value(date(2024, 1, 2)) == "2024-01-02"
    assert _json_value(1.25) == 1.25
    with pytest.raises(ValueError, match="finite"):
        _json_value(float("nan"))
    with pytest.raises(TypeError, match="unsupported API JSON value"):
        _json_value(object())


def test_api_request_metadata_rejects_control_characters() -> None:
    request = SimpleNamespace(headers={"X-Request-ID": "request\nforged"})
    with pytest.raises(ValueError, match="control-free"):
        _request_id(cast(Any, request), lambda: "unused")
    with pytest.raises(ValueError, match="control characters"):
        _safe_header_value("key\r\nforged", "Idempotency-Key", 256)


def test_router_lists_and_reads_cursor_bound_resources() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        response = client.get("/api/v1/strategy-lab/v2/trials?limit=1")
        assert response.status_code == 200
        assert response.json()["data"][0]["id"] == "trial-1"
        assert response.json()["data"][0]["attributes"]["ratio"] == "1.25"

        found = client.get("/api/v1/strategy-lab/v2/trials/trial-1")
        assert found.status_code == 200
        assert found.headers["content-type"].startswith("application/json")

        missing = client.get("/api/v1/strategy-lab/v2/trials/missing")
        assert missing.status_code == 404
        assert missing.json()["errors"][0]["code"] == "not_found"


def test_router_rejects_invalid_cursor_and_unknown_resource_with_typed_errors() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        invalid = client.get("/api/v1/strategy-lab/v2/trials?cursor=not-a-cursor")
        assert invalid.status_code == 400
        assert invalid.json()["errors"][0]["code"] == "validation_error"

        unknown = client.get("/api/v1/strategy-lab/v2/not-a-resource")
        assert unknown.status_code == 404
        assert unknown.json()["errors"][0]["details"]["resource"] == "not-a-resource"

        too_large = client.get("/api/v1/strategy-lab/v2/trials?limit=101")
        assert too_large.status_code == 400


def test_router_rejects_ambiguous_or_non_finite_raw_json_bodies() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        duplicate = client.post(
            "/api/v1/strategy-lab/v2/submissions",
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": "submission-key",
            },
            content=(
                '{"operation":"backtest","operation":"retry",'
                '"attempt_id":"attempt-1","payload":{}}'
            ),
        )
        assert duplicate.status_code == 422
        assert duplicate.json()["errors"][0]["code"] == "validation_error"
        assert adapter.submissions == []

        non_finite = client.post(
            "/api/v1/strategy-lab/v2/submissions",
            headers={
                "Content-Type": "application/json",
                "Idempotency-Key": "submission-key",
            },
            content=(
                '{"operation":"backtest","attempt_id":"attempt-1",'
                '"payload":{"score":NaN}}'
            ),
        )
        assert non_finite.status_code == 422
        assert non_finite.json()["errors"][0]["code"] == "validation_error"
        assert adapter.submissions == []


def test_router_rejects_collection_request_identity_drift() -> None:
    with _client(RequestDriftAdapter()) as client:
        response = client.get("/api/v1/strategy-lab/v2/trials")
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "validation_error"


def test_router_rejects_collection_snapshot_drift_after_cursor_validation() -> None:
    cursor = ApiCursor(
        resource="trials",
        snapshot_digest=SNAPSHOT,
        sort_value="2024-01-01T00:00:00Z",
        item_id="trial-1",
    )
    with _client(SnapshotDriftAdapter()) as client:
        response = client.get(
            "/api/v1/strategy-lab/v2/trials", params={"cursor": cursor.token}
        )
        assert response.status_code == 422
        assert response.json()["errors"][0]["code"] == "validation_error"


def test_strategy_validation_route_is_static_and_authenticated_by_injected_dependency() -> None:
    with _client(FakeAdapter()) as client:
        accepted = client.post(
            "/api/v1/strategy-lab/v2/strategies/validate",
            json={"source": "def signal(inputs):\n    return inputs.close > 0\n"},
        )
        assert accepted.status_code == 200
        assert accepted.json()["data"]["attributes"]["accepted"] is True

        rejected = client.post(
            "/api/v1/strategy-lab/v2/strategies/validate",
            json={"source": "import os\nnow = datetime.now()\n"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["data"]["attributes"]["accepted"] is False
        violations = rejected.json()["data"]["attributes"]["violations"]
        assert any("forbidden_import" in item for item in violations)
        assert any("forbidden_wall_clock" in item for item in violations)

        malformed = client.post(
            "/api/v1/strategy-lab/v2/strategies/validate",
            json=["source"],
        )
        assert malformed.status_code == 422
        assert malformed.json()["errors"][0]["code"] == "validation_error"


def test_strategy_validation_rejects_invalid_request_id_with_typed_error() -> None:
    with _client(FakeAdapter()) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/strategies/validate",
            headers={"X-Request-ID": "r" * 129},
            json={"source": "def signal(inputs):\n    return []\n"},
        )
        assert response.status_code == 400
        error = response.json()["errors"][0]
        assert error["code"] == "validation_error"
        assert error["request_id"] == "unknown"


def test_submission_requires_idempotency_and_returns_accepted_receipt() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        missing = client.post(
            "/api/v1/strategy-lab/v2/submissions",
            json={"operation": "backtest", "attempt_id": "attempt-1", "payload": {}},
        )
        assert missing.status_code == 400
        assert missing.json()["errors"][0]["code"] == "validation_error"

        response = client.post(
            "/api/v1/strategy-lab/v2/submissions",
            headers={"Idempotency-Key": "submission-key", "X-Request-ID": "request-1"},
            json={"operation": "backtest", "attempt_id": "attempt-1", "payload": {"x": 1}},
        )
        assert response.status_code == 202
        assert response.headers["x-request-id"] == "request-1"
        assert response.json()["data"]["type"] == "submissions"
        assert response.json()["data"]["attributes"]["payload_digest"] == content_digest({"x": 1})
        assert adapter.submissions == [("submission-key", "backtest", {"x": 1})]


def test_submission_conflict_is_exposed_as_typed_idempotency_error() -> None:
    with _client(ConflictAdapter()) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/submissions",
            headers={"Idempotency-Key": "submission-key"},
            json={"operation": "backtest", "attempt_id": "attempt-1", "payload": {"x": 1}},
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "idempotency_conflict"


def test_resource_creation_is_idempotent_and_returns_a_resource_document() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/trials",
            headers={"Idempotency-Key": "resource-key", "X-Request-ID": "resource-request"},
            json={
                "attributes": {"name": "mean-reversion", "lookback": 20},
                "relationships": {
                    "experiment": [{"type": "experiments", "id": "experiment-1"}]
                },
            },
        )
        assert response.status_code == 202
        assert response.headers["x-request-id"] == "resource-request"
        assert response.json()["data"]["type"] == "trials"
        assert response.json()["meta"]["decision"] == "accept"
        assert adapter.mutations[0][0:2] == ("trials", "resource-key")


def test_resource_creation_rejects_read_only_or_ambiguous_requests() -> None:
    adapter = FakeAdapter()
    with _client(adapter) as client:
        readonly = client.post(
            "/api/v1/strategy-lab/v2/artifacts",
            headers={"Idempotency-Key": "resource-key"},
            json={"attributes": {}},
        )
        assert readonly.status_code == 405
        assert readonly.json()["errors"][0]["code"] == "precondition_failed"

        duplicate = client.post(
            "/api/v1/strategy-lab/v2/trials",
            headers={"Idempotency-Key": "resource-key"},
            content='{"attributes":{},"attributes":{}}',
        )
        assert duplicate.status_code == 422
        assert duplicate.json()["errors"][0]["code"] == "validation_error"

        missing_key = client.post(
            "/api/v1/strategy-lab/v2/trials", json={"attributes": {}}
        )
        assert missing_key.status_code == 400
        assert missing_key.json()["errors"][0]["code"] == "validation_error"


def test_resource_creation_exposes_typed_idempotency_conflict() -> None:
    with _client(ResourceConflictAdapter()) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/trials",
            headers={"Idempotency-Key": "resource-key"},
            json={"attributes": {"name": "new"}},
        )
        assert response.status_code == 409
        assert response.json()["errors"][0]["code"] == "idempotency_conflict"


def test_command_route_constructs_typed_intent_and_returns_accepted_receipt() -> None:
    adapter = FakeAdapter()
    command_id = content_digest({"command": "cancel"})
    with _client(adapter) as client:
        response = client.post(
            "/api/v1/strategy-lab/v2/attempts/attempt-1/commands",
            headers={"Idempotency-Key": "command-key"},
            json={
                "command_id": command_id,
                "kind": "cancel",
                "reason": "user requested stop",
                "requested_at": NOW.isoformat(),
            },
        )
        assert response.status_code == 202
        assert response.json()["data"]["attributes"]["effect"] == "cancellation_requested"
        assert adapter.commands == [("command-key", "cancel")]
