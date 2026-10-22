"""Materialize immutable fold-local trials for walk-forward search."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    EvaluationWindow,
    MetricValue,
    RunResultManifest,
    ScientificTrial,
)
from app.strategy_lab_v2.experiments import WalkForwardFold
from app.strategy_lab_v2.walk_forward_search import (
    WalkForwardOosResult,
    WalkForwardSelection,
    WalkForwardTrainingPlan,
    WalkForwardTrainingScore,
)


@dataclass(frozen=True, slots=True)
class WalkForwardTrialBinding:
    """Exact planned task-to-trial and evaluation-window association."""

    task_fingerprint: str
    trial_fingerprint: str
    fold_index: int
    candidate_index: int
    purpose: str
    window_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("task_fingerprint", "trial_fingerprint", "window_fingerprint"):
            require_sha256_digest(getattr(self, name), field_name=name)
        if (
            not isinstance(self.fold_index, int)
            or isinstance(self.fold_index, bool)
            or self.fold_index < 0
            or not isinstance(self.candidate_index, int)
            or isinstance(self.candidate_index, bool)
            or self.candidate_index < 0
        ):
            raise ValueError("fold and candidate indices must be non-negative")
        if self.purpose not in {"training", "out_of_sample"}:
            raise ValueError("walk-forward trial purpose must be training or out_of_sample")


@dataclass(frozen=True, slots=True)
class MaterializedWalkForwardTrials:
    """Deterministic task bindings plus the immutable trials they authorize."""

    trials: tuple[ScientificTrial, ...]
    bindings: tuple[WalkForwardTrialBinding, ...]

    def __post_init__(self) -> None:
        if not self.trials or len(self.trials) != len(self.bindings):
            raise ValueError("every walk-forward binding must contain exactly one trial")
        if any(not isinstance(trial, ScientificTrial) for trial in self.trials):
            raise TypeError("walk-forward trials must be ScientificTrial values")
        if any(not isinstance(binding, WalkForwardTrialBinding) for binding in self.bindings):
            raise TypeError("walk-forward bindings must be WalkForwardTrialBinding values")
        if tuple(trial.trial_id for trial in self.trials) != tuple(
            binding.trial_fingerprint for binding in self.bindings
        ):
            raise ValueError("walk-forward bindings must identify their exact ordered trials")
        if len({binding.task_fingerprint for binding in self.bindings}) != len(self.bindings):
            raise ValueError("walk-forward task bindings must be unique")
        if len({binding.purpose for binding in self.bindings}) != 1:
            raise ValueError("one materialized walk-forward set cannot mix evaluation purposes")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def materialize_walk_forward_training_trials(
    plan: WalkForwardTrainingPlan,
    candidates: tuple[ScientificTrial, ...],
    folds: tuple[WalkForwardFold, ...],
    observation_boundaries: tuple[datetime, ...],
) -> MaterializedWalkForwardTrials:
    """Clone each base candidate into its fold's training-only time window.

    Boundaries describe half-open observation intervals: observation ``i`` is
    ``[boundaries[i], boundaries[i + 1])``. Requiring explicit boundaries avoids
    guessing bar duration for the final observation or irregular event series.
    """

    _validate_inputs(plan, candidates, folds, observation_boundaries)
    trials: list[ScientificTrial] = []
    bindings: list[WalkForwardTrialBinding] = []
    for task in plan.tasks:
        candidate = candidates[task.candidate_index]
        fold = folds[task.fold_index]
        start, end = _bounds(fold.train_indices, observation_boundaries)
        window = EvaluationWindow(start=start, end=end, purpose="training")
        trial = _clone_for_window(candidate, window)
        trials.append(trial)
        bindings.append(
            WalkForwardTrialBinding(
                task_fingerprint=task.fingerprint,
                trial_fingerprint=trial.trial_id,
                fold_index=task.fold_index,
                candidate_index=task.candidate_index,
                purpose="training",
                window_fingerprint=window.fingerprint,
            )
        )
    return MaterializedWalkForwardTrials(tuple(trials), tuple(bindings))


def materialize_walk_forward_oos_trials(
    selection: WalkForwardSelection,
    candidates: tuple[ScientificTrial, ...],
    folds: tuple[WalkForwardFold, ...],
    observation_boundaries: tuple[datetime, ...],
) -> MaterializedWalkForwardTrials:
    """Materialize only the per-fold winners, with prior history as warm-up."""

    if not isinstance(selection, WalkForwardSelection):
        raise TypeError("selection must be a WalkForwardSelection")
    if (
        not isinstance(candidates, tuple)
        or not candidates
        or not isinstance(folds, tuple)
        or not folds
    ):
        raise ValueError("OOS materialization requires candidates and folds")
    if any(not isinstance(candidate, ScientificTrial) for candidate in candidates):
        raise TypeError("candidates must contain ScientificTrial values")
    if any(candidate.evaluation_window is not None for candidate in candidates):
        raise ValueError("walk-forward base candidates cannot already have an evaluation window")
    if tuple(task.fold_index for task in selection.oos_tasks) != tuple(range(len(folds))):
        raise ValueError("selection must contain exactly one task for every ordered fold")
    if any(task.candidate_index >= len(candidates) for task in selection.oos_tasks):
        raise ValueError("OOS selection references an unknown candidate")
    _validate_boundaries(folds, observation_boundaries)
    trials: list[ScientificTrial] = []
    bindings: list[WalkForwardTrialBinding] = []
    for task, fold in zip(selection.oos_tasks, folds, strict=True):
        if task.fold_fingerprint != content_digest(fold):
            raise ValueError("OOS selection fold differs from the immutable fold sequence")
        if task.test_indices != fold.test_indices:
            raise ValueError("OOS selection test indices differ from the immutable fold")
        candidate = candidates[task.candidate_index]
        if task.candidate_fingerprint != candidate.trial_id:
            raise ValueError("OOS selection candidate differs from the immutable candidate trial")
        test_start, test_end = _bounds(fold.test_indices, observation_boundaries)
        warmup_start = observation_boundaries[fold.train_indices[0]]
        window = EvaluationWindow(
            start=test_start,
            end=test_end,
            warmup_start=warmup_start,
            purpose="out_of_sample",
        )
        trial = _clone_for_window(candidate, window)
        trials.append(trial)
        bindings.append(
            WalkForwardTrialBinding(
                task_fingerprint=task.fingerprint,
                trial_fingerprint=trial.trial_id,
                fold_index=task.fold_index,
                candidate_index=task.candidate_index,
                purpose="out_of_sample",
                window_fingerprint=window.fingerprint,
            )
        )
    return MaterializedWalkForwardTrials(tuple(trials), tuple(bindings))


def verify_walk_forward_result_binding(
    binding: WalkForwardTrialBinding,
    trial: ScientificTrial,
    *,
    result_trial_fingerprint: str,
    result_window_fingerprint: str,
) -> None:
    """Fail closed unless native result evidence names the exact task trial/window."""

    if not isinstance(binding, WalkForwardTrialBinding):
        raise TypeError("binding must be a WalkForwardTrialBinding")
    if not isinstance(trial, ScientificTrial):
        raise TypeError("trial must be a ScientificTrial")
    window = trial.evaluation_window
    if window is None:
        raise ValueError("walk-forward trial must bind an evaluation window")
    if (
        trial.trial_id != binding.trial_fingerprint
        or result_trial_fingerprint != binding.trial_fingerprint
        or window.fingerprint != binding.window_fingerprint
        or result_window_fingerprint != binding.window_fingerprint
        or window.purpose != binding.purpose
    ):
        raise ValueError("native result evidence differs from the exact walk-forward trial window")


def training_score_from_result_manifest(
    binding: WalkForwardTrialBinding,
    result: RunResultManifest,
    *,
    metric_id: str,
) -> WalkForwardTrainingScore:
    """Extract a training-selection score only from its exact authoritative run."""

    _verify_authoritative_walk_forward_result(binding, result, expected_purpose="training")
    metric = _selection_metric(result, metric_id)
    if metric.value is None:
        raise ValueError("a null metric cannot be used for training selection")
    return WalkForwardTrainingScore(
        training_task_fingerprint=binding.task_fingerprint,
        metric_id=metric_id,
        value=metric.value,
        result_fingerprint=result.fingerprint,
    )


def oos_result_from_manifest(
    binding: WalkForwardTrialBinding,
    result: RunResultManifest,
    *,
    metric_id: str,
) -> WalkForwardOosResult:
    """Extract an OOS receipt only from its exact selected authoritative run."""

    _verify_authoritative_walk_forward_result(binding, result, expected_purpose="out_of_sample")
    metric = _selection_metric(result, metric_id)
    if metric.value is None:
        raise ValueError("a null metric cannot be aggregated as an OOS result")
    return WalkForwardOosResult(
        oos_task_fingerprint=binding.task_fingerprint,
        result_fingerprint=result.fingerprint,
        metric_id=metric_id,
        value=metric.value,
    )


def _verify_authoritative_walk_forward_result(
    binding: WalkForwardTrialBinding,
    result: RunResultManifest,
    *,
    expected_purpose: str,
) -> None:
    if not isinstance(result, RunResultManifest):
        raise TypeError("result must be a RunResultManifest")
    if binding.purpose != expected_purpose:
        raise ValueError(f"result binding purpose must be {expected_purpose}")
    window = result.trial.evaluation_window
    if window is None:
        raise ValueError("walk-forward result trial must bind an evaluation window")
    verify_walk_forward_result_binding(
        binding,
        result.trial,
        result_trial_fingerprint=result.trial_id,
        result_window_fingerprint=window.fingerprint,
    )
    if not result.engine_authoritative or result.engine_name.lower() != "nautilus":
        raise ValueError("walk-forward selection requires an authoritative Nautilus result")


def _selection_metric(result: RunResultManifest, metric_id: str) -> MetricValue:
    if not isinstance(metric_id, str) or not metric_id.strip():
        raise ValueError("metric_id must not be empty")
    matches = tuple(metric for metric in result.metric_set.values if metric.name == metric_id)
    if len(matches) != 1:
        raise ValueError("selection metric must resolve to exactly one result metric")
    return matches[0]


def _validate_inputs(
    plan: WalkForwardTrainingPlan,
    candidates: tuple[ScientificTrial, ...],
    folds: tuple[WalkForwardFold, ...],
    observation_boundaries: tuple[datetime, ...],
) -> None:
    if not isinstance(plan, WalkForwardTrainingPlan):
        raise TypeError("plan must be a WalkForwardTrainingPlan")
    if not isinstance(folds, tuple) or not folds:
        raise ValueError("folds must be a non-empty tuple")
    if any(not isinstance(fold, WalkForwardFold) for fold in folds):
        raise TypeError("folds must contain WalkForwardFold values")
    if not isinstance(candidates, tuple) or not candidates:
        raise ValueError("candidates must be a non-empty tuple")
    if len(candidates) != len(plan.candidate_fingerprints):
        raise ValueError("candidate trials differ in count from the immutable plan")
    if any(not isinstance(candidate, ScientificTrial) for candidate in candidates):
        raise TypeError("candidates must contain ScientificTrial values")
    if tuple(candidate.trial_id for candidate in candidates) != plan.candidate_fingerprints:
        raise ValueError("candidate trial identities differ from the immutable plan")
    if any(candidate.evaluation_window is not None for candidate in candidates):
        raise ValueError("walk-forward base candidates cannot already have an evaluation window")
    if len({candidate.experiment_fingerprint for candidate in candidates}) != 1:
        raise ValueError("all walk-forward candidates must belong to one experiment")
    if candidates[0].experiment_fingerprint != plan.experiment_fingerprint:
        raise ValueError("candidate trials differ from the walk-forward experiment")
    if tuple(content_digest(fold) for fold in folds) != plan.fold_fingerprints:
        raise ValueError("folds differ from the immutable training plan")
    _validate_boundaries(folds, observation_boundaries)


def _validate_boundaries(
    folds: tuple[WalkForwardFold, ...], observation_boundaries: tuple[datetime, ...]
) -> None:
    if not isinstance(observation_boundaries, tuple) or len(observation_boundaries) < 2:
        raise ValueError("observation_boundaries must contain at least two timestamps")
    for value in observation_boundaries:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("observation boundaries must be timezone-aware datetimes")
    if any(
        left >= right for left, right in zip(observation_boundaries, observation_boundaries[1:])
    ):
        raise ValueError("observation boundaries must be strictly increasing")
    required_count = max(max(fold.train_indices[-1], fold.test_indices[-1]) + 1 for fold in folds)
    if len(observation_boundaries) < required_count + 1:
        raise ValueError("observation boundaries must cover all planned observations")


def _bounds(indices: Sequence[int], boundaries: tuple[datetime, ...]) -> tuple[datetime, datetime]:
    if not indices:
        raise ValueError("walk-forward evaluation windows cannot be empty")
    if tuple(indices) != tuple(range(indices[0], indices[-1] + 1)):
        raise ValueError("time-window materialization requires contiguous fold observations")
    return boundaries[indices[0]], boundaries[indices[-1] + 1]


def _clone_for_window(candidate: ScientificTrial, window: EvaluationWindow) -> ScientificTrial:
    return ScientificTrial.create(
        experiment_fingerprint=candidate.experiment_fingerprint,
        snapshot_fingerprint=candidate.snapshot_fingerprint,
        preflight_report=candidate.preflight_report,
        parameter_set=candidate.parameter_set,
        scenario=candidate.scenario,
        seed=candidate.seed,
        randomization=candidate.randomization,
        evaluation_window=window,
    )


__all__ = [
    "MaterializedWalkForwardTrials",
    "WalkForwardTrialBinding",
    "materialize_walk_forward_oos_trials",
    "materialize_walk_forward_training_trials",
    "oos_result_from_manifest",
    "training_score_from_result_manifest",
    "verify_walk_forward_result_binding",
]
