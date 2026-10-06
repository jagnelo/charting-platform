from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    preflight_capabilities,
)
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    EvaluationWindow,
    EventGranularity,
    ProductClass,
    ScientificTrial,
)
from app.strategy_lab_v2.experiments import (
    WalkForwardMode,
    WalkForwardSpec,
    build_walk_forward_folds,
)
from app.strategy_lab_v2.walk_forward_search import (
    SelectionDirection,
    WalkForwardOosResult,
    WalkForwardTrainingScore,
    build_walk_forward_training_plan,
    collect_walk_forward_oos_results,
    select_walk_forward_oos_tasks,
)
from app.strategy_lab_v2.walk_forward_trials import (
    materialize_walk_forward_oos_trials,
    materialize_walk_forward_training_trials,
    verify_walk_forward_result_binding,
)

_START = datetime(2024, 1, 1, tzinfo=UTC)
_END = _START + timedelta(days=365)
_EVIDENCE = content_digest("provider evidence")


def _candidate(experiment: str, index: int) -> ScientificTrial:
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=_START,
        end=_END,
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="regular",
        feed="consolidated",
        execution_model="bar-close-v1",
        account_model="cash-equity-v1",
        corporate_action_semantics="split-adjusted-v1",
    )
    cell = CapabilityCell(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularities=frozenset({EventGranularity.BAR}),
        event_types=frozenset({"ohlcv"}),
        timeframes=frozenset({"1d"}),
        adjustments=frozenset({AdjustmentMode.SPLIT_ADJUSTED}),
        sessions=frozenset({"regular"}),
        feeds=frozenset({"consolidated"}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        corporate_action_semantics=frozenset({"split-adjusted-v1"}),
        history_start=_START,
        history_end=_END,
        evidence_digest=_EVIDENCE,
    )
    return ScientificTrial.create(
        experiment_fingerprint=experiment,
        snapshot_fingerprint=content_digest("snapshot"),
        preflight_report=preflight_capabilities((requirement,), (cell,)),
        parameter_set={"candidate": index},
        seed=index + 11,
    )


def _fixtures():
    folds = build_walk_forward_folds(
        12,
        WalkForwardSpec(
            train_periods=3,
            test_periods=2,
            step_periods=2,
            mode=WalkForwardMode.ROLLING,
        ),
    )
    candidates = tuple(content_digest({"candidate": index}) for index in range(3))
    plan = build_walk_forward_training_plan(
        content_digest("experiment"),
        candidates,
        folds,
        metric_id="net_return",
        direction=SelectionDirection.MAXIMIZE,
    )
    return folds, candidates, plan


def _scores(plan, preferred_by_fold: dict[int, int]):
    scores = []
    for task in plan.tasks:
        preferred = preferred_by_fold[task.fold_index]
        value = Decimal(1) if task.candidate_index == preferred else Decimal(0)
        scores.append(
            WalkForwardTrainingScore(
                task.fingerprint,
                plan.metric_id,
                value,
                content_digest({"result": task.fingerprint}),
            )
        )
    return tuple(scores)


def test_training_plan_contains_only_training_rows_and_selection_is_fold_local() -> None:
    folds, candidates, plan = _fixtures()
    assert len(plan.tasks) == len(folds) * len(candidates)
    for task in plan.tasks:
        assert task.training_indices == folds[task.fold_index].train_indices
        assert not hasattr(task, "test_indices")

    preferred = {fold.fold_index: fold.fold_index % len(candidates) for fold in folds}
    selection = select_walk_forward_oos_tasks(plan, folds, _scores(plan, preferred))

    assert [task.candidate_index for task in selection.oos_tasks] == [
        preferred[fold.fold_index] for fold in folds
    ]
    assert [task.test_indices for task in selection.oos_tasks] == [
        fold.test_indices for fold in folds
    ]
    assert [task.candidate_fingerprint for task in selection.oos_tasks] == [
        candidates[preferred[fold.fold_index]] for fold in folds
    ]


def test_training_trials_bind_exact_fold_time_windows_and_immutable_candidate_inputs() -> None:
    folds, _candidate_fingerprints, plan = _fixtures()
    candidates = tuple(_candidate(plan.experiment_fingerprint, index) for index in range(3))
    plan = build_walk_forward_training_plan(
        plan.experiment_fingerprint,
        tuple(candidate.trial_id for candidate in candidates),
        folds,
        metric_id=plan.metric_id,
        direction=SelectionDirection.MAXIMIZE,
    )
    boundaries = tuple(_START + timedelta(days=index) for index in range(13))

    materialized = materialize_walk_forward_training_trials(plan, candidates, folds, boundaries)

    assert len(materialized.trials) == len(plan.tasks)
    by_task = {
        binding.task_fingerprint: (binding, trial)
        for binding, trial in zip(materialized.bindings, materialized.trials, strict=True)
    }
    for task in plan.tasks:
        binding, trial = by_task[task.fingerprint]
        source = candidates[task.candidate_index]
        fold = folds[task.fold_index]
        assert trial.trial_id == binding.trial_fingerprint
        assert trial.trial_id != source.trial_id
        assert trial.parameter_set == source.parameter_set
        assert trial.seed == source.seed
        assert trial.evaluation_window == EvaluationWindow(
            start=boundaries[fold.train_start],
            end=boundaries[fold.train_end],
            purpose="training",
        )
        assert binding.purpose == "training"


def test_oos_trials_are_only_selected_candidates_and_bind_warmup_and_result_window() -> None:
    folds, _candidate_fingerprints, initial_plan = _fixtures()
    candidates = tuple(_candidate(initial_plan.experiment_fingerprint, index) for index in range(3))
    plan = build_walk_forward_training_plan(
        initial_plan.experiment_fingerprint,
        tuple(candidate.trial_id for candidate in candidates),
        folds,
        metric_id=initial_plan.metric_id,
        direction=SelectionDirection.MAXIMIZE,
    )
    preferred = {fold.fold_index: fold.fold_index % len(candidates) for fold in folds}
    selection = select_walk_forward_oos_tasks(plan, folds, _scores(plan, preferred))
    boundaries = tuple(_START + timedelta(days=index) for index in range(13))

    materialized = materialize_walk_forward_oos_trials(selection, candidates, folds, boundaries)

    assert len(materialized.trials) == len(folds)
    for binding, task, trial, fold in zip(
        materialized.bindings, selection.oos_tasks, materialized.trials, folds, strict=True
    ):
        expected_window = EvaluationWindow(
            start=boundaries[fold.test_start],
            end=boundaries[fold.test_end],
            warmup_start=boundaries[fold.train_start],
            purpose="out_of_sample",
        )
        assert binding.task_fingerprint == task.fingerprint
        assert binding.purpose == "out_of_sample"
        assert trial.parameter_set == candidates[preferred[fold.fold_index]].parameter_set
        assert trial.evaluation_window == expected_window
        verify_walk_forward_result_binding(
            binding,
            trial,
            result_trial_fingerprint=trial.trial_id,
            result_window_fingerprint=expected_window.fingerprint,
        )
        with pytest.raises(ValueError, match="exact walk-forward trial window"):
            verify_walk_forward_result_binding(
                binding,
                trial,
                result_trial_fingerprint=trial.trial_id,
                result_window_fingerprint=content_digest("rebound window"),
            )


def test_walk_forward_trial_materialization_rejects_rebound_candidates_and_bad_boundaries() -> None:
    folds, _candidate_fingerprints, initial_plan = _fixtures()
    candidates = tuple(_candidate(initial_plan.experiment_fingerprint, index) for index in range(3))
    plan = build_walk_forward_training_plan(
        initial_plan.experiment_fingerprint,
        tuple(candidate.trial_id for candidate in candidates),
        folds,
        metric_id=initial_plan.metric_id,
        direction=SelectionDirection.MAXIMIZE,
    )
    boundaries = tuple(_START + timedelta(days=index) for index in range(13))
    with pytest.raises(ValueError, match="candidate trial identities"):
        materialize_walk_forward_training_trials(
            plan, (candidates[1], candidates[0], candidates[2]), folds, boundaries
        )
    with pytest.raises(ValueError, match="cover all planned observations"):
        materialize_walk_forward_training_trials(plan, candidates, folds, boundaries[:11])


def test_training_selection_is_deterministic_and_ties_choose_lowest_candidate_index() -> None:
    folds, _candidates, plan = _fixtures()
    tied = tuple(
        WalkForwardTrainingScore(
            task.fingerprint,
            plan.metric_id,
            Decimal("0.25"),
            content_digest({"tied-result": task.fingerprint}),
        )
        for task in reversed(plan.tasks)
    )

    first = select_walk_forward_oos_tasks(plan, folds, tied)
    replay = select_walk_forward_oos_tasks(plan, folds, tuple(reversed(tied)))

    assert first == replay
    assert all(task.candidate_index == 0 for task in first.oos_tasks)


def test_training_selection_rejects_missing_extra_wrong_metric_or_rebound_evidence() -> None:
    folds, _candidates, plan = _fixtures()
    scores = _scores(plan, {fold.fold_index: 0 for fold in folds})

    with pytest.raises(ValueError, match="exactly cover"):
        select_walk_forward_oos_tasks(plan, folds, scores[:-1])
    with pytest.raises(ValueError, match="unique"):
        select_walk_forward_oos_tasks(plan, folds, (*scores, scores[0]))
    extra = WalkForwardTrainingScore(
        content_digest("unknown-training-task"),
        plan.metric_id,
        Decimal(0),
        content_digest("unknown-training-result"),
    )
    with pytest.raises(ValueError, match="exactly cover"):
        select_walk_forward_oos_tasks(plan, folds, (*scores, extra))
    wrong_metric = (
        WalkForwardTrainingScore(
            scores[0].training_task_fingerprint,
            "gross_return",
            scores[0].value,
            scores[0].result_fingerprint,
        ),
        *scores[1:],
    )
    with pytest.raises(ValueError, match="metric differs"):
        select_walk_forward_oos_tasks(plan, folds, wrong_metric)
    with pytest.raises(ValueError, match="folds differ"):
        select_walk_forward_oos_tasks(plan, folds[:-1], scores)


def test_oos_aggregation_accepts_only_the_selected_fold_tasks() -> None:
    folds, _candidates, plan = _fixtures()
    selection = select_walk_forward_oos_tasks(
        plan,
        folds,
        _scores(plan, {fold.fold_index: 1 for fold in folds}),
    )
    results = tuple(
        WalkForwardOosResult(
            task.fingerprint,
            content_digest({"oos-result": task.fingerprint}),
            plan.metric_id,
            Decimal(task.fold_index),
        )
        for task in reversed(selection.oos_tasks)
    )

    ordered = collect_walk_forward_oos_results(selection, results, metric_id=plan.metric_id)

    assert [result.value for result in ordered] == [
        Decimal(task.fold_index) for task in selection.oos_tasks
    ]
    unselected = WalkForwardOosResult(
        content_digest("not-a-selected-oos-task"),
        content_digest("unselected-result"),
        plan.metric_id,
        Decimal(0),
    )
    with pytest.raises(ValueError, match="exactly cover"):
        collect_walk_forward_oos_results(
            selection,
            (unselected, *results[1:]),
            metric_id=plan.metric_id,
        )
