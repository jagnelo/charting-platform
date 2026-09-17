"""Domain validation and canonicalization for API resource mutations.

The REST router intentionally accepts registration-neutral resource envelopes.
This module is the first application-owned domain boundary: it turns strategy
and package resources into immutable :class:`StrategyVersion` and
:class:`StrategyPackage` contracts before the application persists them, while
leaving other resource types available to their future domain adapters.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    StrategyDependency,
    StrategyPackage,
    StrategyPackageFormat,
    StrategyVersion,
)


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

    Strategy and package creation are deliberately strict because their
    source/dependency/runtime identities control reproducibility. Other
    resources retain the generic frozen envelope until their domain-specific
    adapters are introduced.
    """

    if not isinstance(resource_type, ApiResourceType):
        raise TypeError("resource_type must be an ApiResourceType")
    if not isinstance(attributes, Mapping):
        raise TypeError("resource attributes must be a mapping")
    if resource_type is ApiResourceType.STRATEGY:
        return _normalize_strategy(attributes)
    if resource_type is ApiResourceType.PACKAGE:
        return _normalize_package(attributes)
    return ResourceDomainNormalization(attributes)


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


def _normalize_package(attributes: Mapping[str, Any]) -> ResourceDomainNormalization:
    allowed = {
        "package_id",
        "strategy_fingerprint",
        "package_format",
        "archive_digest",
        "manifest_digest",
        "dependency_lock_digest",
        "archive_byte_length",
        "entrypoint",
        "sdk_version",
        "runtime_abi",
        "resource_id",
        "id",
    }
    unknown = sorted(set(attributes) - allowed)
    if unknown:
        raise ValueError(f"package attributes contain unsupported fields: {', '.join(unknown)}")
    api_ids = [attributes[name] for name in ("resource_id", "id") if name in attributes]
    if any(not isinstance(value, str) or not value.strip() for value in api_ids):
        raise ValueError("package resource_id/id must be a non-empty string")
    if len(api_ids) == 2 and api_ids[0] != api_ids[1]:
        raise ValueError("package resource_id and id must agree")
    try:
        package_format = StrategyPackageFormat(attributes["package_format"])
        package = StrategyPackage(
            package_id=attributes["package_id"],
            strategy_fingerprint=attributes["strategy_fingerprint"],
            package_format=package_format,
            archive_digest=attributes["archive_digest"],
            manifest_digest=attributes["manifest_digest"],
            dependency_lock_digest=attributes["dependency_lock_digest"],
            archive_byte_length=attributes["archive_byte_length"],
            entrypoint=attributes["entrypoint"],
            sdk_version=attributes["sdk_version"],
            runtime_abi=attributes["runtime_abi"],
        )
    except KeyError as error:
        raise ValueError(f"package attribute is required: {error.args[0]}") from error
    except (TypeError, ValueError) as error:
        raise ValueError(f"package attributes are invalid: {error}") from error

    normalized: dict[str, Any] = {
        "package_id": package.package_id,
        "strategy_fingerprint": package.strategy_fingerprint,
        "package_format": package.package_format,
        "archive_digest": package.archive_digest,
        "manifest_digest": package.manifest_digest,
        "dependency_lock_digest": package.dependency_lock_digest,
        "archive_byte_length": package.archive_byte_length,
        "entrypoint": package.entrypoint,
        "sdk_version": package.sdk_version,
        "runtime_abi": package.runtime_abi,
    }
    if api_ids:
        normalized["resource_id"] = api_ids[0]
    return ResourceDomainNormalization(normalized, package.fingerprint)


__all__ = ["ResourceDomainNormalization", "normalize_resource_attributes"]
