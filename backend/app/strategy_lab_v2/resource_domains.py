"""Domain validation and canonicalization for API resource mutations.

The REST router intentionally accepts registration-neutral resource envelopes.
This module is the first application-owned domain boundary: it turns strategy,
package, and portfolio resources into immutable :class:`StrategyVersion`,
:class:`StrategyPackage`, and :class:`PortfolioComposition` contracts before
the application persists them, while leaving other resource types available to
their future domain adapters.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    ExperimentDefinition,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    ProductRiskModel,
    RiskExposureMeasure,
    SharedRiskPolicy,
    StrategyDependency,
    StrategyPackage,
    StrategyPackageFormat,
    StrategyVersion,
    TargetConflictPolicy,
)
from app.strategy_lab_v2.rebalance import (
    CalendarRebalancePolicy,
    RebalanceCadence,
    RebalanceMisfirePolicy,
    RebalanceSelection,
    RebalanceTrigger,
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
    if resource_type is ApiResourceType.PORTFOLIO:
        return _normalize_portfolio(attributes)
    if resource_type is ApiResourceType.EXPERIMENT:
        return _normalize_experiment(attributes)
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


def _decimal_attribute(value: Any, field_name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError(f"{field_name} must be an exact decimal string or integer")
    try:
        decimal_value = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be an exact decimal string or integer") from error
    if not decimal_value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return decimal_value


def _enum_attribute(enum_type: type[Any], value: Any, field_name: str) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} is invalid") from error


def _normalize_portfolio(attributes: Mapping[str, Any]) -> ResourceDomainNormalization:
    allowed = {
        "portfolio_id",
        "version_id",
        "initial_capital",
        "base_currency",
        "components",
        "rebalance_policy",
        "shared_risk_policy",
        "resource_id",
        "id",
    }
    unknown = sorted(set(attributes) - allowed)
    if unknown:
        raise ValueError(f"portfolio attributes contain unsupported fields: {', '.join(unknown)}")
    api_ids = [attributes[name] for name in ("resource_id", "id") if name in attributes]
    if any(not isinstance(value, str) or not value.strip() for value in api_ids):
        raise ValueError("portfolio resource_id/id must be a non-empty string")
    if len(api_ids) == 2 and api_ids[0] != api_ids[1]:
        raise ValueError("portfolio resource_id and id must agree")

    try:
        components_raw = attributes["components"]
        if not isinstance(components_raw, Sequence) or isinstance(components_raw, str | bytes):
            raise ValueError("portfolio components must be a sequence")
        components = tuple(_portfolio_component(item) for item in components_raw)
        rebalance_policy = _rebalance_policy(attributes.get("rebalance_policy"))
        shared_risk_policy = _shared_risk_policy(attributes.get("shared_risk_policy", {}))
        portfolio = PortfolioComposition(
            portfolio_id=attributes["portfolio_id"],
            version_id=attributes["version_id"],
            initial_capital=_decimal_attribute(attributes["initial_capital"], "initial_capital"),
            base_currency=attributes["base_currency"],
            components=components,
            rebalance_policy=rebalance_policy,
            shared_risk_policy=shared_risk_policy,
        )
    except KeyError as error:
        raise ValueError(f"portfolio attribute is required: {error.args[0]}") from error
    except (AttributeError, TypeError, ValueError) as error:
        if isinstance(error, ValueError) and str(error).startswith("portfolio "):
            raise
        raise ValueError(f"portfolio attributes are invalid: {error}") from error

    normalized: dict[str, Any] = {
        "portfolio_id": portfolio.portfolio_id,
        "version_id": portfolio.version_id,
        "initial_capital": portfolio.initial_capital,
        "base_currency": portfolio.base_currency,
        "components": tuple(
            {
                "component_id": item.component_id,
                "strategy_fingerprint": item.strategy_fingerprint,
                "instrument_ids": item.instrument_ids,
                "capital_weight": item.capital_weight,
                "priority": item.priority,
            }
            for item in portfolio.components
        ),
        "rebalance_policy": _rebalance_attributes(portfolio.rebalance_policy),
        "shared_risk_policy": _shared_risk_attributes(portfolio.shared_risk_policy),
    }
    if api_ids:
        normalized["resource_id"] = api_ids[0]
    return ResourceDomainNormalization(normalized, portfolio.fingerprint)


def _normalize_experiment(attributes: Mapping[str, Any]) -> ResourceDomainNormalization:
    allowed = {
        "experiment_id",
        "portfolio_fingerprint",
        "strategy_fingerprints",
        "snapshot_fingerprint",
        "capability_contract_digest",
        "seed",
        "metric_definition_version",
        "engine_contract",
        "resource_id",
        "id",
    }
    unknown = sorted(set(attributes) - allowed)
    if unknown:
        raise ValueError(
            f"experiment attributes contain unsupported fields: {', '.join(unknown)}"
        )
    api_ids = [attributes[name] for name in ("resource_id", "id") if name in attributes]
    if any(not isinstance(value, str) or not value.strip() for value in api_ids):
        raise ValueError("experiment resource_id/id must be a non-empty string")
    if len(api_ids) == 2 and api_ids[0] != api_ids[1]:
        raise ValueError("experiment resource_id and id must agree")
    strategy_fingerprints = attributes.get("strategy_fingerprints")
    if not isinstance(strategy_fingerprints, Sequence) or isinstance(
        strategy_fingerprints, str | bytes
    ):
        raise ValueError("experiment strategy_fingerprints must be a sequence")
    if any(not isinstance(value, str) for value in strategy_fingerprints):
        raise ValueError("experiment strategy_fingerprints must contain strings")
    engine_contract = attributes.get("engine_contract", {})
    if not isinstance(engine_contract, Mapping):
        raise ValueError("experiment engine_contract must be a mapping")
    seed = attributes.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("experiment seed must be an integer")
    try:
        experiment = ExperimentDefinition(
            experiment_id=attributes["experiment_id"],
            portfolio_fingerprint=attributes["portfolio_fingerprint"],
            strategy_fingerprints=tuple(strategy_fingerprints),
            snapshot_fingerprint=attributes["snapshot_fingerprint"],
            capability_contract_digest=attributes["capability_contract_digest"],
            seed=seed,
            metric_definition_version=attributes["metric_definition_version"],
            engine_contract=engine_contract,
        )
    except KeyError as error:
        raise ValueError(f"experiment attribute is required: {error.args[0]}") from error
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"experiment attributes are invalid: {error}") from error

    normalized: dict[str, Any] = {
        "experiment_id": experiment.experiment_id,
        "portfolio_fingerprint": experiment.portfolio_fingerprint,
        "strategy_fingerprints": experiment.strategy_fingerprints,
        "snapshot_fingerprint": experiment.snapshot_fingerprint,
        "capability_contract_digest": experiment.capability_contract_digest,
        "seed": experiment.seed,
        "metric_definition_version": experiment.metric_definition_version,
        "engine_contract": experiment.engine_contract,
    }
    if api_ids:
        normalized["resource_id"] = api_ids[0]
    return ResourceDomainNormalization(normalized, experiment.fingerprint)


def _portfolio_component(value: Any) -> PortfolioComponent:
    if not isinstance(value, Mapping):
        raise ValueError("portfolio components must contain mappings")
    allowed = {"component_id", "strategy_fingerprint", "instrument_ids", "capital_weight", "priority"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"portfolio component contains unsupported fields: {', '.join(unknown)}")
    instruments = value.get("instrument_ids")
    if not isinstance(instruments, Sequence) or isinstance(instruments, str | bytes):
        raise ValueError("portfolio component instrument_ids must be a sequence")
    if any(not isinstance(item, str) or not item.strip() for item in instruments):
        raise ValueError("portfolio component instrument_ids must contain non-empty strings")
    return PortfolioComponent(
        component_id=value["component_id"],
        strategy_fingerprint=value["strategy_fingerprint"],
        instrument_ids=tuple(instruments),
        capital_weight=_decimal_attribute(value["capital_weight"], "capital_weight"),
        priority=value.get("priority", 0),
    )


def _rebalance_policy(value: Any) -> CalendarRebalancePolicy | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("rebalance_policy must be a mapping or null")
    allowed = {
        "calendar_id",
        "calendar_fingerprint",
        "cadence",
        "trigger",
        "selection",
        "misfire_policy",
        "definition_version",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"rebalance_policy contains unsupported fields: {', '.join(unknown)}")
    try:
        return CalendarRebalancePolicy(
            calendar_id=value["calendar_id"],
            calendar_fingerprint=value["calendar_fingerprint"],
            cadence=_enum_attribute(RebalanceCadence, value["cadence"], "rebalance cadence"),
            trigger=_enum_attribute(RebalanceTrigger, value["trigger"], "rebalance trigger"),
            selection=_enum_attribute(
                RebalanceSelection,
                value.get("selection", RebalanceSelection.FIRST_SESSION),
                "rebalance selection",
            ),
            misfire_policy=_enum_attribute(
                RebalanceMisfirePolicy,
                value.get("misfire_policy", RebalanceMisfirePolicy.FAIL_RUN),
                "rebalance misfire policy",
            ),
            definition_version=value.get("definition_version", "strategy-lab.rebalance-policy.v1"),
        )
    except KeyError as error:
        raise ValueError(f"rebalance_policy field is required: {error.args[0]}") from error


def _shared_risk_policy(value: Any) -> SharedRiskPolicy:
    if not isinstance(value, Mapping):
        raise ValueError("shared_risk_policy must be a mapping")
    allowed = {
        "max_gross_exposure_fraction",
        "max_net_exposure_fraction",
        "max_instrument_gross_exposure_fraction",
        "max_component_gross_exposure_fraction",
        "max_component_leverage",
        "max_open_instruments",
        "allow_short_positions",
        "target_conflict_policy",
        "risk_models",
        "definition_version",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"shared_risk_policy contains unsupported fields: {', '.join(unknown)}")
    risk_models_raw = value.get("risk_models", ())
    if not isinstance(risk_models_raw, Sequence) or isinstance(risk_models_raw, str | bytes):
        raise ValueError("shared_risk_policy risk_models must be a sequence")
    risk_models = tuple(_product_risk_model(item) for item in risk_models_raw)
    return SharedRiskPolicy(
        max_gross_exposure_fraction=_decimal_attribute(
            value.get("max_gross_exposure_fraction", Decimal("1.0")),
            "max_gross_exposure_fraction",
        ),
        max_net_exposure_fraction=_decimal_attribute(
            value.get("max_net_exposure_fraction", Decimal("1.0")),
            "max_net_exposure_fraction",
        ),
        max_instrument_gross_exposure_fraction=_decimal_attribute(
            value.get("max_instrument_gross_exposure_fraction", Decimal("1.0")),
            "max_instrument_gross_exposure_fraction",
        ),
        max_component_gross_exposure_fraction=_decimal_attribute(
            value.get("max_component_gross_exposure_fraction", Decimal("1.0")),
            "max_component_gross_exposure_fraction",
        ),
        max_component_leverage=_decimal_attribute(
            value.get("max_component_leverage", Decimal("1.0")), "max_component_leverage"
        ),
        max_open_instruments=value.get("max_open_instruments"),
        allow_short_positions=value.get("allow_short_positions", False),
        target_conflict_policy=_enum_attribute(
            TargetConflictPolicy,
            value.get("target_conflict_policy", TargetConflictPolicy.REJECT),
            "target_conflict_policy",
        ),
        risk_models=risk_models,
        definition_version=value.get("definition_version", "strategy-lab.shared-risk.v1"),
    )


def _product_risk_model(value: Any) -> ProductRiskModel:
    if not isinstance(value, Mapping):
        raise ValueError("risk_models must contain mappings")
    allowed = {"product_class", "exposure_measure", "definition_digest"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"risk model contains unsupported fields: {', '.join(unknown)}")
    try:
        return ProductRiskModel(
            product_class=_enum_attribute(ProductClass, value["product_class"], "product_class"),
            exposure_measure=_enum_attribute(
                RiskExposureMeasure, value["exposure_measure"], "exposure_measure"
            ),
            definition_digest=value["definition_digest"],
        )
    except KeyError as error:
        raise ValueError(f"risk model field is required: {error.args[0]}") from error


def _rebalance_attributes(policy: CalendarRebalancePolicy | None) -> Mapping[str, Any] | None:
    if policy is None:
        return None
    return {
        "calendar_id": policy.calendar_id,
        "calendar_fingerprint": policy.calendar_fingerprint,
        "cadence": policy.cadence,
        "trigger": policy.trigger,
        "selection": policy.selection,
        "misfire_policy": policy.misfire_policy,
        "definition_version": policy.definition_version,
    }


def _shared_risk_attributes(policy: SharedRiskPolicy) -> Mapping[str, Any]:
    return {
        "max_gross_exposure_fraction": policy.max_gross_exposure_fraction,
        "max_net_exposure_fraction": policy.max_net_exposure_fraction,
        "max_instrument_gross_exposure_fraction": policy.max_instrument_gross_exposure_fraction,
        "max_component_gross_exposure_fraction": policy.max_component_gross_exposure_fraction,
        "max_component_leverage": policy.max_component_leverage,
        "max_open_instruments": policy.max_open_instruments,
        "allow_short_positions": policy.allow_short_positions,
        "target_conflict_policy": policy.target_conflict_policy,
        "risk_models": tuple(
            {
                "product_class": item.product_class,
                "exposure_measure": item.exposure_measure,
                "definition_digest": item.definition_digest,
            }
            for item in policy.risk_models
        ),
        "definition_version": policy.definition_version,
    }


__all__ = ["ResourceDomainNormalization", "normalize_resource_attributes"]
