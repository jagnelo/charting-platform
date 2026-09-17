"""Domain validation and canonicalization for API resource mutations.

The REST router intentionally accepts registration-neutral resource envelopes.
This module is the first application-owned domain boundary: it turns a
strategy resource into the immutable :class:`StrategyVersion` contract before
the application persists it, while leaving other resource types available to
their future domain adapters.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import StrategyDependency, StrategyVersion


@dataclass(frozen=True, slots=True)
class ResourceDomainNormalization:
    """Canonical attributes and optional typed-domain identity."""

    attributes: Mapping[str, Any]
    domain_fingerprint: str | None = None

    def __post_init__(self) -> None:
        normalized = freeze_json(self.attributes)
        if not isinstance(normalized, Mapping):
            raise TypeError("normalized resource attributes must be a mapping")
        if self.domain_fingerprint is not None:
            require_sha256_digest(self.domain_fingerprint, field_name="domain_fingerprint")
        object.__setattr__(self, "attributes", normalized)


def normalize_resource_attributes(
    resource_type: ApiResourceType,
    attributes: Mapping[str, Any],
) -> ResourceDomainNormalization:
    """Validate and canonicalize the domain fields for one resource.

    Strategy creation is deliberately strict because its source/dependency
    identity controls reproducibility. Other resources retain the generic
    frozen envelope until their domain-specific adapters are introduced.
    """

    if not isinstance(resource_type, ApiResourceType):
        raise TypeError("resource_type must be an ApiResourceType")
    if not isinstance(attributes, Mapping):
        raise TypeError("resource attributes must be a mapping")
    if resource_type is not ApiResourceType.STRATEGY:
        return ResourceDomainNormalization(attributes)
    return _normalize_strategy(attributes)


def _normalize_strategy(attributes: Mapping[str, Any]) -> ResourceDomainNormalization:
    allowed = {
        "strategy_id",
        "version_id",
        "sdk_version",
        "source_digest",
        "dependencies",
        "parameter_schema",
        "default_parameters",
        "resource_id",
        "id",
    }
    unknown = sorted(set(attributes) - allowed)
    if unknown:
        raise ValueError(f"strategy attributes contain unsupported fields: {', '.join(unknown)}")
    api_ids = [attributes[name] for name in ("resource_id", "id") if name in attributes]
    if any(not isinstance(value, str) or not value.strip() for value in api_ids):
        raise ValueError("strategy resource_id/id must be a non-empty string")
    if len(api_ids) == 2 and api_ids[0] != api_ids[1]:
        raise ValueError("strategy resource_id and id must agree")

    dependencies_raw = attributes.get("dependencies", ())
    if not isinstance(dependencies_raw, Sequence) or isinstance(dependencies_raw, str | bytes):
        raise ValueError("strategy dependencies must be a sequence")
    dependencies: list[StrategyDependency] = []
    for dependency in dependencies_raw:
        if not isinstance(dependency, Mapping) or set(dependency) != {
            "distribution",
            "version",
            "artifact_digest",
        }:
            raise ValueError(
                "strategy dependencies must contain distribution, version, and artifact_digest"
            )
        dependencies.append(
            StrategyDependency(
                dependency["distribution"],
                dependency["version"],
                dependency["artifact_digest"],
            )
        )
    parameter_schema = attributes.get("parameter_schema", {})
    default_parameters = attributes.get("default_parameters", {})
    if not isinstance(parameter_schema, Mapping):
        raise ValueError("strategy parameter_schema must be a mapping")
    if not isinstance(default_parameters, Mapping):
        raise ValueError("strategy default_parameters must be a mapping")
    try:
        strategy = StrategyVersion(
            strategy_id=attributes["strategy_id"],
            version_id=attributes["version_id"],
            sdk_version=attributes["sdk_version"],
            source_digest=attributes["source_digest"],
            dependencies=tuple(dependencies),
            parameter_schema=parameter_schema,
            default_parameters=default_parameters,
        )
    except KeyError as error:
        raise ValueError(f"strategy attribute is required: {error.args[0]}") from error

    normalized: dict[str, Any] = {
        "strategy_id": strategy.strategy_id,
        "version_id": strategy.version_id,
        "sdk_version": strategy.sdk_version,
        "source_digest": strategy.source_digest,
        "dependencies": tuple(
            {
                "distribution": item.distribution,
                "version": item.version,
                "artifact_digest": item.artifact_digest,
            }
            for item in strategy.dependencies
        ),
        "parameter_schema": strategy.parameter_schema,
        "default_parameters": strategy.default_parameters,
    }
    if api_ids:
        normalized["resource_id"] = api_ids[0]
    return ResourceDomainNormalization(normalized, strategy.fingerprint)


__all__ = ["ResourceDomainNormalization", "normalize_resource_attributes"]
