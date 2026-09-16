from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.strategy_lab_v2.api_contracts import ApiCursor
from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.postgres_resources import PostgresResourceReader
from app.strategy_lab_v2.storage import AggregateKey, StoredAggregate


@dataclass
class MemoryStore:
    aggregates: list[StoredAggregate]

    async def get(self, key: AggregateKey) -> StoredAggregate | None:
        for aggregate in self.aggregates:
            if aggregate.key == key:
                return aggregate
        return None

    async def list_type(self, aggregate_type: str) -> tuple[StoredAggregate, ...]:
        return tuple(
            aggregate for aggregate in self.aggregates if aggregate.key.aggregate_type == aggregate_type
        )


def _trial(
    trial_id: str,
    *,
    owner_id: str = "alice",
    sort_value: str | None = None,
    relationships: Any = None,
) -> StoredAggregate:
    state: dict[str, Any] = {
        "owner_id": owner_id,
        "sort_value": sort_value or trial_id,
        "attributes": {"status": "queued", "score": 3},
        "meta": {"source": "postgres"},
    }
    if relationships is not None:
        state["relationships"] = relationships
    return StoredAggregate(
        AggregateKey(ApiResourceType.TRIAL.value, trial_id),
        1,
        state,
    )


@pytest.mark.asyncio
async def test_reader_scopes_owner_and_binds_cursor_to_visible_snapshot() -> None:
    store = MemoryStore(
        [
            _trial("trial-2", sort_value="002"),
            _trial("trial-foreign", owner_id="bob", sort_value="000"),
            _trial("trial-1", sort_value="001"),
        ]
    )
    reader = PostgresResourceReader(store)
    first = await reader.list_resources(
        principal=SimpleNamespace(id="alice"),
        resource_type=ApiResourceType.TRIAL,
        limit=1,
        cursor=None,
        request_id="request-1",
    )
    assert [item.id for item in first.items] == ["trial-1"]
    assert first.has_more is True
    assert first.next_cursor is not None
    second_document = await reader.get_resource(
        principal="alice", resource_type=ApiResourceType.TRIAL, resource_id="trial-2"
    )
    assert second_document is not None
    assert first.snapshot_digest == content_digest(
        (
            ("001", "trial-1", first.items[0].fingerprint),
            ("002", "trial-2", second_document.fingerprint),
        )
    )

    second = await reader.list_resources(
        principal="alice",
        resource_type=ApiResourceType.TRIAL,
        limit=1,
        cursor=first.next_cursor,
        request_id="request-2",
    )
    assert [item.id for item in second.items] == ["trial-2"]
    assert second.has_more is False
    assert second.next_cursor is None


@pytest.mark.asyncio
async def test_reader_does_not_leak_foreign_get_and_projects_relationships() -> None:
    aggregate = _trial(
        "trial-1",
        relationships={"experiment": [{"type": "experiments", "id": "experiment-1"}]},
    )
    reader = PostgresResourceReader(MemoryStore([aggregate, _trial("trial-2", owner_id="bob")]))
    document = await reader.get_resource(
        principal="alice", resource_type=ApiResourceType.TRIAL, resource_id="trial-1"
    )
    assert document is not None
    assert document.relationships["experiment"][0].resource_type is ApiResourceType.EXPERIMENT
    assert await reader.get_resource(
        principal="alice", resource_type=ApiResourceType.TRIAL, resource_id="trial-2"
    ) is None


@pytest.mark.asyncio
async def test_reader_rejects_cursor_for_different_or_changed_snapshot() -> None:
    store = MemoryStore([_trial("trial-1"), _trial("trial-2")])
    reader = PostgresResourceReader(store)
    page = await reader.list_resources(
        principal="alice",
        resource_type=ApiResourceType.TRIAL,
        limit=1,
        cursor=None,
        request_id="request-1",
    )
    cursor = ApiCursor(
        resource=ApiResourceType.ATTEMPT.value,
        snapshot_digest=page.snapshot_digest,
        sort_value="trial-1",
        item_id="trial-1",
    )
    with pytest.raises(ValueError, match="cursor resource"):
        await reader.list_resources(
            principal="alice", resource_type=ApiResourceType.TRIAL, limit=1,
            cursor=cursor, request_id="request-2"
        )

    store.aggregates.append(_trial("trial-3"))
    with pytest.raises(ValueError, match="cursor snapshot"):
        await reader.list_resources(
            principal="alice", resource_type=ApiResourceType.TRIAL, limit=1,
            cursor=page.next_cursor, request_id="request-3"
        )


@pytest.mark.asyncio
async def test_reader_fails_closed_on_malformed_owner_or_relationships() -> None:
    missing_owner = StoredAggregate(
        AggregateKey(ApiResourceType.TRIAL.value, "trial-1"), 1, {"sort_value": "trial-1"}
    )
    malformed_relationship = _trial("trial-2", relationships={"experiment": [{"id": "missing-type"}]})
    reader = PostgresResourceReader(MemoryStore([missing_owner, malformed_relationship]))
    with pytest.raises(ValueError, match="owner_id"):
        await reader.get_resource(
            principal="alice", resource_type=ApiResourceType.TRIAL, resource_id="trial-1"
        )
    with pytest.raises(ValueError, match="target must contain type and id"):
        await reader.get_resource(
            principal="alice", resource_type=ApiResourceType.TRIAL, resource_id="trial-2"
        )


def test_reader_requires_structural_store_methods() -> None:
    with pytest.raises(TypeError, match="async get and list_type"):
        PostgresResourceReader(cast(Any, object()))
