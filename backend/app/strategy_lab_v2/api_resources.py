"""Immutable resource and collection envelopes for Strategy Lab v2 routes.

These values are the machine-facing wire-model boundary for future adapters.
They do not serialize through FastAPI, authorize access, or read persistence;
the route layer remains responsible for those concerns.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from app.strategy_lab_v2.api_contracts import ApiCursor
from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class ApiResourceType(StrEnum):
    STRATEGY = "strategies"
    PACKAGE = "packages"
    PORTFOLIO = "portfolios"
    SNAPSHOT = "snapshots"
    EXPERIMENT = "experiments"
    TRIAL = "trials"
    ATTEMPT = "attempts"
    METRIC_SET = "metric-sets"
    ARTIFACT = "artifacts"
    FORWARD_INSTANCE = "forward-instances"


@dataclass(frozen=True, slots=True)
class ResourceIdentifier:
    """Stable public identity for one API resource."""

    resource_type: ApiResourceType
    resource_id: str
    schema_version: int = 1
    revision_digest: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.resource_type, ApiResourceType):
            raise TypeError("resource_type must be an ApiResourceType")
        _nonempty(self.resource_id, "resource_id")
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version < 1
        ):
            raise ValueError("schema_version must be a positive integer")
        if self.revision_digest is not None:
            require_sha256_digest(self.revision_digest, field_name="revision_digest")

    @property
    def type(self) -> str:
        return self.resource_type.value

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ResourceDocument:
    """One immutable resource document with frozen JSON-shaped fields."""

    identity: ResourceIdentifier
    attributes: Mapping[str, Any] = field(default_factory=dict)
    relationships: Mapping[str, tuple[ResourceIdentifier, ...]] = field(default_factory=dict)
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.identity, ResourceIdentifier):
            raise TypeError("identity must be a ResourceIdentifier")
        if not isinstance(self.attributes, Mapping):
            raise TypeError("attributes must be a mapping")
        if not isinstance(self.relationships, Mapping):
            raise TypeError("relationships must be a mapping")
        if not isinstance(self.meta, Mapping):
            raise TypeError("meta must be a mapping")
        frozen_attributes = freeze_json(self.attributes)
        frozen_meta = freeze_json(self.meta)
        if not isinstance(frozen_attributes, Mapping) or not isinstance(frozen_meta, Mapping):
            raise TypeError("resource fields must be mappings")
        normalized_relationships: dict[str, tuple[ResourceIdentifier, ...]] = {}
        for name, targets in self.relationships.items():
            _nonempty(name, "relationship name")
            if not isinstance(targets, Sequence) or isinstance(targets, str | bytes):
                raise TypeError("relationship values must be sequences")
            normalized = tuple(targets)
            if any(not isinstance(target, ResourceIdentifier) for target in normalized):
                raise TypeError("relationships must contain ResourceIdentifier values")
            normalized_relationships[name] = normalized
        object.__setattr__(self, "attributes", frozen_attributes)
        object.__setattr__(self, "relationships", MappingProxyType(normalized_relationships))
        object.__setattr__(self, "meta", frozen_meta)

    @property
    def type(self) -> str:
        return self.identity.type

    @property
    def id(self) -> str:
        return self.identity.resource_id

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ResourceCollection:
    """Snapshot-bound collection response for cursor-paginated resources."""

    request_id: str
    resource_type: ApiResourceType
    snapshot_digest: str
    items: tuple[ResourceDocument, ...] = ()
    has_more: bool = False
    next_cursor: ApiCursor | None = None

    def __post_init__(self) -> None:
        _nonempty(self.request_id, "request_id")
        if not isinstance(self.resource_type, ApiResourceType):
            raise TypeError("resource_type must be an ApiResourceType")
        require_sha256_digest(self.snapshot_digest, field_name="snapshot_digest")
        if not isinstance(self.items, tuple):
            object.__setattr__(self, "items", tuple(self.items))
        if any(not isinstance(item, ResourceDocument) for item in self.items):
            raise TypeError("items must contain ResourceDocument values")
        if any(item.identity.resource_type is not self.resource_type for item in self.items):
            raise ValueError("items must use the collection resource type")
        if not isinstance(self.has_more, bool):
            raise TypeError("has_more must be a boolean")
        if self.next_cursor is not None:
            if not isinstance(self.next_cursor, ApiCursor):
                raise TypeError("next_cursor must be an ApiCursor")
            if self.next_cursor.resource != self.resource_type.value:
                raise ValueError("next_cursor must reference the collection resource")
            if self.next_cursor.snapshot_digest != self.snapshot_digest:
                raise ValueError("next_cursor must reference the collection snapshot")
        if self.has_more and self.next_cursor is None:
            raise ValueError("a collection with more items requires next_cursor")
        if not self.has_more and self.next_cursor is not None:
            raise ValueError("a final collection must not expose next_cursor")

    @property
    def http_status(self) -> int:
        return 200

    @property
    def resource(self) -> str:
        return self.resource_type.value

    @property
    def fingerprint(self) -> str:
        return content_digest(self)
