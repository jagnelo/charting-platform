"""Descriptive, run-scoped one-factor metric comparisons.

These contracts report a compatible metric difference only. They do not rank
strategies, aggregate replicates, or infer statistical significance.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.strategy_lab_v2.canonical import (
    canonical_json,
    content_digest,
    freeze_json,
    require_sha256_digest,
)
from app.strategy_lab_v2.contracts import (
    MetricBasis,
    MetricValue,
    RunResultManifest,
    SensitivityComparisonEvidence,
    SensitivityEvidenceLevel,
)
from app.strategy_lab_v2.decimal_math import deterministic_decimal_math

SENSITIVITY_METRIC_SCOPE_VERSION = "strategy-lab.sensitivity-metric-scope.v1"
SENSITIVITY_METRIC_DELTA_VERSION = "strategy-lab.one-factor-metric-delta.v1"


class MetricDeltaUnavailableReason(StrEnum):
    PARAMETER_KEYS_DIFFER = "parameter_keys_differ"
    NOT_EXACTLY_ONE_FACTOR = "not_exactly_one_factor"
    BASELINE_METRIC_MISSING = "baseline_metric_missing"
    VARIANT_METRIC_MISSING = "variant_metric_missing"
    CALCULATION_IDENTITY_UNAVAILABLE = "calculation_identity_unavailable"
    CALCULATION_IDENTITY_MISMATCH = "calculation_identity_mismatch"
    MEASUREMENT_SCOPE_MISMATCH = "measurement_scope_mismatch"
    METRIC_VALUE_NULL = "metric_value_null"


@dataclass(frozen=True, slots=True)
class SensitivityMetricScope:
    """Typed identity for the common declared data and measurement context.

    Coverage digests identify upstream coverage claims. This projection does
    not authenticate those claims or inspect the referenced evidence document.
    The scenario digest binds the declared scenario; no separate typed
    evaluation-window contract exists in this engine-neutral package yet.
    """

    experiment_fingerprint: str
    snapshot_fingerprint: str
    capability_contract_digest: str
    scenario_fingerprint: str
    portfolio_fingerprint: str
    base_currency: str
    strategy_package_fingerprints: tuple[str, ...]
    engine_name: str
    engine_version: str
    engine_build_digest: str
    allocation_definition_version: str
    dependency_catalog_digest: str
    assumptions_digest: str
    metric_calculation_fingerprint: str
    coverage_evidence_digests: tuple[str, ...]
    session_calendar_evidence_digests: tuple[str, ...]
    contract_version: str = SENSITIVITY_METRIC_SCOPE_VERSION

    def __post_init__(self) -> None:
        for name in (
            "experiment_fingerprint",
            "snapshot_fingerprint",
            "capability_contract_digest",
            "scenario_fingerprint",
            "portfolio_fingerprint",
            "engine_build_digest",
            "dependency_catalog_digest",
            "assumptions_digest",
            "metric_calculation_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in (
            "base_currency",
            "engine_name",
            "engine_version",
            "allocation_definition_version",
            "contract_version",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.base_currency != self.base_currency.upper():
            raise ValueError("base_currency must be normalized to uppercase")
        packages = tuple(self.strategy_package_fingerprints)
        if not packages:
            raise ValueError("measurement scope requires strategy package fingerprints")
        for digest in packages:
            require_sha256_digest(digest, field_name="strategy_package_fingerprint")
        if packages != tuple(sorted(set(packages))):
            raise ValueError("strategy package fingerprints must be unique and sorted")
        coverage = tuple(self.coverage_evidence_digests)
        calendars = tuple(self.session_calendar_evidence_digests)
        for digest in coverage:
            require_sha256_digest(digest, field_name="coverage_evidence_digest")
        for digest in calendars:
            require_sha256_digest(digest, field_name="session_calendar_evidence_digest")
        if coverage != tuple(sorted(coverage)):
            raise ValueError("coverage evidence digests must be sorted")
        if calendars != tuple(sorted(set(calendars))):
            raise ValueError("session calendar evidence digests must be unique and sorted")
        object.__setattr__(self, "strategy_package_fingerprints", packages)
        object.__setattr__(self, "coverage_evidence_digests", coverage)
        object.__setattr__(self, "session_calendar_evidence_digests", calendars)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class MetricParameterChange:
    """The single canonical parameter value changed between two trials."""

    name: str
    baseline_value: Any
    variant_value: Any

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("changed parameter name must not be empty")
        baseline = freeze_json(self.baseline_value)
        variant = freeze_json(self.variant_value)
        if canonical_json(baseline) == canonical_json(variant):
            raise ValueError("changed parameter values must differ canonically")
        object.__setattr__(self, "baseline_value", baseline)
        object.__setattr__(self, "variant_value", variant)


@dataclass(frozen=True, slots=True)
class OneFactorMetricDelta:
    """A signed, descriptive `variant - baseline` metric difference."""

    metric_name: str
    basis: MetricBasis
    unit: str
    parameter_change: MetricParameterChange
    baseline_value: Decimal
    variant_value: Decimal
    delta: Decimal
    baseline_sample_size: int
    variant_sample_size: int
    baseline_trial_id: str
    variant_trial_id: str
    baseline_attempt_id: str
    variant_attempt_id: str
    calculation_fingerprint: str
    measurement_scope: SensitivityMetricScope
    evidence_level: SensitivityEvidenceLevel
    contract_version: str = SENSITIVITY_METRIC_DELTA_VERSION

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        for name in ("metric_name", "unit", "contract_version"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.basis, MetricBasis):
            raise TypeError("basis must be a MetricBasis")
        if not isinstance(self.parameter_change, MetricParameterChange):
            raise TypeError("parameter_change must use MetricParameterChange")
        for name in ("baseline_value", "variant_value", "delta"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")
        if self.delta != self.variant_value - self.baseline_value:
            raise ValueError("delta must equal variant_value minus baseline_value")
        for name in ("baseline_sample_size", "variant_sample_size"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in (
            "baseline_trial_id",
            "variant_trial_id",
            "baseline_attempt_id",
            "variant_attempt_id",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        require_sha256_digest(self.calculation_fingerprint, field_name="calculation_fingerprint")
        if not isinstance(self.measurement_scope, SensitivityMetricScope):
            raise TypeError("measurement_scope must use SensitivityMetricScope")
        if self.measurement_scope.metric_calculation_fingerprint != self.calculation_fingerprint:
            raise ValueError("measurement scope must bind the reported metric calculation")
        if not isinstance(self.evidence_level, SensitivityEvidenceLevel):
            raise TypeError("evidence_level must be a SensitivityEvidenceLevel")

    @property
    def measurement_scope_fingerprint(self) -> str:
        return self.measurement_scope.fingerprint

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class MetricDeltaUnavailable:
    """Explicit reason a requested descriptive metric delta was withheld."""

    reason: MetricDeltaUnavailableReason
    metric_name: str
    basis: MetricBasis
    baseline_trial_id: str
    variant_trial_id: str
    baseline_attempt_id: str
    variant_attempt_id: str
    evidence_level: SensitivityEvidenceLevel
    baseline_null_reason: str | None = None
    variant_null_reason: str | None = None
    baseline_calculation_fingerprint: str | None = None
    variant_calculation_fingerprint: str | None = None
    baseline_measurement_scope_fingerprint: str | None = None
    variant_measurement_scope_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reason, MetricDeltaUnavailableReason):
            raise TypeError("reason must be a MetricDeltaUnavailableReason")
        if not isinstance(self.basis, MetricBasis):
            raise TypeError("basis must be a MetricBasis")
        if not isinstance(self.evidence_level, SensitivityEvidenceLevel):
            raise TypeError("evidence_level must be a SensitivityEvidenceLevel")
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise ValueError("metric_name must not be empty")
        if self.reason is MetricDeltaUnavailableReason.METRIC_VALUE_NULL and not (
            self.baseline_null_reason or self.variant_null_reason
        ):
            raise ValueError("a null metric outcome must retain at least one side's null reason")
        for name in (
            "baseline_trial_id",
            "variant_trial_id",
            "baseline_attempt_id",
            "variant_attempt_id",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        for name in (
            "baseline_calculation_fingerprint",
            "variant_calculation_fingerprint",
            "baseline_measurement_scope_fingerprint",
            "variant_measurement_scope_fingerprint",
        ):
            digest = getattr(self, name)
            if digest is not None:
                require_sha256_digest(digest, field_name=name)
        for name in ("baseline_null_reason", "variant_null_reason"):
            reason = getattr(self, name)
            if reason is not None and (not isinstance(reason, str) or not reason.strip()):
                raise ValueError(f"{name} must not be empty when present")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


MetricDeltaOutcome = OneFactorMetricDelta | MetricDeltaUnavailable


def _metric_by_key(
    values: tuple[MetricValue, ...], metric_name: str, basis: MetricBasis
) -> MetricValue | None:
    return next((item for item in values if item.name == metric_name and item.basis is basis), None)


def _measurement_scope(result: RunResultManifest, metric: MetricValue) -> SensitivityMetricScope:
    calculation_fingerprint = metric.calculation_fingerprint
    if calculation_fingerprint is None:
        raise ValueError("a measurement scope requires a versioned metric calculation")
    return SensitivityMetricScope(
        experiment_fingerprint=result.experiment_fingerprint,
        snapshot_fingerprint=result.snapshot_fingerprint,
        capability_contract_digest=result.capability_contract_digest,
        scenario_fingerprint=content_digest(result.trial.scenario),
        portfolio_fingerprint=result.portfolio_fingerprint,
        base_currency=result.portfolio.base_currency,
        strategy_package_fingerprints=tuple(sorted(result.strategy_package_fingerprints)),
        engine_name=result.engine_name,
        engine_version=result.engine_version,
        engine_build_digest=result.engine_build_digest,
        allocation_definition_version=result.allocation_definition_version,
        dependency_catalog_digest=result.dependency_catalog_digest,
        assumptions_digest=result.assumptions_digest,
        metric_calculation_fingerprint=calculation_fingerprint,
        coverage_evidence_digests=tuple(
            sorted(item.coverage_evidence_digest for item in result.snapshot.series)
        ),
        session_calendar_evidence_digests=tuple(
            sorted(
                {
                    item.digest
                    for item in metric.evidence_references
                    if item.role == "session_calendar"
                }
            )
        ),
    )


def _unavailable(
    evidence: SensitivityComparisonEvidence,
    metric_name: str,
    basis: MetricBasis,
    reason: MetricDeltaUnavailableReason,
    *,
    baseline: MetricValue | None = None,
    variant: MetricValue | None = None,
    baseline_scope: SensitivityMetricScope | None = None,
    variant_scope: SensitivityMetricScope | None = None,
) -> MetricDeltaUnavailable:
    return MetricDeltaUnavailable(
        reason=reason,
        metric_name=metric_name,
        basis=basis,
        baseline_trial_id=evidence.baseline_result.trial_id,
        variant_trial_id=evidence.variant_result.trial_id,
        baseline_attempt_id=evidence.baseline_result.attempt_id,
        variant_attempt_id=evidence.variant_result.attempt_id,
        evidence_level=evidence.evidence_level,
        baseline_null_reason=baseline.null_reason if baseline is not None else None,
        variant_null_reason=variant.null_reason if variant is not None else None,
        baseline_calculation_fingerprint=(
            baseline.calculation_fingerprint if baseline is not None else None
        ),
        variant_calculation_fingerprint=(
            variant.calculation_fingerprint if variant is not None else None
        ),
        baseline_measurement_scope_fingerprint=(
            baseline_scope.fingerprint if baseline_scope is not None else None
        ),
        variant_measurement_scope_fingerprint=(
            variant_scope.fingerprint if variant_scope is not None else None
        ),
    )


@deterministic_decimal_math
def compare_one_factor_metric(
    evidence: SensitivityComparisonEvidence,
    *,
    metric_name: str,
    basis: MetricBasis,
) -> MetricDeltaOutcome:
    """Return a descriptive `variant - baseline` delta or a typed unavailable reason."""

    if not isinstance(evidence, SensitivityComparisonEvidence):
        raise TypeError("evidence must use SensitivityComparisonEvidence")
    if not isinstance(metric_name, str) or not metric_name.strip():
        raise ValueError("metric_name must not be empty")
    if not isinstance(basis, MetricBasis):
        raise TypeError("basis must be a MetricBasis")

    baseline_parameters = evidence.baseline_result.trial.parameter_set
    variant_parameters = evidence.variant_result.trial.parameter_set
    if set(baseline_parameters) != set(variant_parameters):
        return _unavailable(
            evidence,
            metric_name,
            basis,
            MetricDeltaUnavailableReason.PARAMETER_KEYS_DIFFER,
        )
    changed_parameters = tuple(
        name
        for name in baseline_parameters
        if canonical_json(baseline_parameters[name]) != canonical_json(variant_parameters[name])
    )
    if len(changed_parameters) != 1:
        return _unavailable(
            evidence,
            metric_name,
            basis,
            MetricDeltaUnavailableReason.NOT_EXACTLY_ONE_FACTOR,
        )

    baseline = _metric_by_key(evidence.baseline_result.metric_set.values, metric_name, basis)
    variant = _metric_by_key(evidence.variant_result.metric_set.values, metric_name, basis)
    if baseline is None:
        return _unavailable(
            evidence,
            metric_name,
            basis,
            MetricDeltaUnavailableReason.BASELINE_METRIC_MISSING,
            variant=variant,
        )
    if variant is None:
        return _unavailable(
            evidence,
            metric_name,
            basis,
            MetricDeltaUnavailableReason.VARIANT_METRIC_MISSING,
            baseline=baseline,
        )

    baseline_calculation = baseline.calculation_fingerprint
    variant_calculation = variant.calculation_fingerprint
    if baseline_calculation is None or variant_calculation is None:
        return _unavailable(
            evidence,
            metric_name,
            basis,
            MetricDeltaUnavailableReason.CALCULATION_IDENTITY_UNAVAILABLE,
            baseline=baseline,
            variant=variant,
        )
    if baseline_calculation != variant_calculation:
        return _unavailable(
            evidence,
            metric_name,
            basis,
            MetricDeltaUnavailableReason.CALCULATION_IDENTITY_MISMATCH,
            baseline=baseline,
            variant=variant,
        )

    baseline_scope = _measurement_scope(evidence.baseline_result, baseline)
    variant_scope = _measurement_scope(evidence.variant_result, variant)
    if baseline_scope != variant_scope:
        return _unavailable(
            evidence,
            metric_name,
            basis,
            MetricDeltaUnavailableReason.MEASUREMENT_SCOPE_MISMATCH,
            baseline=baseline,
            variant=variant,
            baseline_scope=baseline_scope,
            variant_scope=variant_scope,
        )

    if baseline.value is None or variant.value is None:
        return _unavailable(
            evidence,
            metric_name,
            basis,
            MetricDeltaUnavailableReason.METRIC_VALUE_NULL,
            baseline=baseline,
            variant=variant,
            baseline_scope=baseline_scope,
            variant_scope=variant_scope,
        )

    changed_name = changed_parameters[0]
    return OneFactorMetricDelta(
        metric_name=metric_name,
        basis=basis,
        unit=baseline.unit,
        parameter_change=MetricParameterChange(
            name=changed_name,
            baseline_value=baseline_parameters[changed_name],
            variant_value=variant_parameters[changed_name],
        ),
        baseline_value=baseline.value,
        variant_value=variant.value,
        delta=variant.value - baseline.value,
        baseline_sample_size=baseline.sample_size,
        variant_sample_size=variant.sample_size,
        baseline_trial_id=evidence.baseline_result.trial_id,
        variant_trial_id=evidence.variant_result.trial_id,
        baseline_attempt_id=evidence.baseline_result.attempt_id,
        variant_attempt_id=evidence.variant_result.attempt_id,
        calculation_fingerprint=baseline_calculation,
        measurement_scope=baseline_scope,
        evidence_level=evidence.evidence_level,
    )
