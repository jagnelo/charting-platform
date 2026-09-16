"""Owner-scoped resource reads over the Strategy Lab v2 aggregate store.

This is a read-only persistence adapter for the registration-neutral API
boundary.  It projects the versioned canonical aggregate JSON used by
``PostgresAggregateStore`` into :mod:`api_resources` values, computes a stable
visible snapshot for cursor pagination, and never mutates a row or invokes a
worker.  Additive relational migrations can replace the aggregate projection
later without changing the route contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from app.strategy_lab_v2.api_contracts import ApiCursor
from app.strategy_lab_v2.api_resources import (
    ApiResourceType,
    ResourceCollection,
    ResourceDocument,
    ResourceIdentifier,
)
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.storage import AggregateKey, StoredAggregate


class AggregateReadStore(Protocol):
    """Minimal read surface needed by :class:`PostgresResourceReader`."""

    async def get(self, key: AggregateKey) -> StoredAggregate | None: ...

    async def list_type(self, aggregate_type: str) -> tuple[StoredAggregate, ...]: ...


class PostgresResourceReader:
    """Project owner-scoped aggregate state into immutable API resources."""

    def __init__(self, store: AggregateReadStore) -> None:
        # Protocol runtime checks are intentionally avoided; duck typing keeps
        # test doubles and future SQLAlchemy adapters usable without requiring
        # ``@runtime_checkable`` on the structural contract.
        if not callable(getattr(store, "get", None)) or not callable(
            getattr(store, "list_type", None)
        ):
            raise TypeError("store must provide async get and list_type methods")
        self._store = store

    async def get_resource(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        resource_id: str,
    ) -> ResourceDocument | None:
        """Return one resource or ``None`` without leaking another owner’s row."""

        if not isinstance(resource_type, ApiResourceType):
            raise TypeError("resource_type must be an ApiResourceType")
        if not isinstance(resource_id, str) or not resource_id.strip():
            raise ValueError("resource_id must not be empty")
        aggregate = await self._store.get(AggregateKey(resource_type.value, resource_id))
        if aggregate is None:
            return None
        if not self._owned_by(aggregate, principal):
            return None
        return self._project(aggregate, resource_type)

    async def list_resources(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        limit: int,
        cursor: ApiCursor | None,
        request_id: str,
    ) -> ResourceCollection:
        """Return a deterministic page bound to the visible aggregate snapshot."""

        if not isinstance(resource_type, ApiResourceType):
            raise TypeError("resource_type must be an ApiResourceType")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if cursor is not None and not isinstance(cursor, ApiCursor):
            raise TypeError("cursor must be an ApiCursor or None")

        aggregates = await self._store.list_type(resource_type.value)
        records: list[tuple[str, ResourceDocument]] = []
        for aggregate in aggregates:
            if not self._owned_by(aggregate, principal):
                continue
            document = self._project(aggregate, resource_type)
            sort_value = self._sort_value(aggregate)
            records.append((sort_value, document))
        records.sort(key=lambda item: (item[0], item[1].id))
        if len({document.id for _, document in records}) != len(records):
            raise ValueError("visible resource IDs must be unique")
        snapshot_digest = content_digest(
            tuple((sort_value, document.id, document.fingerprint) for sort_value, document in records)
        )
        if cursor is not None:
            if cursor.resource != resource_type.value:
                raise ValueError("cursor resource does not match the requested collection")
            if cursor.snapshot_digest != snapshot_digest:
                raise ValueError("cursor snapshot does not match the visible resource set")
            records = [
                item for item in records if (item[0], item[1].id) > (cursor.sort_value, cursor.item_id)
            ]
        page = records[:limit]
        has_more = len(records) > len(page)
        next_cursor = None
        if has_more:
            sort_value, document = page[-1]
            next_cursor = ApiCursor(
                resource=resource_type.value,
                snapshot_digest=snapshot_digest,
                sort_value=sort_value,
                item_id=document.id,
            )
        return ResourceCollection(
            request_id=request_id,
            resource_type=resource_type,
            snapshot_digest=snapshot_digest,
            items=tuple(document for _, document in page),
            has_more=has_more,
            next_cursor=next_cursor,
        )

    @staticmethod
    def _owned_by(aggregate: StoredAggregate, principal: Any) -> bool:
        state = aggregate.state
        if not isinstance(state, Mapping) or "owner_id" not in state:
            raise ValueError("resource aggregate must declare owner_id")
        owner_id = state["owner_id"]
        principal_id = getattr(principal, "id", principal)
        if owner_id is None or principal_id is None:
            raise ValueError("resource owner identity must not be null")
        return str(owner_id) == str(principal_id)

    @staticmethod
    def _sort_value(aggregate: StoredAggregate) -> str:
        state = aggregate.state
        if not isinstance(state, Mapping):
            raise ValueError("resource aggregate state must be a mapping")
        value = state.get("sort_value", aggregate.key.aggregate_id)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("resource sort_value must be a non-empty string")
        return value

    @staticmethod
    def _project(aggregate: StoredAggregate, resource_type: ApiResourceType) -> ResourceDocument:
        state = aggregate.state
        if not isinstance(state, Mapping):
            raise ValueError("resource aggregate state must be a mapping")
        declared_type = state.get("resource_type", resource_type.value)
        if declared_type != resource_type.value:
            raise ValueError("resource aggregate type does not match the requested resource")
        declared_id = state.get("resource_id", aggregate.key.aggregate_id)
        if declared_id != aggregate.key.aggregate_id:
            raise ValueError("resource aggregate ID does not match its state")
        schema_version = state.get("schema_version", 1)
        if not isinstance(schema_version, int) or isinstance(schema_version, bool) or schema_version < 1:
            raise ValueError("resource schema_version must be a positive integer")
        revision_digest = state.get("revision_digest")
        if revision_digest is not None:
            require_sha256_digest(revision_digest, field_name="revision_digest")
        attributes = state.get("attributes", {})
        meta = state.get("meta", {})
        if not isinstance(attributes, Mapping) or not isinstance(meta, Mapping):
            raise ValueError("resource attributes and meta must be mappings")
        relationships = PostgresResourceReader._relationships(state.get("relationships", {}))
        return ResourceDocument(
            ResourceIdentifier(
                resource_type,
                aggregate.key.aggregate_id,
                schema_version=schema_version,
                revision_digest=revision_digest,
            ),
            attributes=attributes,
            relationships=relationships,
            meta=meta,
        )

    @staticmethod
    def _relationships(raw: Any) -> dict[str, tuple[ResourceIdentifier, ...]]:
        if not isinstance(raw, Mapping):
            raise ValueError("resource relationships must be a mapping")
        result: dict[str, tuple[ResourceIdentifier, ...]] = {}
        for name, targets in raw.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("relationship names must be non-empty strings")
            if not isinstance(targets, Sequence) or isinstance(targets, str | bytes):
                raise ValueError("relationship targets must be sequences")
            identifiers: list[ResourceIdentifier] = []
            for target in targets:
                if not isinstance(target, Mapping):
                    raise ValueError("relationship target must be a mapping")
                if set(target) != {"type", "id"}:
                    raise ValueError("relationship target must contain type and id only")
                try:
                    target_type = ApiResourceType(target["type"])
                except (TypeError, ValueError) as error:
                    raise ValueError("relationship target type is unsupported") from error
                identifiers.append(ResourceIdentifier(target_type, target["id"]))
            result[name] = tuple(identifiers)
        return result


__all__ = ["AggregateReadStore", "PostgresResourceReader"]
