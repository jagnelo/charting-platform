from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    preflight_capabilities,
)
from app.strategy_lab_v2.conformance import (
    EngineReleaseChannel,
    NautilusReleasePin,
    NautilusResultProvenance,
)
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    ArtifactManifest,
    AttemptState,
    DataSeriesManifest,
    DataSnapshot,
    EvaluationWindow,
    EventGranularity,
    MetricBasis,
    MetricSet,
    MetricValue,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    RunAttempt,
    RunResultManifest,
    ScientificTrial,
    StrategyPackage,
    StrategyPackageFormat,
    StrategyVersion,
)
from app.strategy_lab_v2.experiments import (
    WalkForwardMode,
    WalkForwardSpec,
    build_walk_forward_folds,
)
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchStateDecision,
    record_search_candidate_terminal,
    start_search_candidate,
)
from app.strategy_lab_v2.walk_forward_queue import (
    WalkForwardQueueResultEvidence,
    append_selected_oos_queue,
    initialize_walk_forward_training_queue,
    oos_results_from_search_queue,
    training_scores_from_search_queue,
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
    oos_result_from_manifest,
    training_score_from_result_manifest,
    verify_walk_forward_result_binding,
)

_START = datetime(2024, 1, 1, tzinfo=UTC)
_END = _START + timedelta(days=365)
_EVIDENCE = content_digest("provider evidence")
_NAUTILUS_PIN = NautilusReleasePin(
    package_version="2.0.0rc5",
    release_tag="v2.0.0rc5",
    source_digest=content_digest("nautilus source"),
    wheel_digest=content_digest("nautilus wheel"),
    runtime_image_digest=content_digest("nautilus runtime image"),
    python_version="3.12.4",
    rust_version="1.88.0",
    legacy_runtime_isolated=True,
)


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
    report = preflight_capabilities((requirement,), (cell,))
    snapshot = DataSnapshot(
        snapshot_id="walk-forward-snapshot",
        provider_snapshot_id="provider-walk-forward-snapshot",
        preflight_report=report,
        series=(
            DataSeriesManifest(
                instrument_id="US.AAPL",
                event_type="ohlcv",
                event_granularity=EventGranularity.BAR,
                timeframe="1d",
                session="regular",
                feed="consolidated",
                start=_START,
                end=_END,
                adjustment=AdjustmentMode.SPLIT_ADJUSTED,
                corporate_action_semantics="split-adjusted-v1",
                coverage_evidence_digest=_EVIDENCE,
                content_digest=content_digest("walk-forward-series"),
                row_count=252,
            ),
        ),
        created_at=_START,
    )
    return ScientificTrial.create(
        experiment_fingerprint=experiment,
        snapshot_fingerprint=snapshot.fingerprint,
        preflight_report=report,
        parameter_set={"candidate": index},
        seed=index + 11,
    )


def _authoritative_result(
    trial: ScientificTrial,
    metric_id: str,
    value: Decimal,
    *,
    attempt_id: str | None = None,
):
    strategy = StrategyVersion(
        "walk-forward-strategy",
        "v1",
        "2.0",
        content_digest("walk-forward-strategy-source"),
    )

    package = StrategyPackage(
        "walk-forward-package",
        strategy.fingerprint,
        StrategyPackageFormat.WHEEL,
        content_digest("package archive"),
        content_digest("package manifest"),
        content_digest("package lock"),
        128,
        "strategy:run",
        "2.0",
        "cp312",
    )
    portfolio = PortfolioComposition(
        "walk-forward-portfolio",
        "v1",
        Decimal("100000"),
        "USD",
        (PortfolioComponent("component-1", strategy.fingerprint, ("US.AAPL",), Decimal(1)),),
    )
    snapshot = DataSnapshot(
        snapshot_id="walk-forward-snapshot",
        provider_snapshot_id="provider-walk-forward-snapshot",
        preflight_report=trial.preflight_report,
        series=(
            DataSeriesManifest(
                instrument_id="US.AAPL",
                event_type="ohlcv",
                event_granularity=EventGranularity.BAR,
                timeframe="1d",
                session="regular",
                feed="consolidated",
                start=_START,
                end=_END,
                adjustment=AdjustmentMode.SPLIT_ADJUSTED,
                corporate_action_semantics="split-adjusted-v1",
                coverage_evidence_digest=_EVIDENCE,
                content_digest=content_digest("walk-forward-series"),
                row_count=252,
            ),
        ),
        created_at=_START,
    )
    attempt = RunAttempt(
        attempt_id or f"walk-forward-{trial.trial_id}",
        trial.trial_id,
        1,
        AttemptState.SUCCEEDED,
        _START,
    )
    metric = MetricValue(
        metric_id,
        value,
        "fraction",
        "strategy-lab.metrics.v2",
        MetricBasis.NET,
        100,
    )
    metric_set = MetricSet(
        "walk-forward-metrics",
        trial.trial_id,
        attempt.attempt_id,
        "strategy-lab.metrics.v2",
        (metric,),
        _START,
    )
    artifact_digest = content_digest("walk-forward-output")
    return RunResultManifest(
        trial=trial,
        attempt=attempt,
        strategy_packages=(package,),
        portfolio=portfolio,
        snapshot=snapshot,
        engine_name="nautilus",
        engine_version=_NAUTILUS_PIN.package_version,
        engine_build_digest=_NAUTILUS_PIN.runtime_image_digest,
        allocation_definition_version="allocation.v1",
        dependency_catalog_digest=content_digest("dependency catalog"),
        assumptions_digest=content_digest("execution assumptions"),
        metric_set=metric_set,
        output_artifacts=(
            ArtifactManifest(
                artifact_digest,
                128,
                "application/vnd.apache.parquet",
                "1",
                artifact_digest,
            ),
        ),
        created_at=_START,
        engine_authoritative=True,
        engine_provenance=NautilusResultProvenance(
            _NAUTILUS_PIN,
            EngineReleaseChannel.RELEASE_CANDIDATE,
            content_digest("conformance evidence"),
            content_digest("conformance report"),
            content_digest("execution plan"),
            "backtest_authoritative",
        ),
    )


def _complete_training_queue(plan, training_trials, queue_bindings, state):
    trial_by_id = {trial.trial_id: trial for trial in training_trials.trials}
    results_by_attempt = {}
    for index, candidate in enumerate(state.candidates):
        attempt_id = f"walk-forward-queue-attempt-{index}"
        result_fingerprint = content_digest({"queue-result": index})
        trial = trial_by_id[candidate.trial_fingerprint]
        result = _authoritative_result(
            trial,
            plan.metric_id,
            Decimal(int(trial.parameter_set["candidate"]) + 1),
            attempt_id=attempt_id,
        )
        results_by_attempt[attempt_id] = WalkForwardQueueResultEvidence(
            result_fingerprint,
            result,
        )
        started = start_search_candidate(
            state,
            index,
            attempt_id=attempt_id,
            now=_START + timedelta(seconds=index * 2 + 1),
        )
        completed = record_search_candidate_terminal(
            started.state,
            index,
            attempt_id=attempt_id,
            phase=SearchCandidatePhase.SUCCEEDED,
            now=_START + timedelta(seconds=index * 2 + 2),
            result_fingerprint=result_fingerprint,
        )
        state = completed.state
    scores = training_scores_from_search_queue(
        plan,
        training_trials,
        queue_bindings,
        state,
        results_by_attempt,
    )
    return state, results_by_attempt, scores


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


def test_training_and_oos_scores_can_only_be_derived_from_exact_authoritative_manifests() -> None:
    folds, _candidate_fingerprints, initial_plan = _fixtures()
    candidates = tuple(_candidate(initial_plan.experiment_fingerprint, index) for index in range(3))
    plan = build_walk_forward_training_plan(
        initial_plan.experiment_fingerprint,
        tuple(candidate.trial_id for candidate in candidates),
        folds,
        metric_id="net_return",
        direction=SelectionDirection.MAXIMIZE,
    )
    boundaries = tuple(_START + timedelta(days=index) for index in range(13))
    training = materialize_walk_forward_training_trials(plan, candidates, folds, boundaries)
    training_binding = training.bindings[0]
    training_result = _authoritative_result(training.trials[0], "net_return", Decimal("0.2"))

    score = training_score_from_result_manifest(
        training_binding,
        training_result,
        metric_id="net_return",
    )

    assert score.training_task_fingerprint == training_binding.task_fingerprint
    assert score.value == Decimal("0.2")
    assert score.result_fingerprint == training_result.fingerprint
    with pytest.raises(ValueError, match="differs from the exact"):
        training_score_from_result_manifest(
            training_binding,
            _authoritative_result(training.trials[1], "net_return", Decimal("0.3")),
            metric_id="net_return",
        )
    with pytest.raises(ValueError, match="authoritative Nautilus"):
        training_score_from_result_manifest(
            training_binding,
            replace(training_result, engine_authoritative=False),
            metric_id="net_return",
        )

    selection = select_walk_forward_oos_tasks(
        plan,
        folds,
        _scores(plan, {fold.fold_index: 0 for fold in folds}),
    )
    oos = materialize_walk_forward_oos_trials(selection, candidates, folds, boundaries)
    oos_result = _authoritative_result(oos.trials[0], "net_return", Decimal("0.1"))
    receipt = oos_result_from_manifest(oos.bindings[0], oos_result, metric_id="net_return")

    assert receipt.oos_task_fingerprint == oos.bindings[0].task_fingerprint
    assert receipt.value == Decimal("0.1")
    assert receipt.result_fingerprint == oos_result.fingerprint
    with pytest.raises(ValueError, match="purpose must be out_of_sample"):
        oos_result_from_manifest(training_binding, oos_result, metric_id="net_return")


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


def test_walk_forward_phases_flatten_into_one_resumable_search_queue() -> None:
    folds, _candidate_fingerprints, initial_plan = _fixtures()
    candidates = tuple(_candidate(initial_plan.experiment_fingerprint, index) for index in range(3))
    plan = build_walk_forward_training_plan(
        initial_plan.experiment_fingerprint,
        tuple(candidate.trial_id for candidate in candidates),
        folds,
        metric_id="net_return",
        direction=SelectionDirection.MAXIMIZE,
    )
    boundaries = tuple(_START + timedelta(days=index) for index in range(13))
    training = materialize_walk_forward_training_trials(plan, candidates, folds, boundaries)
    state, training_bindings = initialize_walk_forward_training_queue(plan, training, now=_START)
    state, training_results, scores = _complete_training_queue(
        plan, training, training_bindings, state
    )
    selection = select_walk_forward_oos_tasks(plan, folds, scores)
    oos = materialize_walk_forward_oos_trials(selection, candidates, folds, boundaries)

    waiting = append_selected_oos_queue(
        initialize_walk_forward_training_queue(plan, training, now=_START)[0],
        plan,
        folds,
        training,
        training_bindings,
        training_results,
        selection,
        oos,
        now=_START + timedelta(days=1),
    )
    assert waiting.resolution.decision is SearchStateDecision.REJECT
    assert "must succeed" in (waiting.resolution.rejection_reason or "")

    appended = append_selected_oos_queue(
        state,
        plan,
        folds,
        training,
        training_bindings,
        training_results,
        selection,
        oos,
        now=_START + timedelta(days=3),
    )

    assert appended.resolution.decision is SearchStateDecision.APPLY
    assert appended.resolution.state.experiment_fingerprint == plan.experiment_fingerprint
    training_trial_count = len({binding.trial_fingerprint for binding in training_bindings})
    assert len(appended.resolution.state.candidates) == training_trial_count + len(folds)
    assert tuple(binding.candidate_index for binding in appended.oos_task_bindings) == tuple(
        range(training_trial_count, training_trial_count + len(folds))
    )
    assert tuple(
        candidate.trial_fingerprint for candidate in appended.resolution.state.candidates
    ) == (
        *dict.fromkeys(trial.trial_id for trial in training.trials),
        *(trial.trial_id for trial in oos.trials),
    )

    replay = append_selected_oos_queue(
        appended.resolution.state,
        plan,
        folds,
        training,
        training_bindings,
        training_results,
        selection,
        oos,
        now=_START + timedelta(days=4),
    )
    assert replay.resolution.decision is SearchStateDecision.REPLAY_EXISTING
    assert replay.resolution.state == appended.resolution.state


def test_training_scores_rehydrate_from_search_attempts_and_exact_result_manifests() -> None:
    folds, _candidate_fingerprints, initial_plan = _fixtures()
    candidates = tuple(_candidate(initial_plan.experiment_fingerprint, index) for index in range(3))
    plan = build_walk_forward_training_plan(
        initial_plan.experiment_fingerprint,
        tuple(candidate.trial_id for candidate in candidates),
        folds,
        metric_id="net_return",
        direction=SelectionDirection.MAXIMIZE,
    )
    boundaries = tuple(_START + timedelta(days=index) for index in range(13))
    training = materialize_walk_forward_training_trials(plan, candidates, folds, boundaries)
    state, queue_bindings = initialize_walk_forward_training_queue(plan, training, now=_START)
    trial_by_id = {trial.trial_id: trial for trial in training.trials}
    results_by_attempt: dict[str, WalkForwardQueueResultEvidence] = {}
    search_result_fingerprints: dict[str, str] = {}

    for candidate_index, candidate_state in enumerate(state.candidates):
        attempt_id = f"walk-forward-attempt-{candidate_index}"
        search_result_fingerprint = content_digest({"search-result": candidate_index})
        search_result_fingerprints[attempt_id] = search_result_fingerprint
        result = _authoritative_result(
            trial_by_id[candidate_state.trial_fingerprint],
            "net_return",
            Decimal(candidate_index + 1),
            attempt_id=attempt_id,
        )
        results_by_attempt[attempt_id] = WalkForwardQueueResultEvidence(
            search_result_fingerprint,
            result,
        )
        started = start_search_candidate(
            state,
            candidate_index,
            attempt_id=attempt_id,
            now=_START + timedelta(seconds=candidate_index + 1),
        )
        terminal = record_search_candidate_terminal(
            started.state,
            candidate_index,
            attempt_id=attempt_id,
            phase=SearchCandidatePhase.SUCCEEDED,
            result_fingerprint=search_result_fingerprint,
            now=_START + timedelta(seconds=candidate_index + 2),
        )
        state = terminal.state

    scores = training_scores_from_search_queue(
        plan,
        training,
        queue_bindings,
        state,
        results_by_attempt,
    )

    assert tuple(score.training_task_fingerprint for score in scores) == tuple(
        task.fingerprint for task in plan.tasks
    )
    assert tuple(score.value for score in scores) == tuple(
        Decimal(
            int(
                results_by_attempt[
                    state.candidates[binding.candidate_index].attempt_id  # type: ignore[index]
                ].manifest.trial.parameter_set["candidate"]
            )
            + 1
        )
        for binding in queue_bindings
    )

    first_attempt = state.candidates[0].attempt_id
    assert first_attempt is not None
    rebound = dict(results_by_attempt)
    rebound[first_attempt] = WalkForwardQueueResultEvidence(
        search_result_fingerprints[first_attempt],
        results_by_attempt[state.candidates[1].attempt_id].manifest,  # type: ignore[index]
    )
    with pytest.raises(ValueError, match="persisted search receipt"):
        training_scores_from_search_queue(plan, training, queue_bindings, state, rebound)


def test_oos_results_rehydrate_only_selected_suffix_attempts_and_exact_manifests() -> None:
    folds, _candidate_fingerprints, initial_plan = _fixtures()
    candidates = tuple(_candidate(initial_plan.experiment_fingerprint, index) for index in range(3))
    plan = build_walk_forward_training_plan(
        initial_plan.experiment_fingerprint,
        tuple(candidate.trial_id for candidate in candidates),
        folds,
        metric_id="net_return",
        direction=SelectionDirection.MAXIMIZE,
    )
    boundaries = tuple(_START + timedelta(days=index) for index in range(13))
    training = materialize_walk_forward_training_trials(plan, candidates, folds, boundaries)
    state, training_bindings = initialize_walk_forward_training_queue(plan, training, now=_START)
    state, training_results, scores = _complete_training_queue(
        plan, training, training_bindings, state
    )
    selection = select_walk_forward_oos_tasks(plan, folds, scores)
    oos = materialize_walk_forward_oos_trials(selection, candidates, folds, boundaries)
    transition = append_selected_oos_queue(
        state,
        plan,
        folds,
        training,
        training_bindings,
        training_results,
        selection,
        oos,
        now=_START + timedelta(days=3),
    )
    state = transition.resolution.state
    results_by_attempt: dict[str, WalkForwardQueueResultEvidence] = {}
    trial_by_id = {trial.trial_id: trial for trial in oos.trials}
    expected_values: list[Decimal] = []
    for offset, binding in enumerate(transition.oos_task_bindings):
        attempt_id = f"walk-forward-oos-attempt-{offset}"
        result_fingerprint = content_digest({"oos-search-result": offset})
        value = Decimal(offset + 10)
        result = _authoritative_result(
            trial_by_id[binding.trial_fingerprint],
            "net_return",
            value,
            attempt_id=attempt_id,
        )
        results_by_attempt[attempt_id] = WalkForwardQueueResultEvidence(result_fingerprint, result)
        started = start_search_candidate(
            state,
            binding.candidate_index,
            attempt_id=attempt_id,
            now=_START + timedelta(days=4, seconds=offset),
        )
        terminal = record_search_candidate_terminal(
            started.state,
            binding.candidate_index,
            attempt_id=attempt_id,
            phase=SearchCandidatePhase.SUCCEEDED,
            result_fingerprint=result_fingerprint,
            now=_START + timedelta(days=4, seconds=offset + 1),
        )
        state = terminal.state
        expected_values.append(value)

    receipts = oos_results_from_search_queue(
        plan,
        selection,
        training_bindings,
        oos,
        transition.oos_task_bindings,
        state,
        results_by_attempt,
    )

    assert tuple(receipt.value for receipt in receipts) == tuple(expected_values)
    assert tuple(receipt.oos_task_fingerprint for receipt in receipts) == tuple(
        task.fingerprint for task in selection.oos_tasks
    )
    with pytest.raises(ValueError, match="exactly cover selected successful attempts"):
        oos_results_from_search_queue(
            plan,
            selection,
            training_bindings,
            oos,
            transition.oos_task_bindings,
            state,
            {**results_by_attempt, **training_results},
        )
    first_attempt = state.candidates[transition.oos_task_bindings[0].candidate_index].attempt_id
    assert first_attempt is not None
    rebound = dict(results_by_attempt)
    rebound[first_attempt] = WalkForwardQueueResultEvidence(
        results_by_attempt[first_attempt].search_result_fingerprint,
        next(iter(training_results.values())).manifest,
    )
    with pytest.raises(ValueError, match="persisted search receipt"):
        oos_results_from_search_queue(
            plan,
            selection,
            training_bindings,
            oos,
            transition.oos_task_bindings,
            state,
            rebound,
        )


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
