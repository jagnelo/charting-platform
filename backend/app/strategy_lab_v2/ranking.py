"""Deterministic, descriptive ordering of completed Strategy Lab results.

Ranking is an explicit analysis view, not a profitability or statistical
verdict. Results are compared only when their experiment context and metric
calculation identity agree. Degraded preflight results are excluded by default
and can be included only through an explicit caller choice with their label
retained in every entry.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    MetricBasis,
    MetricValue,
    RunResultManifest,
)

RANKING_DEFINITION_VERSION = "strategy-lab.descriptive-ranking.v1"


class RankingDirection(StrEnum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class RankingExclusionReason(StrEnum):
    INELIGIBLE_PREFLIGHT = "ineligible_preflight"
    MISSING_METRIC = "missing_metric"
    NULL_METRIC = "null_metric"
    UNVERSIONED_METRIC = "unversioned_metric"
    INCOMPATIBLE_CONTEXT = "incompatible_context"
    DUPLICATE_TRIAL = "duplicate_trial"


@dataclass(frozen=True, slots=True)
class RankingExclusion:
    trial_id: str
    attempt_id: str
    result_fingerprint: str
    reason: RankingExclusionReason
    detail: str

    def __post_init__(self) -> None:
        require_sha256_digest(self.trial_id, field_name="trial_id")
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        require_sha256_digest(self.result_fingerprint, field_name="result_fingerprint")
        if not isinstance(self.reason, RankingExclusionReason):
            raise TypeError("reason must be a RankingExclusionReason")
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise ValueError("detail must not be empty")


@dataclass(frozen=True, slots=True)
class RankingEntry:
    position: int
    trial_id: str
    attempt_id: str
    result_fingerprint: str
    metric_name: str
    metric_basis: MetricBasis
    value: Decimal
    sample_size: int
    preflight_label: str

    def __post_init__(self) -> None:
        if not isinstance(self.position, int) or isinstance(self.position, bool) or self.position < 1:
            raise ValueError("ranking position must be positive")
        require_sha256_digest(self.trial_id, field_name="trial_id")
        if not isinstance(self.attempt_id, str) or not self.attempt_id.strip():
            raise ValueError("attempt_id must not be empty")
        require_sha256_digest(self.result_fingerprint, field_name="result_fingerprint")
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise ValueError("metric_name must not be empty")
        if not isinstance(self.metric_basis, MetricBasis):
            raise TypeError("metric_basis must be a MetricBasis")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("ranking value must be a finite Decimal")
        if not isinstance(self.sample_size, int) or isinstance(self.sample_size, bool) or self.sample_size < 1:
            raise ValueError("ranking sample_size must be positive")
        if not isinstance(self.preflight_label, str) or not self.preflight_label.strip():
            raise ValueError("preflight_label must not be empty")


@dataclass(frozen=True, slots=True)
class DescriptiveRanking:
    definition_version: str
    experiment_fingerprint: str
    snapshot_fingerprint: str
    portfolio_fingerprint: str
    metric_name: str
    metric_basis: MetricBasis
    metric_calculation_fingerprint: str
    direction: RankingDirection
    include_degraded: bool
    total_results: int
    eligible_results: int
    entries: tuple[RankingEntry, ...]
    exclusions: tuple[RankingExclusion, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.definition_version, str) or not self.definition_version.strip():
            raise ValueError("definition_version must not be empty")
        require_sha256_digest(self.experiment_fingerprint, field_name="experiment_fingerprint")
        require_sha256_digest(self.snapshot_fingerprint, field_name="snapshot_fingerprint")
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        require_sha256_digest(
            self.metric_calculation_fingerprint,
            field_name="metric_calculation_fingerprint",
        )
        if not isinstance(self.direction, RankingDirection):
            raise TypeError("direction must be a RankingDirection")
        if not isinstance(self.metric_name, str) or not self.metric_name.strip():
            raise ValueError("metric_name must not be empty")
        if not isinstance(self.metric_basis, MetricBasis):
            raise TypeError("metric_basis must be a MetricBasis")
        if not isinstance(self.include_degraded, bool):
            raise TypeError("include_degraded must be a bool")
        if not isinstance(self.total_results, int) or isinstance(self.total_results, bool) or self.total_results < 1:
            raise ValueError("total_results must be positive")
        if not isinstance(self.eligible_results, int) or isinstance(self.eligible_results, bool) or self.eligible_results < 0:
            raise ValueError("eligible_results must be non-negative")
        entries = tuple(self.entries)
        exclusions = tuple(self.exclusions)
        if any(not isinstance(item, RankingEntry) for item in entries):
            raise TypeError("entries must contain RankingEntry values")
        if any(not isinstance(item, RankingExclusion) for item in exclusions):
            raise TypeError("exclusions must contain RankingExclusion values")
        if tuple(item.position for item in entries) != tuple(range(1, len(entries) + 1)):
            raise ValueError("ranking entry positions must be contiguous")
        if self.eligible_results != len(entries):
            raise ValueError("eligible_results must match the number of entries")
        if self.total_results != len(entries) + len(exclusions):
            raise ValueError("total_results must equal entries plus exclusions")
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "exclusions", exclusions)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def _metric(result: RunResultManifest, name: str, basis: MetricBasis) -> MetricValue | None:
    values = tuple(
        item for item in result.metric_set.values if item.name == name and item.basis is basis
    )
    if len(values) > 1:
        raise ValueError("metric set contains duplicate ranking metric values")
    return values[0] if values else None


def _context_key(result: RunResultManifest) -> tuple[str, str, str, str, str]:
    return (
        result.snapshot_fingerprint,
        result.portfolio_fingerprint,
        result.engine_build_digest,
        result.allocation_definition_version,
        result.metric_definition_version,
    )


def descriptive_rank_results(
    results: Iterable[RunResultManifest],
    *,
    metric_name: str,
    metric_basis: MetricBasis = MetricBasis.NET,
    direction: RankingDirection = RankingDirection.MAXIMIZE,
    include_degraded: bool = False,
) -> DescriptiveRanking:
    """Order compatible completed results by one finite metric value.

    The first result establishes experiment/context identity and the requested
    metric's unit. Incompatible entries are explicitly excluded rather than
    coerced. Ties use the immutable trial id as a deterministic tie-breaker and
    receive distinct ordinal positions.
    """

    if not isinstance(metric_name, str) or not metric_name.strip():
        raise ValueError("metric_name must not be empty")
    if not isinstance(metric_basis, MetricBasis):
        raise TypeError("metric_basis must be a MetricBasis")
    if not isinstance(direction, RankingDirection):
        raise TypeError("direction must be a RankingDirection")
    if not isinstance(include_degraded, bool):
        raise TypeError("include_degraded must be a bool")
    ordered_results = tuple(results)
    if not ordered_results:
        raise ValueError("ranking requires at least one result")
    if any(not isinstance(item, RunResultManifest) for item in ordered_results):
        raise TypeError("results must contain RunResultManifest values")
    experiment_fingerprint = ordered_results[0].experiment_fingerprint
    for result in ordered_results[1:]:
        if result.experiment_fingerprint != experiment_fingerprint:
            raise ValueError("ranking results must belong to one experiment")

    baseline_result: RunResultManifest | None = None
    baseline_metric: MetricValue | None = None
    for result in ordered_results:
        metric = _metric(result, metric_name, metric_basis)
        if metric is not None and metric.calculation_fingerprint is not None:
            baseline_result = result
            baseline_metric = metric
            break
    if baseline_metric is None or baseline_metric.calculation_fingerprint is None:
        raise ValueError("the ranking metric requires a structured calculation definition")
    if baseline_result is None:  # pragma: no cover - guarded by the metric check above
        raise ValueError("the ranking metric requires a baseline result")
    baseline_context = _context_key(baseline_result)
    baseline_calculation = baseline_metric.calculation_fingerprint
    baseline_unit = baseline_metric.unit

    entries: list[RankingEntry] = []
    exclusions: list[RankingExclusion] = []
    seen_trials: set[str] = set()
    for result in ordered_results:
        if result.trial_id in seen_trials:
            exclusions.append(
                RankingExclusion(
                    result.trial_id,
                    result.attempt_id,
                    result.fingerprint,
                    RankingExclusionReason.DUPLICATE_TRIAL,
                    "multiple successful attempts cannot rank one scientific trial twice",
                )
            )
            continue
        seen_trials.add(result.trial_id)
        if not include_degraded and not result.trial.ranking_eligible:
            exclusions.append(
                RankingExclusion(
                    result.trial_id,
                    result.attempt_id,
                    result.fingerprint,
                    RankingExclusionReason.INELIGIBLE_PREFLIGHT,
                    "degraded or unsupported preflight is excluded by default",
                )
            )
            continue
        if _context_key(result) != baseline_context:
            exclusions.append(
                RankingExclusion(
                    result.trial_id,
                    result.attempt_id,
                    result.fingerprint,
                    RankingExclusionReason.INCOMPATIBLE_CONTEXT,
                    "snapshot, portfolio, engine, allocation, metric-set, or unit context differs",
                )
            )
            continue
        metric = _metric(result, metric_name, metric_basis)
        if metric is None:
            exclusions.append(
                RankingExclusion(
                    result.trial_id,
                    result.attempt_id,
                    result.fingerprint,
                    RankingExclusionReason.MISSING_METRIC,
                    "requested metric and basis are absent",
                )
            )
            continue
        if metric.value is None:
            exclusions.append(
                RankingExclusion(
                    result.trial_id,
                    result.attempt_id,
                    result.fingerprint,
                    RankingExclusionReason.NULL_METRIC,
                    metric.null_reason or "metric value is unavailable",
                )
            )
            continue
        if metric.unit != baseline_unit:
            exclusions.append(
                RankingExclusion(
                    result.trial_id,
                    result.attempt_id,
                    result.fingerprint,
                    RankingExclusionReason.INCOMPATIBLE_CONTEXT,
                    "metric unit differs from the ranking baseline",
                )
            )
            continue
        if metric.calculation_fingerprint != baseline_calculation:
            exclusions.append(
                RankingExclusion(
                    result.trial_id,
                    result.attempt_id,
                    result.fingerprint,
                    RankingExclusionReason.UNVERSIONED_METRIC,
                    "metric calculation identity differs from the ranking baseline",
                )
            )
            continue
        entries.append(
            RankingEntry(
                position=1,
                trial_id=result.trial_id,
                attempt_id=result.attempt_id,
                result_fingerprint=result.fingerprint,
                metric_name=metric.name,
                metric_basis=metric.basis,
                value=metric.value,
                sample_size=metric.sample_size,
                preflight_label=result.trial.preflight_label,
            )
        )

    entries.sort(
        key=lambda item: (
            -item.value if direction is RankingDirection.MAXIMIZE else item.value,
            item.trial_id,
        )
    )
    numbered = tuple(
        RankingEntry(
            position=index,
            trial_id=item.trial_id,
            attempt_id=item.attempt_id,
            result_fingerprint=item.result_fingerprint,
            metric_name=item.metric_name,
            metric_basis=item.metric_basis,
            value=item.value,
            sample_size=item.sample_size,
            preflight_label=item.preflight_label,
        )
        for index, item in enumerate(entries, start=1)
    )
    exclusions.sort(key=lambda item: (item.trial_id, item.attempt_id, item.reason.value))
    return DescriptiveRanking(
        definition_version=RANKING_DEFINITION_VERSION,
        experiment_fingerprint=experiment_fingerprint,
        snapshot_fingerprint=baseline_context[0],
        portfolio_fingerprint=baseline_context[1],
        metric_name=metric_name,
        metric_basis=metric_basis,
        metric_calculation_fingerprint=baseline_calculation,
        direction=direction,
        include_degraded=include_degraded,
        total_results=len(ordered_results),
        eligible_results=len(numbered),
        entries=numbered,
        exclusions=tuple(exclusions),
    )
