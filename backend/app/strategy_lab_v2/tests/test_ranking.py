from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import Degradation, preflight_capabilities
from app.strategy_lab_v2.contracts import (
    AttemptState,
    MetricBasis,
    MetricCalculationDefinition,
    MetricSet,
    MetricValue,
    RunAttempt,
    ScientificTrial,
)
from app.strategy_lab_v2.ranking import (
    RankingDirection,
    RankingExclusionReason,
    descriptive_rank_results,
)
from app.strategy_lab_v2.tests.test_core import _cell, _requirement
from app.strategy_lab_v2.tests.test_result_publication import _result

CALCULATION = MetricCalculationDefinition(
    "simple-return",
    "strategy-lab.metric-calculation.v1",
    {"annualization": "none"},
)


def _rankable_result(
    value: str,
    *,
    parameter: int,
    attempt_id: str,
    base=None,
    experiment_fingerprint: str | None = None,
):
    result = base or _result()[0]
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment_fingerprint or result.experiment_fingerprint,
        snapshot_fingerprint=result.snapshot_fingerprint,
        preflight_report=result.trial.preflight_report,
        parameter_set={"lookback": parameter},
        seed=parameter,
    )
    attempt = RunAttempt(attempt_id, trial.trial_id, 1, AttemptState.SUCCEEDED, result.attempt.created_at)
    metric = MetricValue(
        "return",
        Decimal(value),
        "fraction",
        result.metric_set.definition_version,
        MetricBasis.NET,
        10,
        calculation_definition=CALCULATION,
    )
    metrics = MetricSet(
        f"metrics-{attempt_id}",
        trial.trial_id,
        attempt_id,
        result.metric_set.definition_version,
        (metric,),
        result.metric_set.created_at,
    )
    return replace(result, trial=trial, attempt=attempt, metric_set=metrics)


def _null_result(base):
    metric = MetricValue(
        "return",
        None,
        "fraction",
        base.metric_set.definition_version,
        MetricBasis.NET,
        0,
        null_reason="insufficient observations",
        calculation_definition=CALCULATION,
    )
    metrics = replace(base.metric_set, values=(metric,))
    return replace(base, metric_set=metrics)


def _unversioned_result(base):
    metric = replace(base.metric_set.values[0], calculation_definition=None)
    return replace(base, metric_set=replace(base.metric_set, values=(metric,)))


def _missing_result(base):
    metric = MetricValue(
        "other-metric",
        Decimal("1"),
        "fraction",
        base.metric_set.definition_version,
        MetricBasis.NET,
        10,
        calculation_definition=CALCULATION,
    )
    return replace(base, metric_set=replace(base.metric_set, values=(metric,)))


def test_descriptive_ranking_is_deterministic_and_directional() -> None:
    first = _rankable_result("0.10", parameter=1, attempt_id="attempt-a")
    second = _rankable_result("0.25", parameter=2, attempt_id="attempt-b")
    ranking = descriptive_rank_results(
        (first, second), metric_name="return", direction=RankingDirection.MAXIMIZE
    )

    assert ranking.eligible_results == 2
    assert [entry.value for entry in ranking.entries] == [Decimal("0.25"), Decimal("0.10")]
    assert ranking.entries[0].position == 1
    assert ranking.entries[0].preflight_label == "rigorous"
    assert ranking.fingerprint == descriptive_rank_results(
        (second, first), metric_name="return", direction=RankingDirection.MAXIMIZE
    ).fingerprint
    minimum = descriptive_rank_results(
        (first, second), metric_name="return", direction=RankingDirection.MINIMIZE
    )
    assert [entry.value for entry in minimum.entries] == [Decimal("0.10"), Decimal("0.25")]


def test_degraded_results_are_excluded_by_default_and_labeled_when_explicitly_included() -> None:
    rigorous = _rankable_result("0.10", parameter=1, attempt_id="attempt-rigorous")
    degradation = (Degradation("US.AAPL", "session", "regular", "extended unavailable"),)
    degraded_report = preflight_capabilities(
        (_requirement(session="extended"),),
        (_cell(),),
        allow_degraded=True,
        degradations=degradation,
    )
    degraded_snapshot = replace(rigorous.snapshot, preflight_report=degraded_report)
    degraded_trial = ScientificTrial.create(
        experiment_fingerprint=rigorous.experiment_fingerprint,
        snapshot_fingerprint=degraded_snapshot.fingerprint,
        preflight_report=degraded_report,
        parameter_set={"lookback": 2},
        seed=2,
    )
    degraded_attempt = RunAttempt("attempt-degraded", degraded_trial.trial_id, 1, AttemptState.SUCCEEDED, rigorous.attempt.created_at)
    degraded_metric = MetricValue(
        "return", Decimal("0.50"), "fraction", rigorous.metric_set.definition_version,
        MetricBasis.NET, 10, calculation_definition=CALCULATION,
    )
    degraded_metrics = MetricSet(
        "metrics-degraded", degraded_trial.trial_id, degraded_attempt.attempt_id,
        rigorous.metric_set.definition_version, (degraded_metric,), rigorous.metric_set.created_at,
    )
    degraded = replace(
        rigorous,
        snapshot=degraded_snapshot,
        trial=degraded_trial,
        attempt=degraded_attempt,
        metric_set=degraded_metrics,
    )

    ranking = descriptive_rank_results((rigorous, degraded), metric_name="return")
    assert ranking.eligible_results == 1
    assert ranking.exclusions[0].reason is RankingExclusionReason.INELIGIBLE_PREFLIGHT
    assert ranking.exclusions[0].trial_id == degraded.trial_id

    explicit = descriptive_rank_results(
        (degraded,), metric_name="return", include_degraded=True
    )
    assert explicit.eligible_results == 1
    assert explicit.entries[0].preflight_label == "degraded"


def test_missing_null_unversioned_and_incompatible_results_are_explicitly_excluded() -> None:
    valid = _rankable_result("0.10", parameter=1, attempt_id="attempt-valid")
    null = _null_result(_rankable_result("0.20", parameter=2, attempt_id="attempt-null"))
    unversioned = _unversioned_result(_rankable_result("0.30", parameter=3, attempt_id="attempt-unversioned"))
    missing = _missing_result(_rankable_result("0.35", parameter=5, attempt_id="attempt-missing"))
    incompatible = replace(
        _rankable_result("0.40", parameter=4, attempt_id="attempt-incompatible"),
        engine_build_digest=content_digest("other-build"),
    )
    ranking = descriptive_rank_results(
        (valid, null, unversioned, missing, incompatible), metric_name="return"
    )

    assert ranking.eligible_results == 1
    assert {item.reason for item in ranking.exclusions} == {
        RankingExclusionReason.NULL_METRIC,
        RankingExclusionReason.UNVERSIONED_METRIC,
        RankingExclusionReason.MISSING_METRIC,
        RankingExclusionReason.INCOMPATIBLE_CONTEXT,
    }


def test_duplicate_successful_attempts_for_one_trial_do_not_rank_twice() -> None:
    first = _rankable_result("0.10", parameter=1, attempt_id="attempt-one")
    duplicate = replace(
        first,
        attempt=RunAttempt("attempt-two", first.trial_id, 2, AttemptState.SUCCEEDED, first.attempt.created_at),
        metric_set=replace(first.metric_set, metric_set_id="metrics-two", attempt_id="attempt-two"),
    )
    ranking = descriptive_rank_results((first, duplicate), metric_name="return")

    assert ranking.eligible_results == 1
    assert ranking.exclusions[0].reason is RankingExclusionReason.DUPLICATE_TRIAL


def test_ranking_requires_one_experiment_and_structured_metric_definition() -> None:
    first = _rankable_result("0.10", parameter=1, attempt_id="attempt-one")
    second = _rankable_result(
        "0.20",
        parameter=2,
        attempt_id="attempt-two",
        experiment_fingerprint=content_digest("other-experiment"),
    )
    with pytest.raises(ValueError, match="one experiment"):
        descriptive_rank_results((first, second), metric_name="return")
    unversioned = _unversioned_result(first)
    with pytest.raises(ValueError, match="structured calculation"):
        descriptive_rank_results((unversioned,), metric_name="return")
