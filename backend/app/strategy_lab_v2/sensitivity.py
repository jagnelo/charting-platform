"""Descriptive, run-scoped one-factor metric comparisons.

These contracts report a compatible metric difference only. They do not rank
strategies, aggregate replicates, or infer statistical significance.
"""

from __future__ import annotations

from collections.abc import Sequence
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
    TrialSeedPolicy,
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


SENSITIVITY_REPLICATE_SUMMARY_VERSION = "strategy-lab.one-factor-replicate-summary.v1"
DEFAULT_REPLICATE_QUANTILE_PROBABILITIES = (
    Decimal("0.05"),
    Decimal("0.25"),
    Decimal("0.50"),
    Decimal("0.75"),
    Decimal("0.95"),
)


class ReplicateSummaryUnavailableReason(StrEnum):
    """Why a complete one-factor replicate summary was withheld."""

    BASELINE_EMPTY = "baseline_empty"
    VARIANT_EMPTY = "variant_empty"
    DUPLICATE_TRIAL = "duplicate_trial"
    DUPLICATE_ATTEMPT = "duplicate_attempt"
    REPLICATE_COUNT_MISMATCH = "replicate_count_mismatch"
    REPLICATE_INDEX_INCOMPLETE = "replicate_index_incomplete"
    ARM_PARAMETER_INCONSISTENT = "arm_parameter_inconsistent"
    PARAMETER_KEYS_DIFFER = "parameter_keys_differ"
    NOT_EXACTLY_ONE_FACTOR = "not_exactly_one_factor"
    FIXED_CONTEXT_MISMATCH = "fixed_context_mismatch"
    BASELINE_METRIC_MISSING = "baseline_metric_missing"
    VARIANT_METRIC_MISSING = "variant_metric_missing"
    CALCULATION_IDENTITY_UNAVAILABLE = "calculation_identity_unavailable"
    CALCULATION_IDENTITY_MISMATCH = "calculation_identity_mismatch"
    MEASUREMENT_SCOPE_MISMATCH = "measurement_scope_mismatch"
    METRIC_VALUE_NULL = "metric_value_null"


@dataclass(frozen=True, slots=True)
class NearestRankStatistic:
    """One empirical nearest-rank statistic over replicate-level values."""

    probability: Decimal
    value: Decimal

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        if (
            not isinstance(self.probability, Decimal)
            or not self.probability.is_finite()
            or self.probability <= 0
            or self.probability > 1
        ):
            raise ValueError("nearest-rank probability must be finite and in (0, 1]")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("nearest-rank value must be a finite Decimal")


@dataclass(frozen=True, slots=True)
class ReplicateRandomizationSummary:
    """The per-arm seed provenance retained by a replicate summary."""

    replicate_count: int
    replicate_indices: tuple[int, ...]
    master_seeds: tuple[int, ...]
    seeds: tuple[int, ...]
    policies: tuple[TrialSeedPolicy, ...]
    scope_fingerprints: tuple[str | None, ...]
    seed_group_fingerprints: tuple[str | None, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.replicate_count, int)
            or isinstance(self.replicate_count, bool)
            or self.replicate_count < 1
        ):
            raise ValueError("replicate_count must be a positive integer")
        fields = (
            self.replicate_indices,
            self.master_seeds,
            self.seeds,
            self.policies,
            self.scope_fingerprints,
            self.seed_group_fingerprints,
        )
        if any(len(field) != self.replicate_count for field in fields):
            raise ValueError("randomization provenance fields must match replicate_count")
        indices = tuple(self.replicate_indices)
        if indices != tuple(range(self.replicate_count)):
            raise ValueError("replicate indices must cover every planned index exactly once")
        if any(
            not isinstance(value, int) or isinstance(value, bool)
            for value in (*self.master_seeds, *self.seeds)
        ):
            raise ValueError("randomization seeds must be integers")
        policies = tuple(self.policies)
        if any(not isinstance(value, TrialSeedPolicy) for value in policies):
            raise TypeError("randomization policies must use TrialSeedPolicy")
        scopes = tuple(self.scope_fingerprints)
        groups = tuple(self.seed_group_fingerprints)
        for digest in (*scopes, *groups):
            if digest is not None:
                require_sha256_digest(digest, field_name="randomization provenance digest")
        for policy, scope, group in zip(policies, scopes, groups, strict=True):
            if policy is TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE and (
                scope is None or group is None
            ):
                raise ValueError("shared-seed provenance requires scope and seed-group digests")
        object.__setattr__(self, "replicate_indices", indices)
        object.__setattr__(self, "master_seeds", tuple(self.master_seeds))
        object.__setattr__(self, "seeds", tuple(self.seeds))
        object.__setattr__(self, "policies", policies)
        object.__setattr__(self, "scope_fingerprints", scopes)
        object.__setattr__(self, "seed_group_fingerprints", groups)

    @property
    def has_shared_seed_provenance(self) -> bool:
        return all(
            policy is TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE for policy in self.policies
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ReplicateMetricStatistics:
    """Descriptive statistics over one complete arm of metric replicates."""

    metric_name: str
    basis: MetricBasis
    unit: str
    replicate_count: int
    observation_sample_sizes: tuple[int, ...]
    mean: Decimal
    median: Decimal
    minimum: Decimal
    maximum: Decimal
    nearest_rank_statistics: tuple[NearestRankStatistic, ...]
    randomization: ReplicateRandomizationSummary

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        for name in ("metric_name", "unit"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.basis, MetricBasis):
            raise TypeError("basis must be a MetricBasis")
        if (
            not isinstance(self.replicate_count, int)
            or isinstance(self.replicate_count, bool)
            or self.replicate_count < 1
        ):
            raise ValueError("replicate_count must be a positive integer")
        sample_sizes = tuple(self.observation_sample_sizes)
        if len(sample_sizes) != self.replicate_count or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in sample_sizes
        ):
            raise ValueError("observation sample sizes must match the replicate count")
        for name in ("mean", "median", "minimum", "maximum"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be a finite Decimal")
        if self.minimum > self.maximum or not self.minimum <= self.median <= self.maximum:
            raise ValueError("median must lie between the replicate minimum and maximum")
        nearest = tuple(self.nearest_rank_statistics)
        if any(not isinstance(item, NearestRankStatistic) for item in nearest):
            raise TypeError("nearest-rank statistics must use NearestRankStatistic")
        if tuple(item.probability for item in nearest) != tuple(
            sorted({item.probability for item in nearest})
        ):
            raise ValueError("nearest-rank probabilities must be unique and sorted")
        if not isinstance(self.randomization, ReplicateRandomizationSummary):
            raise TypeError("randomization must use ReplicateRandomizationSummary")
        if self.randomization.replicate_count != self.replicate_count:
            raise ValueError("randomization provenance must match the metric replicate count")
        object.__setattr__(self, "observation_sample_sizes", sample_sizes)
        object.__setattr__(self, "nearest_rank_statistics", nearest)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    @property
    def sample_size(self) -> int:
        """Number of complete replicate observations summarized by this arm."""

        return self.replicate_count

    @property
    def quantiles(self) -> tuple[NearestRankStatistic, ...]:
        """Compatibility alias for the configured nearest-rank statistics."""

        return self.nearest_rank_statistics


@dataclass(frozen=True, slots=True)
class OneFactorReplicateMetricSummary:
    """Descriptive baseline/variant replicate summary; never an inferential result."""

    metric_name: str
    basis: MetricBasis
    unit: str
    parameter_change: MetricParameterChange
    baseline: ReplicateMetricStatistics
    variant: ReplicateMetricStatistics
    mean_delta: Decimal
    calculation_fingerprint: str
    measurement_scope: SensitivityMetricScope
    baseline_trial_ids: tuple[str, ...]
    variant_trial_ids: tuple[str, ...]
    baseline_attempt_ids: tuple[str, ...]
    variant_attempt_ids: tuple[str, ...]
    evidence_level: SensitivityEvidenceLevel
    contract_version: str = SENSITIVITY_REPLICATE_SUMMARY_VERSION

    @deterministic_decimal_math
    def __post_init__(self) -> None:
        for name in ("metric_name", "unit", "contract_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.basis, MetricBasis):
            raise TypeError("basis must be a MetricBasis")
        if not isinstance(self.parameter_change, MetricParameterChange):
            raise TypeError("parameter_change must use MetricParameterChange")
        if not isinstance(self.baseline, ReplicateMetricStatistics) or not isinstance(
            self.variant, ReplicateMetricStatistics
        ):
            raise TypeError("replicate summary arms must use ReplicateMetricStatistics")
        if (self.baseline.metric_name, self.baseline.basis, self.baseline.unit) != (
            self.metric_name,
            self.basis,
            self.unit,
        ) or (self.variant.metric_name, self.variant.basis, self.variant.unit) != (
            self.metric_name,
            self.basis,
            self.unit,
        ):
            raise ValueError("replicate summary arms must bind the requested metric")
        if not isinstance(self.mean_delta, Decimal) or not self.mean_delta.is_finite():
            raise ValueError("mean_delta must be a finite Decimal")
        if self.mean_delta != self.variant.mean - self.baseline.mean:
            raise ValueError("mean_delta must equal variant mean minus baseline mean")
        require_sha256_digest(self.calculation_fingerprint, field_name="calculation_fingerprint")
        if not isinstance(self.measurement_scope, SensitivityMetricScope):
            raise TypeError("measurement_scope must use SensitivityMetricScope")
        if self.measurement_scope.metric_calculation_fingerprint != self.calculation_fingerprint:
            raise ValueError("measurement scope must bind the reported metric calculation")
        if not isinstance(self.evidence_level, SensitivityEvidenceLevel):
            raise TypeError("evidence_level must be a SensitivityEvidenceLevel")
        ids = (
            ("baseline_trial_ids", self.baseline_trial_ids, self.baseline.replicate_count),
            ("variant_trial_ids", self.variant_trial_ids, self.variant.replicate_count),
            ("baseline_attempt_ids", self.baseline_attempt_ids, self.baseline.replicate_count),
            ("variant_attempt_ids", self.variant_attempt_ids, self.variant.replicate_count),
        )
        for name, values, expected in ids:
            values = tuple(values)
            if (
                len(values) != expected
                or len(set(values)) != len(values)
                or any(not isinstance(value, str) or not value.strip() for value in values)
            ):
                raise ValueError(f"{name} must contain unique ids for every replicate")
            object.__setattr__(self, name, values)

    @property
    def baseline_randomization(self) -> ReplicateRandomizationSummary:
        return self.baseline.randomization

    @property
    def variant_randomization(self) -> ReplicateRandomizationSummary:
        return self.variant.randomization

    @property
    def delta(self) -> Decimal:
        """Compatibility alias for the descriptive difference of arm means."""

        return self.mean_delta

    @property
    def baseline_statistics(self) -> ReplicateMetricStatistics:
        return self.baseline

    @property
    def variant_statistics(self) -> ReplicateMetricStatistics:
        return self.variant

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ReplicateMetricSummaryUnavailable:
    """Typed fail-closed outcome for an invalid or incomplete replicate group."""

    reason: ReplicateSummaryUnavailableReason
    metric_name: str
    basis: MetricBasis
    baseline_trial_ids: tuple[str, ...] = ()
    variant_trial_ids: tuple[str, ...] = ()
    baseline_attempt_ids: tuple[str, ...] = ()
    variant_attempt_ids: tuple[str, ...] = ()
    baseline_null_reasons: tuple[str, ...] = ()
    variant_null_reasons: tuple[str, ...] = ()
    detail: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reason, ReplicateSummaryUnavailableReason):
            raise TypeError("reason must be a ReplicateSummaryUnavailableReason")
        if not isinstance(self.basis, MetricBasis):
            raise TypeError("basis must be a MetricBasis")
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise ValueError("metric_name must not be empty")
        for name in (
            "baseline_trial_ids",
            "variant_trial_ids",
            "baseline_attempt_ids",
            "variant_attempt_ids",
        ):
            values = tuple(getattr(self, name))
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{name} must contain non-empty strings")
            object.__setattr__(self, name, values)
        for name in ("baseline_null_reasons", "variant_null_reasons"):
            values = tuple(getattr(self, name))
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{name} must contain non-empty strings")
            object.__setattr__(self, name, values)
        if self.detail is not None and (
            not isinstance(self.detail, str) or not self.detail.strip()
        ):
            raise ValueError("detail must not be blank when present")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


ReplicateMetricSummaryOutcome = OneFactorReplicateMetricSummary | ReplicateMetricSummaryUnavailable
ReplicateSummaryUnavailable = ReplicateMetricSummaryUnavailable
ReplicateSummaryOutcome = ReplicateMetricSummaryOutcome


def _replicate_unavailable(
    reason: ReplicateSummaryUnavailableReason,
    metric_name: str,
    basis: MetricBasis,
    baseline: Sequence[RunResultManifest],
    variant: Sequence[RunResultManifest],
    *,
    baseline_null_reasons: Sequence[str] = (),
    variant_null_reasons: Sequence[str] = (),
    detail: str | None = None,
) -> ReplicateMetricSummaryUnavailable:
    return ReplicateMetricSummaryUnavailable(
        reason=reason,
        metric_name=metric_name,
        basis=basis,
        baseline_trial_ids=tuple(item.trial_id for item in baseline),
        variant_trial_ids=tuple(item.trial_id for item in variant),
        baseline_attempt_ids=tuple(item.attempt_id for item in baseline),
        variant_attempt_ids=tuple(item.attempt_id for item in variant),
        baseline_null_reasons=tuple(baseline_null_reasons),
        variant_null_reasons=tuple(variant_null_reasons),
        detail=detail,
    )


def _validate_replicate_arm(
    results: Sequence[RunResultManifest],
) -> ReplicateSummaryUnavailableReason | None:
    if len({item.trial_id for item in results}) != len(results):
        return ReplicateSummaryUnavailableReason.DUPLICATE_TRIAL
    if len({item.attempt_id for item in results}) != len(results):
        return ReplicateSummaryUnavailableReason.DUPLICATE_ATTEMPT
    counts = {item.trial.randomization.replicate_count for item in results}
    if len(counts) != 1:
        return ReplicateSummaryUnavailableReason.REPLICATE_COUNT_MISMATCH
    count = next(iter(counts))
    indices = tuple(item.trial.randomization.replicate_index for item in results)
    if len(set(indices)) != len(indices) or tuple(sorted(indices)) != tuple(range(count)):
        return ReplicateSummaryUnavailableReason.REPLICATE_INDEX_INCOMPLETE
    return None


def _ordered_replicates(results: Sequence[RunResultManifest]) -> tuple[RunResultManifest, ...]:
    return tuple(sorted(results, key=lambda item: item.trial.randomization.replicate_index))


def _consistent_parameter_set(
    results: Sequence[RunResultManifest],
) -> tuple[str, dict[str, Any]] | None:
    first = results[0].trial.parameter_set
    first_key = canonical_json(first)
    if any(canonical_json(item.trial.parameter_set) != first_key for item in results[1:]):
        return None
    return first_key, dict(first)


def _fixed_execution_context(result: RunResultManifest) -> tuple[Any, ...]:
    return (
        result.experiment_fingerprint,
        result.snapshot_fingerprint,
        result.capability_contract_digest,
        canonical_json(result.trial.scenario),
        result.portfolio_fingerprint,
        result.strategy_package_fingerprints,
        result.engine_name,
        result.engine_version,
        result.engine_build_digest,
        result.allocation_definition_version,
        result.dependency_catalog_digest,
        result.assumptions_digest,
    )


def _randomization_summary(
    results: Sequence[RunResultManifest],
) -> ReplicateRandomizationSummary:
    ordered = _ordered_replicates(results)
    assignments = tuple(item.trial.randomization for item in ordered)
    return ReplicateRandomizationSummary(
        replicate_count=len(assignments),
        replicate_indices=tuple(item.replicate_index for item in assignments),
        master_seeds=tuple(item.master_seed for item in assignments),
        seeds=tuple(item.seed for item in assignments),
        policies=tuple(item.policy for item in assignments),
        scope_fingerprints=tuple(item.scope_fingerprint for item in assignments),
        seed_group_fingerprints=tuple(item.seed_group_fingerprint for item in assignments),
    )


def _replicate_evidence_level(
    baseline: Sequence[RunResultManifest], variant: Sequence[RunResultManifest]
) -> SensitivityEvidenceLevel:
    for left, right in zip(
        _ordered_replicates(baseline), _ordered_replicates(variant), strict=True
    ):
        left_assignment = left.trial.randomization
        right_assignment = right.trial.randomization
        if not (
            left_assignment.policy is TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE
            and right_assignment.policy is TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE
            and left_assignment.master_seed == right_assignment.master_seed
            and left_assignment.seed == right_assignment.seed
            and left_assignment.scope_fingerprint == right_assignment.scope_fingerprint
            and left_assignment.seed_group_fingerprint == right_assignment.seed_group_fingerprint
            and left_assignment.replicate_index == right_assignment.replicate_index
            and left_assignment.replicate_count == right_assignment.replicate_count
        ):
            return SensitivityEvidenceLevel.UNPAIRED
    return SensitivityEvidenceLevel.SHARED_SEED_ONLY


def _validate_quantile_probabilities(
    probabilities: Sequence[Decimal],
) -> tuple[Decimal, ...]:
    values = tuple(probabilities)
    if not values or any(
        not isinstance(value, Decimal) or not value.is_finite() or value <= 0 or value > 1
        for value in values
    ):
        raise ValueError("quantile_probabilities must contain finite Decimal values in (0, 1]")
    if len(set(values)) != len(values):
        raise ValueError("quantile_probabilities must not contain duplicates")
    return tuple(sorted(values))


def _nearest_rank(values: Sequence[Decimal], probability: Decimal) -> Decimal:
    numerator, denominator = probability.as_integer_ratio()
    rank = (len(values) * numerator + denominator - 1) // denominator
    return sorted(values)[rank - 1]


@deterministic_decimal_math
def _replicate_statistics(
    results: Sequence[RunResultManifest],
    metrics: Sequence[MetricValue],
    *,
    metric_name: str,
    basis: MetricBasis,
    quantile_probabilities: Sequence[Decimal],
) -> ReplicateMetricStatistics:
    values = tuple(item.value for item in metrics)
    if any(value is None for value in values):
        raise ValueError("replicate statistics require non-null metric values")
    finite_values = tuple(value for value in values if value is not None)
    ordered_values = tuple(sorted(finite_values))
    return ReplicateMetricStatistics(
        metric_name=metric_name,
        basis=basis,
        unit=metrics[0].unit,
        replicate_count=len(results),
        observation_sample_sizes=tuple(item.sample_size for item in metrics),
        mean=sum(finite_values, Decimal(0)) / Decimal(len(finite_values)),
        median=_nearest_rank(ordered_values, Decimal("0.5")),
        minimum=ordered_values[0],
        maximum=ordered_values[-1],
        nearest_rank_statistics=tuple(
            NearestRankStatistic(
                probability=probability,
                value=_nearest_rank(ordered_values, probability),
            )
            for probability in quantile_probabilities
        ),
        randomization=_randomization_summary(results),
    )


@deterministic_decimal_math
def summarize_one_factor_metric_replicates(
    baseline_results: Sequence[RunResultManifest],
    variant_results: Sequence[RunResultManifest],
    *,
    metric_name: str,
    basis: MetricBasis,
    quantile_probabilities: Sequence[Decimal] = DEFAULT_REPLICATE_QUANTILE_PROBABILITIES,
) -> ReplicateMetricSummaryOutcome:
    """Summarize complete one-factor replicate arms descriptively.

    A summary is emitted only when each arm contains every planned replicate
    exactly once and all fixed execution/metric measurement context agrees.
    The returned mean difference is descriptive (`variant - baseline`); no
    ranking, significance, confidence interval, independence, or pairing claim
    is made.
    """

    if not isinstance(metric_name, str) or not metric_name.strip():
        raise ValueError("metric_name must not be empty")
    if not isinstance(basis, MetricBasis):
        raise TypeError("basis must be a MetricBasis")
    probabilities = _validate_quantile_probabilities(quantile_probabilities)
    baseline = tuple(baseline_results)
    variant = tuple(variant_results)
    if not baseline:
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.BASELINE_EMPTY,
            metric_name,
            basis,
            baseline,
            variant,
        )
    if not variant:
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.VARIANT_EMPTY,
            metric_name,
            basis,
            baseline,
            variant,
        )
    if any(not isinstance(item, RunResultManifest) for item in (*baseline, *variant)):
        raise TypeError("replicate results must use RunResultManifest values")

    for arm in (baseline, variant):
        reason = _validate_replicate_arm(arm)
        if reason is not None:
            return _replicate_unavailable(reason, metric_name, basis, baseline, variant)
    baseline_count = baseline[0].trial.randomization.replicate_count
    variant_count = variant[0].trial.randomization.replicate_count
    if baseline_count != variant_count:
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.REPLICATE_COUNT_MISMATCH,
            metric_name,
            basis,
            baseline,
            variant,
        )

    ordered_baseline = _ordered_replicates(baseline)
    ordered_variant = _ordered_replicates(variant)
    baseline_parameters = _consistent_parameter_set(ordered_baseline)
    variant_parameters = _consistent_parameter_set(ordered_variant)
    if baseline_parameters is None or variant_parameters is None:
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.ARM_PARAMETER_INCONSISTENT,
            metric_name,
            basis,
            baseline,
            variant,
        )
    baseline_key, baseline_parameter_values = baseline_parameters
    variant_key, variant_parameter_values = variant_parameters
    if set(baseline_parameter_values) != set(variant_parameter_values):
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.PARAMETER_KEYS_DIFFER,
            metric_name,
            basis,
            baseline,
            variant,
        )
    changed_parameters = tuple(
        name
        for name in baseline_parameter_values
        if canonical_json(baseline_parameter_values[name])
        != canonical_json(variant_parameter_values[name])
    )
    if len(changed_parameters) != 1:
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.NOT_EXACTLY_ONE_FACTOR,
            metric_name,
            basis,
            baseline,
            variant,
        )
    if len({_fixed_execution_context(item) for item in (*ordered_baseline, *ordered_variant)}) != 1:
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.FIXED_CONTEXT_MISMATCH,
            metric_name,
            basis,
            baseline,
            variant,
        )

    baseline_metrics = tuple(
        _metric_by_key(item.metric_set.values, metric_name, basis) for item in ordered_baseline
    )
    variant_metrics = tuple(
        _metric_by_key(item.metric_set.values, metric_name, basis) for item in ordered_variant
    )
    if any(item is None for item in baseline_metrics):
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.BASELINE_METRIC_MISSING,
            metric_name,
            basis,
            baseline,
            variant,
        )
    if any(item is None for item in variant_metrics):
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.VARIANT_METRIC_MISSING,
            metric_name,
            basis,
            baseline,
            variant,
        )
    baseline_metric_values = tuple(item for item in baseline_metrics if item is not None)
    variant_metric_values = tuple(item for item in variant_metrics if item is not None)
    all_metrics = (*baseline_metric_values, *variant_metric_values)
    calculations = tuple(item.calculation_fingerprint for item in all_metrics)
    if any(value is None for value in calculations):
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.CALCULATION_IDENTITY_UNAVAILABLE,
            metric_name,
            basis,
            baseline,
            variant,
        )
    calculation_fingerprints = tuple(value for value in calculations if value is not None)
    if len(set(calculation_fingerprints)) != 1:
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.CALCULATION_IDENTITY_MISMATCH,
            metric_name,
            basis,
            baseline,
            variant,
        )
    calculation_fingerprint = calculation_fingerprints[0]
    scopes = tuple(
        _measurement_scope(result, metric)
        for result, metric in zip((*ordered_baseline, *ordered_variant), all_metrics, strict=True)
    )
    if len(set(scopes)) != 1:
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.MEASUREMENT_SCOPE_MISMATCH,
            metric_name,
            basis,
            baseline,
            variant,
        )
    null_baseline = tuple(item.null_reason for item in baseline_metric_values if item.value is None)
    null_variant = tuple(item.null_reason for item in variant_metric_values if item.value is None)
    if null_baseline or null_variant:
        return _replicate_unavailable(
            ReplicateSummaryUnavailableReason.METRIC_VALUE_NULL,
            metric_name,
            basis,
            baseline,
            variant,
            baseline_null_reasons=tuple(value for value in null_baseline if value is not None),
            variant_null_reasons=tuple(value for value in null_variant if value is not None),
        )

    baseline_statistics = _replicate_statistics(
        ordered_baseline,
        baseline_metric_values,
        metric_name=metric_name,
        basis=basis,
        quantile_probabilities=probabilities,
    )
    variant_statistics = _replicate_statistics(
        ordered_variant,
        variant_metric_values,
        metric_name=metric_name,
        basis=basis,
        quantile_probabilities=probabilities,
    )
    return OneFactorReplicateMetricSummary(
        metric_name=metric_name,
        basis=basis,
        unit=baseline_statistics.unit,
        parameter_change=MetricParameterChange(
            name=changed_parameters[0],
            baseline_value=baseline_parameter_values[changed_parameters[0]],
            variant_value=variant_parameter_values[changed_parameters[0]],
        ),
        baseline=baseline_statistics,
        variant=variant_statistics,
        mean_delta=variant_statistics.mean - baseline_statistics.mean,
        calculation_fingerprint=calculation_fingerprint,
        measurement_scope=scopes[0],
        baseline_trial_ids=tuple(item.trial_id for item in ordered_baseline),
        variant_trial_ids=tuple(item.trial_id for item in ordered_variant),
        baseline_attempt_ids=tuple(item.attempt_id for item in ordered_baseline),
        variant_attempt_ids=tuple(item.attempt_id for item in ordered_variant),
        evidence_level=_replicate_evidence_level(ordered_baseline, ordered_variant),
    )


def compare_one_factor_metric_replicates(
    baseline_results: Sequence[RunResultManifest],
    variant_results: Sequence[RunResultManifest],
    *,
    metric_name: str,
    basis: MetricBasis,
    quantile_probabilities: Sequence[Decimal] = DEFAULT_REPLICATE_QUANTILE_PROBABILITIES,
) -> ReplicateMetricSummaryOutcome:
    """Compatibility alias for :func:`summarize_one_factor_metric_replicates`."""

    return summarize_one_factor_metric_replicates(
        baseline_results,
        variant_results,
        metric_name=metric_name,
        basis=basis,
        quantile_probabilities=quantile_probabilities,
    )
