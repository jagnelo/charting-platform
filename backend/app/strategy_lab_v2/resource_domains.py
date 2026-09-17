"""Domain validation and canonicalization for API resource mutations.

The REST router intentionally accepts registration-neutral resource envelopes.
This module is the first application-owned domain boundary: it turns strategy,
package, portfolio, experiment, attempt, snapshot, trial, metric-set, and
forward-instance resources into immutable typed contracts before the application
persists them, while leaving other
resource types available to their future domain adapters.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityDecision,
    CapabilityRequirement,
    Degradation,
    PreflightClass,
    PreflightReport,
)
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    AttemptState,
    CarryInMode,
    DataSeriesManifest,
    DataSnapshot,
    EvaluationWindow,
    EventGranularity,
    ExperimentDefinition,
    ForwardInstance,
    ForwardState,
    MetricBasis,
    MetricCalculationDefinition,
    MetricEvidenceReference,
    MetricSet,
    MetricValue,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    ProductRiskModel,
    RiskExposureMeasure,
    RunAttempt,
    ScientificTrial,
    SharedRiskPolicy,
    StrategyDependency,
    StrategyPackage,
    StrategyPackageFormat,
    StrategyVersion,
    TargetConflictPolicy,
    TrialRandomization,
    TrialSeedPolicy,
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

    Typed strategy, package, portfolio, experiment, attempt, snapshot, trial,
    metric-set, and forward-instance creation is deliberately strict because
    these identities
    control reproducibility. Other resources retain the generic frozen envelope
    until their domain-specific adapters are introduced.
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
    if resource_type is ApiResourceType.ATTEMPT:
        return _normalize_attempt(attributes)
    if resource_type is ApiResourceType.SNAPSHOT:
        return _normalize_snapshot(attributes)
    if resource_type is ApiResourceType.TRIAL:
        return _normalize_trial(attributes)
    if resource_type is ApiResourceType.METRIC_SET:
        return _normalize_metric_set(attributes)
    if resource_type is ApiResourceType.FORWARD_INSTANCE:
        return _normalize_forward_instance(attributes)
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


def _datetime_attribute(value: Any, field_name: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from error
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be a timezone-aware timestamp")
    return value.astimezone(UTC)


def _normalize_attempt(attributes: Mapping[str, Any]) -> ResourceDomainNormalization:
    allowed = {
        "attempt_id",
        "trial_id",
        "ordinal",
        "state",
        "created_at",
        "updated_at",
        "resource_id",
        "id",
    }
    unknown = sorted(set(attributes) - allowed)
    if unknown:
        raise ValueError(f"attempt attributes contain unsupported fields: {', '.join(unknown)}")
    api_ids = [attributes[name] for name in ("resource_id", "id") if name in attributes]
    if any(not isinstance(value, str) or not value.strip() for value in api_ids):
        raise ValueError("attempt resource_id/id must be a non-empty string")
    if len(api_ids) == 2 and api_ids[0] != api_ids[1]:
        raise ValueError("attempt resource_id and id must agree")
    try:
        attempt = RunAttempt(
            attempt_id=attributes["attempt_id"],
            trial_id=attributes["trial_id"],
            ordinal=attributes["ordinal"],
            state=_enum_attribute(AttemptState, attributes["state"], "attempt state"),
            created_at=_datetime_attribute(attributes["created_at"], "created_at"),
            updated_at=(
                _datetime_attribute(attributes["updated_at"], "updated_at")
                if "updated_at" in attributes
                else None
            ),
        )
    except KeyError as error:
        raise ValueError(f"attempt attribute is required: {error.args[0]}") from error
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"attempt attributes are invalid: {error}") from error

    normalized: dict[str, Any] = {
        "attempt_id": attempt.attempt_id,
        "trial_id": attempt.trial_id,
        "ordinal": attempt.ordinal,
        "state": attempt.state,
        "created_at": attempt.created_at,
        "updated_at": attempt.updated_at,
    }
    if api_ids:
        normalized["resource_id"] = api_ids[0]
    identity = {
        "attempt_id": attempt.attempt_id,
        "trial_id": attempt.trial_id,
        "ordinal": attempt.ordinal,
    }
    return ResourceDomainNormalization(normalized, content_digest(identity))


def _normalize_snapshot(attributes: Mapping[str, Any]) -> ResourceDomainNormalization:
    allowed = {
        "snapshot_id",
        "provider_snapshot_id",
        "preflight_report",
        "series",
        "created_at",
        "resource_id",
        "id",
    }
    unknown = sorted(set(attributes) - allowed)
    if unknown:
        raise ValueError(f"snapshot attributes contain unsupported fields: {', '.join(unknown)}")
    api_ids = [attributes[name] for name in ("resource_id", "id") if name in attributes]
    if any(not isinstance(value, str) or not value.strip() for value in api_ids):
        raise ValueError("snapshot resource_id/id must be a non-empty string")
    if len(api_ids) == 2 and api_ids[0] != api_ids[1]:
        raise ValueError("snapshot resource_id and id must agree")
    try:
        series_raw = attributes["series"]
        if not isinstance(series_raw, Sequence) or isinstance(series_raw, str | bytes):
            raise ValueError("snapshot series must be a sequence")
        snapshot = DataSnapshot(
            snapshot_id=attributes["snapshot_id"],
            provider_snapshot_id=attributes["provider_snapshot_id"],
            preflight_report=_preflight_report(attributes["preflight_report"]),
            series=tuple(_data_series_manifest(item) for item in series_raw),
            created_at=_datetime_attribute(attributes["created_at"], "created_at"),
        )
    except KeyError as error:
        raise ValueError(f"snapshot attribute is required: {error.args[0]}") from error
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"snapshot attributes are invalid: {error}") from error

    normalized: dict[str, Any] = {
        "snapshot_id": snapshot.snapshot_id,
        "provider_snapshot_id": snapshot.provider_snapshot_id,
        "preflight_report": _preflight_attributes(snapshot.preflight_report),
        "series": tuple(_series_attributes(item) for item in snapshot.series),
        "created_at": snapshot.created_at,
    }
    if api_ids:
        normalized["resource_id"] = api_ids[0]
    return ResourceDomainNormalization(normalized, snapshot.fingerprint)


def _normalize_trial(attributes: Mapping[str, Any]) -> ResourceDomainNormalization:
    allowed = {
        "trial_id",
        "experiment_fingerprint",
        "snapshot_fingerprint",
        "preflight_report",
        "parameter_set",
        "scenario",
        "seed",
        "randomization",
        "evaluation_window",
        "resource_id",
        "id",
    }
    unknown = sorted(set(attributes) - allowed)
    if unknown:
        raise ValueError(f"trial attributes contain unsupported fields: {', '.join(unknown)}")
    api_ids = [attributes[name] for name in ("resource_id", "id") if name in attributes]
    if any(not isinstance(value, str) or not value.strip() for value in api_ids):
        raise ValueError("trial resource_id/id must be a non-empty string")
    if len(api_ids) == 2 and api_ids[0] != api_ids[1]:
        raise ValueError("trial resource_id and id must agree")
    parameter_set = attributes.get("parameter_set", {})
    scenario = attributes.get("scenario", {})
    if not isinstance(parameter_set, Mapping):
        raise ValueError("trial parameter_set must be a mapping")
    if not isinstance(scenario, Mapping):
        raise ValueError("trial scenario must be a mapping")
    try:
        randomization = (
            _trial_randomization(attributes["randomization"])
            if "randomization" in attributes
            else None
        )
        evaluation_window = (
            _evaluation_window(attributes["evaluation_window"])
            if "evaluation_window" in attributes
            else None
        )
        trial = ScientificTrial.create(
            experiment_fingerprint=attributes["experiment_fingerprint"],
            snapshot_fingerprint=attributes["snapshot_fingerprint"],
            preflight_report=_preflight_report(attributes["preflight_report"]),
            parameter_set=parameter_set,
            scenario=scenario,
            seed=attributes.get("seed"),
            randomization=randomization,
            evaluation_window=evaluation_window,
        )
        if "trial_id" in attributes and attributes["trial_id"] != trial.trial_id:
            raise ValueError("trial_id does not match the immutable trial identity")
    except KeyError as error:
        raise ValueError(f"trial attribute is required: {error.args[0]}") from error
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"trial attributes are invalid: {error}") from error

    normalized: dict[str, Any] = {
        "trial_id": trial.trial_id,
        "experiment_fingerprint": trial.experiment_fingerprint,
        "snapshot_fingerprint": trial.snapshot_fingerprint,
        "preflight_report": _preflight_attributes(trial.preflight_report),
        "parameter_set": trial.parameter_set,
        "scenario": trial.scenario,
        "seed": trial.seed,
        "randomization": _trial_randomization_attributes(trial.randomization),
        "evaluation_window": _evaluation_window_attributes(trial.evaluation_window),
    }
    if api_ids:
        normalized["resource_id"] = api_ids[0]
    return ResourceDomainNormalization(normalized, trial.trial_id)


def _trial_randomization(value: Any) -> TrialRandomization:
    if not isinstance(value, Mapping):
        raise ValueError("trial randomization must be a mapping")
    allowed = {
        "master_seed",
        "seed",
        "policy",
        "replicate_index",
        "scope_fingerprint",
        "seed_group_fingerprint",
        "replicate_count",
        "derivation_version",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"trial randomization contains unsupported fields: {', '.join(unknown)}")
    try:
        return TrialRandomization(
            master_seed=value["master_seed"],
            seed=value["seed"],
            policy=_enum_attribute(TrialSeedPolicy, value["policy"], "trial seed policy"),
            replicate_index=value["replicate_index"],
            scope_fingerprint=value.get("scope_fingerprint"),
            seed_group_fingerprint=value.get("seed_group_fingerprint"),
            replicate_count=value["replicate_count"],
            derivation_version=value["derivation_version"],
        )
    except KeyError as error:
        raise ValueError(f"trial randomization field is required: {error.args[0]}") from error


def _evaluation_window(value: Any) -> EvaluationWindow:
    if not isinstance(value, Mapping):
        raise ValueError("trial evaluation_window must be a mapping")
    allowed = {"start", "end", "purpose", "warmup_start"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"evaluation_window contains unsupported fields: {', '.join(unknown)}")
    try:
        return EvaluationWindow(
            start=_datetime_attribute(value["start"], "evaluation start"),
            end=_datetime_attribute(value["end"], "evaluation end"),
            purpose=value["purpose"],
            warmup_start=(
                _datetime_attribute(value["warmup_start"], "evaluation warmup_start")
                if value.get("warmup_start") is not None
                else None
            ),
        )
    except KeyError as error:
        raise ValueError(f"evaluation_window field is required: {error.args[0]}") from error


def _trial_randomization_attributes(value: TrialRandomization) -> Mapping[str, Any]:
    return {
        "master_seed": value.master_seed,
        "seed": value.seed,
        "policy": value.policy,
        "replicate_index": value.replicate_index,
        "scope_fingerprint": value.scope_fingerprint,
        "seed_group_fingerprint": value.seed_group_fingerprint,
        "replicate_count": value.replicate_count,
        "derivation_version": value.derivation_version,
    }


def _evaluation_window_attributes(value: EvaluationWindow | None) -> Mapping[str, Any] | None:
    if value is None:
        return None
    return {
        "start": value.start,
        "end": value.end,
        "purpose": value.purpose,
        "warmup_start": value.warmup_start,
    }


def _normalize_metric_set(attributes: Mapping[str, Any]) -> ResourceDomainNormalization:
    allowed = {
        "metric_set_id",
        "trial_id",
        "attempt_id",
        "definition_version",
        "values",
        "created_at",
        "resource_id",
        "id",
    }
    unknown = sorted(set(attributes) - allowed)
    if unknown:
        raise ValueError(f"metric_set attributes contain unsupported fields: {', '.join(unknown)}")
    api_ids = [attributes[name] for name in ("resource_id", "id") if name in attributes]
    if any(not isinstance(value, str) or not value.strip() for value in api_ids):
        raise ValueError("metric_set resource_id/id must be a non-empty string")
    if len(api_ids) == 2 and api_ids[0] != api_ids[1]:
        raise ValueError("metric_set resource_id and id must agree")
    try:
        values_raw = attributes["values"]
        if not isinstance(values_raw, Sequence) or isinstance(values_raw, str | bytes):
            raise ValueError("metric_set values must be a sequence")
        metric_set = MetricSet(
            metric_set_id=attributes["metric_set_id"],
            trial_id=attributes["trial_id"],
            attempt_id=attributes["attempt_id"],
            definition_version=attributes["definition_version"],
            values=tuple(_metric_value(item) for item in values_raw),
            created_at=_datetime_attribute(attributes["created_at"], "created_at"),
        )
    except KeyError as error:
        raise ValueError(f"metric_set attribute is required: {error.args[0]}") from error
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"metric_set attributes are invalid: {error}") from error

    normalized: dict[str, Any] = {
        "metric_set_id": metric_set.metric_set_id,
        "trial_id": metric_set.trial_id,
        "attempt_id": metric_set.attempt_id,
        "definition_version": metric_set.definition_version,
        "values": tuple(_metric_value_attributes(item) for item in metric_set.values),
        "created_at": metric_set.created_at,
    }
    if api_ids:
        normalized["resource_id"] = api_ids[0]
    return ResourceDomainNormalization(normalized, metric_set.fingerprint)


def _metric_value(value: Any) -> MetricValue:
    if not isinstance(value, Mapping):
        raise ValueError("metric_set values must contain mappings")
    allowed = {
        "name",
        "value",
        "unit",
        "definition_version",
        "basis",
        "sample_size",
        "annualization_basis",
        "calculation_basis",
        "null_reason",
        "calculation_definition",
        "evidence_references",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"metric value contains unsupported fields: {', '.join(unknown)}")
    evidence_raw = value.get("evidence_references", ())
    if not isinstance(evidence_raw, Sequence) or isinstance(evidence_raw, str | bytes):
        raise ValueError("metric evidence_references must be a sequence")
    calculation_definition = value.get("calculation_definition")
    if calculation_definition is not None:
        calculation_definition = _metric_calculation_definition(calculation_definition)
    metric_value = value.get("value")
    if metric_value is not None:
        metric_value = _decimal_attribute(metric_value, "metric value")
    try:
        return MetricValue(
            name=value["name"],
            value=metric_value,
            unit=value["unit"],
            definition_version=value["definition_version"],
            basis=_enum_attribute(MetricBasis, value["basis"], "metric basis"),
            sample_size=value["sample_size"],
            annualization_basis=value.get("annualization_basis"),
            calculation_basis=value.get("calculation_basis"),
            null_reason=value.get("null_reason"),
            calculation_definition=calculation_definition,
            evidence_references=tuple(_metric_evidence_reference(item) for item in evidence_raw),
        )
    except KeyError as error:
        raise ValueError(f"metric value field is required: {error.args[0]}") from error


def _metric_calculation_definition(value: Any) -> MetricCalculationDefinition:
    if not isinstance(value, Mapping):
        raise ValueError("calculation_definition must be a mapping")
    allowed = {"formula_id", "contract_version", "parameters"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(
            f"calculation_definition contains unsupported fields: {', '.join(unknown)}"
        )
    parameters = value.get("parameters", {})
    if not isinstance(parameters, Mapping):
        raise ValueError("calculation_definition parameters must be a mapping")
    try:
        return MetricCalculationDefinition(
            formula_id=value["formula_id"],
            contract_version=value["contract_version"],
            parameters=parameters,
        )
    except KeyError as error:
        raise ValueError(f"calculation_definition field is required: {error.args[0]}") from error


def _metric_evidence_reference(value: Any) -> MetricEvidenceReference:
    if not isinstance(value, Mapping):
        raise ValueError("metric evidence references must contain mappings")
    allowed = {"role", "digest"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"metric evidence contains unsupported fields: {', '.join(unknown)}")
    try:
        return MetricEvidenceReference(role=value["role"], digest=value["digest"])
    except KeyError as error:
        raise ValueError(f"metric evidence field is required: {error.args[0]}") from error


def _metric_value_attributes(value: MetricValue) -> Mapping[str, Any]:
    calculation_definition = value.calculation_definition
    calculation_attributes = None
    if calculation_definition is not None:
        calculation_attributes = {
            "formula_id": calculation_definition.formula_id,
            "contract_version": calculation_definition.contract_version,
            "parameters": calculation_definition.parameters,
        }
    return {
        "name": value.name,
        "value": value.value,
        "unit": value.unit,
        "definition_version": value.definition_version,
        "basis": value.basis,
        "sample_size": value.sample_size,
        "annualization_basis": value.annualization_basis,
        "calculation_basis": value.calculation_basis,
        "null_reason": value.null_reason,
        "calculation_definition": calculation_attributes,
        "evidence_references": tuple(
            {"role": item.role, "digest": item.digest} for item in value.evidence_references
        ),
    }


def _normalize_forward_instance(attributes: Mapping[str, Any]) -> ResourceDomainNormalization:
    allowed = {
        "instance_id",
        "portfolio_fingerprint",
        "warmup_snapshot_fingerprint",
        "carry_in_mode",
        "state",
        "last_event_id",
        "last_event_sequence",
        "correction_count",
        "created_at",
        "updated_at",
        "resource_id",
        "id",
    }
    unknown = sorted(set(attributes) - allowed)
    if unknown:
        raise ValueError(
            f"forward_instance attributes contain unsupported fields: {', '.join(unknown)}"
        )
    api_ids = [attributes[name] for name in ("resource_id", "id") if name in attributes]
    if any(not isinstance(value, str) or not value.strip() for value in api_ids):
        raise ValueError("forward_instance resource_id/id must be a non-empty string")
    if len(api_ids) == 2 and api_ids[0] != api_ids[1]:
        raise ValueError("forward_instance resource_id and id must agree")
    last_event_id = attributes.get("last_event_id")
    if last_event_id is not None and (not isinstance(last_event_id, str) or not last_event_id.strip()):
        raise ValueError("forward_instance last_event_id must be a non-empty string when present")
    last_event_sequence = attributes.get("last_event_sequence")
    correction_count = attributes.get("correction_count")
    if not isinstance(last_event_sequence, int) or isinstance(last_event_sequence, bool):
        raise ValueError("forward_instance last_event_sequence must be an integer")
    if not isinstance(correction_count, int) or isinstance(correction_count, bool):
        raise ValueError("forward_instance correction_count must be an integer")
    try:
        instance = ForwardInstance(
            instance_id=attributes["instance_id"],
            portfolio_fingerprint=attributes["portfolio_fingerprint"],
            warmup_snapshot_fingerprint=attributes["warmup_snapshot_fingerprint"],
            carry_in_mode=_enum_attribute(CarryInMode, attributes["carry_in_mode"], "carry_in_mode"),
            state=_enum_attribute(ForwardState, attributes["state"], "forward state"),
            last_event_id=last_event_id,
            last_event_sequence=last_event_sequence,
            correction_count=correction_count,
            created_at=_datetime_attribute(attributes["created_at"], "created_at"),
            updated_at=_datetime_attribute(attributes["updated_at"], "updated_at"),
        )
    except KeyError as error:
        raise ValueError(f"forward_instance attribute is required: {error.args[0]}") from error
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError(f"forward_instance attributes are invalid: {error}") from error

    normalized: dict[str, Any] = {
        "instance_id": instance.instance_id,
        "portfolio_fingerprint": instance.portfolio_fingerprint,
        "warmup_snapshot_fingerprint": instance.warmup_snapshot_fingerprint,
        "carry_in_mode": instance.carry_in_mode,
        "state": instance.state,
        "last_event_id": instance.last_event_id,
        "last_event_sequence": instance.last_event_sequence,
        "correction_count": instance.correction_count,
        "created_at": instance.created_at,
        "updated_at": instance.updated_at,
    }
    if api_ids:
        normalized["resource_id"] = api_ids[0]
    return ResourceDomainNormalization(normalized, content_digest(instance))


def _preflight_report(value: Any) -> PreflightReport:
    if not isinstance(value, Mapping):
        raise ValueError("preflight_report must be a mapping")
    allowed = {"decisions", "fingerprint", "allow_degraded", "degradations"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"preflight_report contains unsupported fields: {', '.join(unknown)}")
    decisions_raw = value.get("decisions")
    if not isinstance(decisions_raw, Sequence) or isinstance(decisions_raw, str | bytes):
        raise ValueError("preflight_report decisions must be a sequence")
    degradations_raw = value.get("degradations", ())
    if not isinstance(degradations_raw, Sequence) or isinstance(degradations_raw, str | bytes):
        raise ValueError("preflight_report degradations must be a sequence")
    return PreflightReport(
        decisions=tuple(_capability_decision(item) for item in decisions_raw),
        fingerprint=value["fingerprint"],
        allow_degraded=value.get("allow_degraded", False),
        degradations=tuple(_degradation(item) for item in degradations_raw),
    )


def _capability_decision(value: Any) -> CapabilityDecision:
    if not isinstance(value, Mapping):
        raise ValueError("preflight decisions must contain mappings")
    allowed = {
        "requirement",
        "classification",
        "evidence_digest",
        "gaps",
        "degradations",
        "ranking_eligible",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"capability decision contains unsupported fields: {', '.join(unknown)}")
    gaps = value.get("gaps", ())
    if not isinstance(gaps, Sequence) or isinstance(gaps, str | bytes):
        raise ValueError("capability decision gaps must be a sequence")
    degradations = value.get("degradations", ())
    if not isinstance(degradations, Sequence) or isinstance(degradations, str | bytes):
        raise ValueError("capability decision degradations must be a sequence")
    try:
        return CapabilityDecision(
            requirement=_capability_requirement(value["requirement"]),
            classification=_enum_attribute(
                PreflightClass, value["classification"], "capability classification"
            ),
            evidence_digest=value.get("evidence_digest"),
            gaps=tuple(gaps),
            degradations=tuple(_degradation(item) for item in degradations),
            ranking_eligible=value["ranking_eligible"],
        )
    except KeyError as error:
        raise ValueError(f"capability decision field is required: {error.args[0]}") from error


def _capability_requirement(value: Any) -> CapabilityRequirement:
    if not isinstance(value, Mapping):
        raise ValueError("capability requirement must be a mapping")
    allowed = {
        "instrument_id",
        "product_class",
        "event_granularity",
        "event_type",
        "timeframe",
        "start",
        "end",
        "adjustment",
        "session",
        "feed",
        "execution_model",
        "account_model",
        "corporate_action_semantics",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"capability requirement contains unsupported fields: {', '.join(unknown)}")
    try:
        return CapabilityRequirement(
            instrument_id=value["instrument_id"],
            product_class=_enum_attribute(ProductClass, value["product_class"], "product_class"),
            event_granularity=_enum_attribute(
                EventGranularity, value["event_granularity"], "event_granularity"
            ),
            event_type=value["event_type"],
            timeframe=value["timeframe"],
            start=_datetime_attribute(value["start"], "requirement start"),
            end=_datetime_attribute(value["end"], "requirement end"),
            adjustment=_enum_attribute(AdjustmentMode, value["adjustment"], "adjustment"),
            session=value["session"],
            feed=value["feed"],
            execution_model=value["execution_model"],
            account_model=value["account_model"],
            corporate_action_semantics=value["corporate_action_semantics"],
        )
    except KeyError as error:
        raise ValueError(f"capability requirement field is required: {error.args[0]}") from error


def _degradation(value: Any) -> Degradation:
    if not isinstance(value, Mapping):
        raise ValueError("degradations must contain mappings")
    allowed = {"instrument_id", "field", "substituted_value", "reason"}
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"degradation contains unsupported fields: {', '.join(unknown)}")
    try:
        return Degradation(
            instrument_id=value["instrument_id"],
            field=value["field"],
            substituted_value=value["substituted_value"],
            reason=value["reason"],
        )
    except KeyError as error:
        raise ValueError(f"degradation field is required: {error.args[0]}") from error


def _data_series_manifest(value: Any) -> DataSeriesManifest:
    if not isinstance(value, Mapping):
        raise ValueError("snapshot series must contain mappings")
    allowed = {
        "instrument_id",
        "event_type",
        "event_granularity",
        "timeframe",
        "session",
        "feed",
        "start",
        "end",
        "adjustment",
        "corporate_action_semantics",
        "coverage_evidence_digest",
        "content_digest",
        "row_count",
    }
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"snapshot series contains unsupported fields: {', '.join(unknown)}")
    try:
        return DataSeriesManifest(
            instrument_id=value["instrument_id"],
            event_type=value["event_type"],
            event_granularity=_enum_attribute(
                EventGranularity, value["event_granularity"], "series event_granularity"
            ),
            timeframe=value["timeframe"],
            session=value["session"],
            feed=value["feed"],
            start=_datetime_attribute(value["start"], "series start"),
            end=_datetime_attribute(value["end"], "series end"),
            adjustment=_enum_attribute(AdjustmentMode, value["adjustment"], "series adjustment"),
            corporate_action_semantics=value["corporate_action_semantics"],
            coverage_evidence_digest=value["coverage_evidence_digest"],
            content_digest=value["content_digest"],
            row_count=value["row_count"],
        )
    except KeyError as error:
        raise ValueError(f"snapshot series field is required: {error.args[0]}") from error


def _preflight_attributes(report: PreflightReport) -> Mapping[str, Any]:
    return {
        "decisions": tuple(_decision_attributes(item) for item in report.decisions),
        "fingerprint": report.fingerprint,
        "allow_degraded": report.allow_degraded,
        "degradations": tuple(_degradation_attributes(item) for item in report.degradations),
    }


def _decision_attributes(decision: CapabilityDecision) -> Mapping[str, Any]:
    requirement = decision.requirement
    return {
        "requirement": {
            "instrument_id": requirement.instrument_id,
            "product_class": requirement.product_class,
            "event_granularity": requirement.event_granularity,
            "event_type": requirement.event_type,
            "timeframe": requirement.timeframe,
            "start": requirement.start,
            "end": requirement.end,
            "adjustment": requirement.adjustment,
            "session": requirement.session,
            "feed": requirement.feed,
            "execution_model": requirement.execution_model,
            "account_model": requirement.account_model,
            "corporate_action_semantics": requirement.corporate_action_semantics,
        },
        "classification": decision.classification,
        "evidence_digest": decision.evidence_digest,
        "gaps": decision.gaps,
        "degradations": tuple(_degradation_attributes(item) for item in decision.degradations),
        "ranking_eligible": decision.ranking_eligible,
    }


def _degradation_attributes(value: Degradation) -> Mapping[str, Any]:
    return {
        "instrument_id": value.instrument_id,
        "field": value.field,
        "substituted_value": value.substituted_value,
        "reason": value.reason,
    }


def _series_attributes(value: DataSeriesManifest) -> Mapping[str, Any]:
    return {
        "instrument_id": value.instrument_id,
        "event_type": value.event_type,
        "event_granularity": value.event_granularity,
        "timeframe": value.timeframe,
        "session": value.session,
        "feed": value.feed,
        "start": value.start,
        "end": value.end,
        "adjustment": value.adjustment,
        "corporate_action_semantics": value.corporate_action_semantics,
        "coverage_evidence_digest": value.coverage_evidence_digest,
        "content_digest": value.content_digest,
        "row_count": value.row_count,
    }


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
