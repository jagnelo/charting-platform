from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType, ResourceDocument, ResourceIdentifier
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.resource_mutations import (
    ResourceMutationDecision,
    ResourceMutationRequest,
    create_resource_mutation_receipt,
    resolve_resource_mutation,
)

NOW = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)


def _request(*, resource_type: ApiResourceType = ApiResourceType.TRIAL, payload: dict | None = None) -> ResourceMutationRequest:
    return ResourceMutationRequest(
        resource_type=resource_type,
        idempotency_key="mutation-key",
        payload=payload or {"attributes": {"name": "trial"}},
        requested_at=NOW,
    )


def _document(resource_type: ApiResourceType = ApiResourceType.TRIAL, resource_id: str = "trial-1") -> ResourceDocument:
    return ResourceDocument(ResourceIdentifier(resource_type, resource_id))


def test_resource_mutation_accepts_and_replays_exact_receipts() -> None:
    request = _request()
    receipt = create_resource_mutation_receipt(request, _document(), accepted_at=NOW)
    accepted = resolve_resource_mutation(request)
    assert accepted.decision is ResourceMutationDecision.ACCEPT
    replay = resolve_resource_mutation(request, (receipt,))
    assert replay.decision is ResourceMutationDecision.REPLAY_EXISTING
    assert replay.existing_receipt == receipt


def test_resource_mutation_conflicts_on_changed_content_or_history() -> None:
    request = _request()
    receipt = create_resource_mutation_receipt(request, _document(), accepted_at=NOW)
    changed = _request(payload={"attributes": {"name": "changed"}})
    conflict = resolve_resource_mutation(changed, (receipt,))
    assert conflict.decision is ResourceMutationDecision.IDEMPOTENCY_CONFLICT
    assert conflict.existing_receipt == receipt

    other = create_resource_mutation_receipt(
        _request(payload={"attributes": {"name": "other"}}), _document(), accepted_at=NOW
    )
    with pytest.raises(ValueError, match="conflicting idempotency"):
        resolve_resource_mutation(request, (receipt, other))


def test_resource_mutation_binds_resource_type_and_normalizes_time() -> None:
    request = ResourceMutationRequest(
        ApiResourceType.TRIAL,
        "mutation-key",
        {"attributes": {"value": 1}},
        datetime(2024, 1, 2, 13, 0, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="resource type"):
        create_resource_mutation_receipt(
            request,
            _document(ApiResourceType.EXPERIMENT),
            accepted_at=datetime(2024, 1, 2, 13, 0, tzinfo=UTC),
        )
    assert request.payload_digest == content_digest({"attributes": {"value": 1}})
    assert request.requested_at.tzinfo is not None


def test_resource_mutation_rejects_invalid_inputs() -> None:
    with pytest.raises(TypeError, match="resource_type"):
        ResourceMutationRequest("trials", "key", {}, NOW)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="idempotency_key"):
        ResourceMutationRequest(ApiResourceType.TRIAL, "", {}, NOW)
    with pytest.raises(ValueError, match="timezone"):
        ResourceMutationRequest(ApiResourceType.TRIAL, "key", {}, datetime(2024, 1, 2))
