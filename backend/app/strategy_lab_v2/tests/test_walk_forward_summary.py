from __future__ import annotations

from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    MetricBasis,
    MetricCalculationDefinition,
    MetricValue,
)
from app.strategy_lab_v2.tests.test_walk_forward_search import _fixtures, _scores
from app.strategy_lab_v2.walk_forward_search import (
    WalkForwardOosResult,
    select_walk_forward_oos_tasks,
)
from app.strategy_lab_v2.walk_forward_summary import build_walk_forward_oos_summary


def _summary_fixture():
    folds, _candidate_fingerprints, plan = _fixtures()
    selection = select_walk_forward_oos_tasks(
        plan,
        folds,
        _scores(plan, {fold.fold_index: fold.fold_index % 3 for fold in folds}),
    )
    results = tuple(
        WalkForwardOosResult(
            task.fingerprint,
            content_digest({"oos-result": task.fold_index}),
            plan.metric_id,
            Decimal(task.fold_index + 1),
        )
        for task in reversed(selection.oos_tasks)
    )
    calculation = MetricCalculationDefinition(
        "native.net_return",
        "strategy-lab.metric-calculation.v1",
        {"basis": "net"},
    )
    source_metrics = tuple(
        MetricValue(
            name=plan.metric_id,
            value=Decimal(task.fold_index + 1),
            unit="fraction",
            definition_version="strategy-lab.metrics.v2",
            basis=MetricBasis.NET,
            sample_size=2,
            calculation_basis="native_equity_curve",
            calculation_definition=calculation,
        )
        for task in selection.oos_tasks
    )

    return build_walk_forward_oos_summary(
        experiment_fingerprint=plan.experiment_fingerprint,
        definition_fingerprint=content_digest("walk-forward-definition"),
        selection=selection,
        results=results,
        source_metrics=source_metrics,
    )


def test_oos_summary_computes_versioned_fold_distribution_with_exact_evidence() -> None:
    summary = _summary_fixture()
    folds = summary.selection.oos_tasks

    assert tuple(result.oos_task_fingerprint for result in summary.results) == tuple(
        task.fingerprint for task in summary.selection.oos_tasks
    )
    statistics = {metric.name.rsplit("__", 1)[0]: metric for metric in summary.aggregate_metrics}
    assert statistics["oos_fold_mean"].value == Decimal(len(folds) + 1) / Decimal(2)
    assert statistics["oos_fold_median"].value == Decimal(len(folds) + 1) / Decimal(2)
    assert abs(
        statistics["oos_fold_population_stddev"].value - Decimal("1.118033988749895")
    ) < Decimal("1e-15")
    assert statistics["oos_fold_minimum"].value == Decimal("1")
    assert statistics["oos_fold_maximum"].value == Decimal(len(folds))
    assert all(metric.sample_size == len(folds) for metric in summary.aggregate_metrics)
    assert all(
        len(metric.evidence_references) == len(folds) for metric in summary.aggregate_metrics
    )


def test_oos_summary_fails_closed_on_incompatible_metric_units() -> None:
    folds, _candidate_fingerprints, plan = _fixtures()
    selection = select_walk_forward_oos_tasks(
        plan, folds, _scores(plan, {0: 0, 1: 1, 2: 2, 3: 0, 4: 1})
    )
    results = tuple(
        WalkForwardOosResult(
            task.fingerprint,
            content_digest({"oos-result": task.fold_index}),
            plan.metric_id,
            Decimal("0.1"),
        )
        for task in selection.oos_tasks
    )
    source_metrics = tuple(
        MetricValue(
            name=plan.metric_id,
            value=result.value,
            unit="fraction" if index == 0 else "percent",
            definition_version="strategy-lab.metrics.v2",
            basis=MetricBasis.NET,
            sample_size=2,
        )
        for index, result in enumerate(results)
    )

    with pytest.raises(ValueError, match="definitions or values are inconsistent"):
        build_walk_forward_oos_summary(
            experiment_fingerprint=plan.experiment_fingerprint,
            definition_fingerprint=content_digest("walk-forward-definition"),
            selection=selection,
            results=results,
            source_metrics=source_metrics,
        )
