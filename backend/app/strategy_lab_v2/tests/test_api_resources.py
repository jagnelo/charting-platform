from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.api_contracts import ApiCursor
from app.strategy_lab_v2.api_resources import (
    ApiResourceType,
    ResourceCollection,
    ResourceDocument,
    ResourceIdentifier,
)
from app.strategy_lab_v2.canonical import content_digest

SNAPSHOT = content_digest("snapshot-1")


def _trial(trial_id: str = "trial-1") -> ResourceDocument:
    return ResourceDocument(
        ResourceIdentifier(ApiResourceType.TRIAL, trial_id, revision_digest=content_digest(trial_id)),
        attributes={"name": "mean-reversion", "enabled": True},
        relationships={
            "experiment": (ResourceIdentifier(ApiResourceType.EXPERIMENT, "experiment-1"),)
        },
        meta={"source": "strategy-lab-v2"},
    )


def _cursor(item_id: str = "trial-1") -> ApiCursor:
    return ApiCursor(
        ApiResourceType.TRIAL.value,
        SNAPSHOT,
        datetime(2024, 1, 1, tzinfo=UTC).isoformat(),
        item_id,
    )


def test_resource_document_freezes_fields_and_exposes_stable_identity() -> None:
    document = _trial()
    assert document.type == "trials"
    assert document.id == "trial-1"
    assert document.attributes["enabled"] is True
    assert document.relationships["experiment"][0].resource_id == "experiment-1"  # type: ignore[index]
    assert document.fingerprint.startswith("sha256:")
    with pytest.raises(TypeError):
        document.attributes["enabled"] = False  # type: ignore[index]


def test_collection_binds_resource_type_and_snapshot_to_cursor() -> None:
    collection = ResourceCollection(
        "request-1",
        ApiResourceType.TRIAL,
        SNAPSHOT,
        (_trial(),),
        True,
        _cursor(),
    )
    assert collection.http_status == 200
    assert collection.resource == "trials"
    assert collection.next_cursor is not None
    assert collection.next_cursor.snapshot_digest == SNAPSHOT
    assert collection.fingerprint.startswith("sha256:")


def test_collection_rejects_foreign_items_and_cursor_snapshots() -> None:
    with pytest.raises(ValueError, match="collection resource type"):
        ResourceCollection("request-1", ApiResourceType.TRIAL, SNAPSHOT, (
            ResourceDocument(ResourceIdentifier(ApiResourceType.ATTEMPT, "attempt-1")),
        ))
    with pytest.raises(ValueError, match="collection snapshot"):
        ResourceCollection(
            "request-1", ApiResourceType.TRIAL, SNAPSHOT, (_trial(),), True,
            ApiCursor("trials", content_digest("other"), "sort", "trial-1"),
        )


def test_collection_requires_cursor_only_when_more_items_exist() -> None:
    with pytest.raises(ValueError, match="requires next_cursor"):
        ResourceCollection("request-1", ApiResourceType.TRIAL, SNAPSHOT, (_trial(),), True)
    with pytest.raises(ValueError, match="final collection"):
        ResourceCollection(
            "request-1", ApiResourceType.TRIAL, SNAPSHOT, (_trial(),), False, _cursor()
        )


def test_resource_contract_rejects_unfrozen_or_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="resource_id"):
        ResourceIdentifier(ApiResourceType.TRIAL, " ")
    with pytest.raises(ValueError, match="snapshot_digest"):
        ResourceCollection("request-1", ApiResourceType.TRIAL, "bad")
    with pytest.raises(TypeError, match="relationship values"):
        ResourceDocument(
            ResourceIdentifier(ApiResourceType.TRIAL, "trial-1"),
            relationships={"experiment": "experiment-1"},  # type: ignore[dict-item]
        )
