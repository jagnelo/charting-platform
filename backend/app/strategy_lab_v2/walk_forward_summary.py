"""Versioned, evidence-bound descriptive metrics for walk-forward OOS folds."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    MetricCalculationDefinition,
    MetricEvidenceReference,
    MetricValue,
)
from app.strategy_lab_v2.walk_forward_search import (
    WalkForwardOosResult,
    WalkForwardSelection,
    collect_walk_forward_oos_results,
)

WALK_FORWARD_AGGREGATE_DEFINITION = "strategy-lab.walk-forward.fold-distribution.v1"


@dataclass(frozen=True, slots=True)
class WalkForwardOosSummary:
    """Immutable selected-fold receipts and their descriptive metric distribution.

    These statistics describe the distribution of one metric across selected
    OOS folds. They are not portfolio-compounded return, drawdown, or risk-
    adjusted performance; those require the underlying native equity series.
    """

    experiment_fingerprint: str
    definition_fingerprint: str
    selection: WalkForwardSelection
    metric_id: str
    results: tuple[WalkForwardOosResult, ...]
    source_metrics: tuple[MetricValue, ...]
    aggregate_metrics: tuple[MetricValue, ...]

    def __post_init__(self) -> None:
        require_sha256_digest(self.experiment_fingerprint, field_name="experiment_fingerprint")
        require_sha256_digest(self.definition_fingerprint, field_name="definition_fingerprint")
        if not isinstance(self.selection, WalkForwardSelection):
            raise TypeError("selection must be a WalkForwardSelection")
        if not isinstance(self.metric_id, str) or not self.metric_id.strip():
            raise ValueError("metric_id must not be empty")
        results = collect_walk_forward_oos_results(
            self.selection,
            tuple(self.results),
            metric_id=self.metric_id,
        )
        source_metrics = tuple(self.source_metrics)
        aggregate_metrics = tuple(self.aggregate_metrics)
        if len(source_metrics) != len(results) or any(
            not isinstance(metric, MetricValue) for metric in source_metrics
        ):
            raise ValueError("source metrics must cover every selected OOS fold")
        if any(
            metric.name != self.metric_id or metric.value != result.value or metric.sample_size < 1
            for result, metric in zip(results, source_metrics, strict=True)
        ):
            raise ValueError("source metrics differ from the verified OOS fold receipts")
        first = source_metrics[0]
        if any(
            metric.unit != first.unit
            or metric.basis is not first.basis
            or metric.definition_version != first.definition_version
            or metric.calculation_fingerprint != first.calculation_fingerprint
            for metric in source_metrics[1:]
        ):
            raise ValueError("OOS fold metrics do not share comparable definitions and units")
        if tuple(item.name for item in aggregate_metrics) != _statistic_names(self.metric_id):
            raise ValueError("aggregate metrics must contain the exact ordered fold statistics")
        evidence = tuple(
            sorted(
                (
                    MetricEvidenceReference("oos_result_manifest", result.result_fingerprint)
                    for result in results
                ),
                key=lambda item: (item.role, item.digest),
            )
        )
        for statistic, name, value, metric in zip(
            ("mean", "median", "population_stddev", "minimum", "maximum"),
            _statistic_names(self.metric_id),
            _statistics(tuple(result.value for result in results)),
            aggregate_metrics,
            strict=True,
        ):
            expected_calculation = MetricCalculationDefinition(
                formula_id=f"walk_forward.oos_fold.{statistic}",
                contract_version=WALK_FORWARD_AGGREGATE_DEFINITION,
                parameters={
                    "source_metric_id": self.metric_id,
                    "source_calculation_fingerprint": first.calculation_fingerprint,
                    "selection_fingerprint": self.selection.fingerprint,
                    "sample_unit": "fold",
                },
            )
            if (
                metric.name != name
                or metric.value != value
                or metric.unit != first.unit
                or metric.basis is not first.basis
                or metric.definition_version != WALK_FORWARD_AGGREGATE_DEFINITION
                or metric.sample_size != len(results)
                or metric.annualization_basis is not None
                or metric.calculation_basis != "selected_oos_fold_distribution"
                or metric.calculation_definition != expected_calculation
                or metric.null_reason is not None
                or metric.evidence_references != evidence
            ):
                raise ValueError("aggregate metric does not match the selected OOS fold evidence")
        object.__setattr__(self, "results", results)
        object.__setattr__(self, "source_metrics", source_metrics)
        object.__setattr__(self, "aggregate_metrics", aggregate_metrics)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def build_walk_forward_oos_summary(
    *,
    experiment_fingerprint: str,
    definition_fingerprint: str,
    selection: WalkForwardSelection,
    results: tuple[WalkForwardOosResult, ...],
    source_metrics: tuple[MetricValue, ...],
) -> WalkForwardOosSummary:
    """Build deterministic mean/median/deviation/min/max across OOS folds."""

    if not results:
        raise ValueError("OOS summary requires one result per selected fold")
    metric_id = results[0].metric_id
    ordered = collect_walk_forward_oos_results(selection, results, metric_id=metric_id)
    if len(source_metrics) != len(ordered) or not source_metrics:
        raise ValueError("source metrics must cover every selected OOS fold")
    first = source_metrics[0]
    if first.name != metric_id:
        raise ValueError("source metric name differs from the selected OOS metric")
    if any(
        metric.name != metric_id
        or metric.value != result.value
        or metric.unit != first.unit
        or metric.basis is not first.basis
        or metric.definition_version != first.definition_version
        or metric.calculation_fingerprint != first.calculation_fingerprint
        for result, metric in zip(ordered, source_metrics, strict=True)
    ):
        raise ValueError("selected OOS metric definitions or values are inconsistent")
    evidence = tuple(
        sorted(
            (
                MetricEvidenceReference("oos_result_manifest", result.result_fingerprint)
                for result in ordered
            ),
            key=lambda item: (item.role, item.digest),
        )
    )
    statistics = _statistics(tuple(result.value for result in ordered))
    metrics = tuple(
        MetricValue(
            name=name,
            value=value,
            unit=first.unit,
            definition_version=WALK_FORWARD_AGGREGATE_DEFINITION,
            basis=first.basis,
            sample_size=len(ordered),
            calculation_basis="selected_oos_fold_distribution",
            calculation_definition=MetricCalculationDefinition(
                formula_id=f"walk_forward.oos_fold.{statistic}",
                contract_version=WALK_FORWARD_AGGREGATE_DEFINITION,
                parameters={
                    "source_metric_id": metric_id,
                    "source_calculation_fingerprint": first.calculation_fingerprint,
                    "selection_fingerprint": selection.fingerprint,
                    "sample_unit": "fold",
                },
            ),
            evidence_references=evidence,
        )
        for statistic, name, value in zip(
            ("mean", "median", "population_stddev", "minimum", "maximum"),
            _statistic_names(metric_id),
            statistics,
            strict=True,
        )
    )
    return WalkForwardOosSummary(
        experiment_fingerprint=experiment_fingerprint,
        definition_fingerprint=definition_fingerprint,
        selection=selection,
        metric_id=metric_id,
        results=ordered,
        source_metrics=tuple(source_metrics),
        aggregate_metrics=metrics,
    )


def _statistic_names(metric_id: str) -> tuple[str, ...]:
    return tuple(
        f"oos_fold_{statistic}__{metric_id}"
        for statistic in ("mean", "median", "population_stddev", "minimum", "maximum")
    )


def _statistics(values: tuple[Decimal, ...]) -> tuple[Decimal, ...]:
    if not values or any(not value.is_finite() for value in values):
        raise ValueError("OOS fold metrics must be a non-empty set of finite values")
    ordered = tuple(sorted(values))
    count = Decimal(len(values))
    mean = sum(values, Decimal(0)) / count
    midpoint = len(ordered) // 2
    median = (
        ordered[midpoint]
        if len(ordered) % 2
        else (ordered[midpoint - 1] + ordered[midpoint]) / Decimal(2)
    )
    variance = sum(((value - mean) ** 2 for value in values), Decimal(0)) / count
    return mean, median, variance.sqrt(), ordered[0], ordered[-1]


__all__ = [
    "WALK_FORWARD_AGGREGATE_DEFINITION",
    "WalkForwardOosSummary",
    "build_walk_forward_oos_summary",
]
