"""Compose walk-forward phases with the durable experiment search queue."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.contracts import RunResultManifest
from app.strategy_lab_v2.experiments import WalkForwardFold
from app.strategy_lab_v2.search_state import (
    SearchCandidatePhase,
    SearchExecutionState,
    SearchStateDecision,
    SearchStateResolution,
    append_search_candidates,
    new_search_execution_state,
)
from app.strategy_lab_v2.walk_forward_search import (
    WalkForwardOosResult,
    WalkForwardSelection,
    WalkForwardTrainingPlan,
    WalkForwardTrainingScore,
    collect_walk_forward_oos_results,
    select_walk_forward_oos_tasks,
)
from app.strategy_lab_v2.walk_forward_trials import (
    MaterializedWalkForwardTrials,
    oos_result_from_manifest,
    training_score_from_result_manifest,
)


@dataclass(frozen=True, slots=True)
class WalkForwardQueueTaskBinding:
    """Stable queue index mapped to the walk-forward semantic task identity."""

    candidate_index: int
    task_fingerprint: str
    trial_fingerprint: str
    fold_index: int
    parameter_candidate_index: int
    purpose: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate_index, int)
            or isinstance(self.candidate_index, bool)
            or self.candidate_index < 0
        ):
            raise ValueError("candidate_index must be a non-negative integer")
        for name in ("task_fingerprint", "trial_fingerprint"):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in ("fold_index", "parameter_candidate_index"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.purpose not in {"training", "out_of_sample"}:
            raise ValueError("walk-forward queue task purpose is unsupported")


@dataclass(frozen=True, slots=True)
class WalkForwardQueueTransition:
    """Search-state transition plus deterministic OOS queue assignments."""

    resolution: SearchStateResolution
    oos_task_bindings: tuple[WalkForwardQueueTaskBinding, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.resolution, SearchStateResolution):
            raise TypeError("resolution must be a SearchStateResolution")
        bindings = tuple(self.oos_task_bindings)
        if any(not isinstance(binding, WalkForwardQueueTaskBinding) for binding in bindings):
            raise TypeError("OOS task bindings must be WalkForwardQueueTaskBinding values")
        if self.resolution.decision is SearchStateDecision.REJECT and bindings:
            raise ValueError("rejected queue transitions cannot expose task assignments")
        if len({binding.task_fingerprint for binding in bindings}) != len(bindings):
            raise ValueError("OOS queue task bindings must be unique")
        object.__setattr__(self, "oos_task_bindings", bindings)


@dataclass(frozen=True, slots=True)
class WalkForwardQueueResultEvidence:
    """Owner-resolved run manifest bound to its durable worker completion digest."""

    search_result_fingerprint: str
    manifest: RunResultManifest

    def __post_init__(self) -> None:
        require_sha256_digest(
            self.search_result_fingerprint, field_name="search_result_fingerprint"
        )
        if not isinstance(self.manifest, RunResultManifest):
            raise TypeError("manifest must be a RunResultManifest")


def initialize_walk_forward_training_queue(
    plan: WalkForwardTrainingPlan,
    training_trials: MaterializedWalkForwardTrials,
    *,
    now: datetime | None = None,
) -> tuple[SearchExecutionState, tuple[WalkForwardQueueTaskBinding, ...]]:
    """Flatten tasks into stable indices; omit time for deterministic replay."""

    _validate_training_materialization(plan, training_trials)
    index_by_trial: dict[str, int] = {}
    bindings: list[WalkForwardQueueTaskBinding] = []
    for task, trial in zip(plan.tasks, training_trials.trials, strict=True):
        queue_index = index_by_trial.setdefault(trial.trial_id, len(index_by_trial))
        bindings.append(
            WalkForwardQueueTaskBinding(
                candidate_index=queue_index,
                task_fingerprint=task.fingerprint,
                trial_fingerprint=trial.trial_id,
                fold_index=task.fold_index,
                parameter_candidate_index=task.candidate_index,
                purpose="training",
            )
        )
    state = new_search_execution_state(
        plan.experiment_fingerprint,
        tuple(index_by_trial),
        now=now,
    )
    return state, tuple(bindings)


def training_scores_from_search_queue(
    plan: WalkForwardTrainingPlan,
    training_trials: MaterializedWalkForwardTrials,
    queue_bindings: tuple[WalkForwardQueueTaskBinding, ...],
    state: SearchExecutionState,
    results_by_attempt: Mapping[str, WalkForwardQueueResultEvidence],
) -> tuple[WalkForwardTrainingScore, ...]:
    """Rehydrate scores through durable candidate attempts and authoritative manifests."""

    _validate_training_materialization(plan, training_trials)
    if not isinstance(state, SearchExecutionState):
        raise TypeError("state must be a SearchExecutionState")
    if state.experiment_fingerprint != plan.experiment_fingerprint:
        raise ValueError("search state differs from the walk-forward experiment")
    if not isinstance(queue_bindings, tuple) or tuple(
        binding.task_fingerprint for binding in queue_bindings
    ) != tuple(task.fingerprint for task in plan.tasks):
        raise ValueError("queue bindings differ from the exact walk-forward task order")
    if any(binding.purpose != "training" for binding in queue_bindings):
        raise ValueError("training queue contains a non-training task binding")
    if not isinstance(results_by_attempt, Mapping):
        raise TypeError("results_by_attempt must be an owner-resolved attempt mapping")

    window_binding_by_task = {
        binding.task_fingerprint: binding for binding in training_trials.bindings
    }
    queue_index_by_trial: dict[str, int] = {}
    for queue_binding in queue_bindings:
        expected_index = queue_index_by_trial.setdefault(
            queue_binding.trial_fingerprint, len(queue_index_by_trial)
        )
        window_binding = window_binding_by_task[queue_binding.task_fingerprint]
        if (
            queue_binding.candidate_index != expected_index
            or queue_binding.trial_fingerprint != window_binding.trial_fingerprint
            or queue_binding.fold_index != window_binding.fold_index
            or queue_binding.parameter_candidate_index != window_binding.candidate_index
        ):
            raise ValueError("queue task binding differs from its fold trial binding")
    training_count = len(queue_index_by_trial)
    if len(state.candidates) < training_count:
        raise ValueError("durable search queue is missing planned training candidates")
    training_candidates = state.candidates[:training_count]
    if tuple(candidate.trial_fingerprint for candidate in training_candidates) != tuple(
        queue_index_by_trial
    ):
        raise ValueError("durable training candidate order differs from the walk-forward plan")

    expected_attempts: set[str] = set()
    for candidate in training_candidates:
        if candidate.phase is not SearchCandidatePhase.SUCCEEDED or candidate.attempt_id is None:
            raise ValueError("every training candidate must have a successful durable attempt")
        expected_attempts.add(candidate.attempt_id)
    if set(results_by_attempt) != expected_attempts:
        raise ValueError("resolved training manifests must exactly cover successful attempts")

    scores: list[WalkForwardTrainingScore] = []
    for queue_binding, window_binding in zip(queue_bindings, training_trials.bindings, strict=True):
        candidate = state.candidates[queue_binding.candidate_index]
        assert candidate.attempt_id is not None
        evidence = results_by_attempt[candidate.attempt_id]
        manifest = evidence.manifest
        if (
            manifest.attempt_id != candidate.attempt_id
            or manifest.trial_id != queue_binding.trial_fingerprint
            or manifest.experiment_fingerprint != plan.experiment_fingerprint
            or evidence.search_result_fingerprint != candidate.result_fingerprint
        ):
            raise ValueError("resolved result manifest differs from the persisted search receipt")
        scores.append(
            training_score_from_result_manifest(
                window_binding,
                manifest,
                metric_id=plan.metric_id,
            )
        )
    return tuple(scores)


def append_selected_oos_queue(
    state: SearchExecutionState,
    plan: WalkForwardTrainingPlan,
    folds: tuple[WalkForwardFold, ...],
    training_trials: MaterializedWalkForwardTrials,
    training_queue_bindings: tuple[WalkForwardQueueTaskBinding, ...],
    training_results_by_attempt: Mapping[str, WalkForwardQueueResultEvidence],
    selection: WalkForwardSelection,
    oos_trials: MaterializedWalkForwardTrials,
    *,
    now: datetime,
) -> WalkForwardQueueTransition:
    """Append only the verified selected OOS trials to the same experiment queue.

    The persisted search state already owns candidate indices and attempt
    receipts. Keeping the original experiment fingerprint and appending only
    after the full training phase avoids a second queue or a schema migration.
    The selection is recomputed from the immutable plan and complete training
    score set before any OOS index is admitted.
    """

    if not isinstance(state, SearchExecutionState):
        raise TypeError("state must be a SearchExecutionState")
    if state.experiment_fingerprint != plan.experiment_fingerprint:
        raise ValueError("search state differs from the walk-forward experiment")
    _validate_training_materialization(plan, training_trials)
    if not isinstance(selection, WalkForwardSelection):
        raise TypeError("selection must be a WalkForwardSelection")
    if selection.training_plan_fingerprint != plan.fingerprint:
        raise ValueError("selection differs from the immutable training plan")
    training_fingerprints = tuple(
        dict.fromkeys(binding.trial_fingerprint for binding in training_trials.bindings)
    )
    oos_fingerprints = tuple(binding.trial_fingerprint for binding in oos_trials.bindings)
    if len(oos_fingerprints) != len(set(oos_fingerprints)):
        raise ValueError("each selected OOS fold must materialize a unique immutable trial")
    observed_fingerprints = tuple(candidate.trial_fingerprint for candidate in state.candidates)
    expected_all = (*training_fingerprints, *oos_fingerprints)
    if observed_fingerprints not in (training_fingerprints, expected_all):
        return WalkForwardQueueTransition(
            SearchStateResolution(
                SearchStateDecision.REJECT,
                state,
                rejection_reason="persisted search queue does not match the exact walk-forward phase trials",
            )
        )
    if observed_fingerprints == training_fingerprints and (
        not state.complete
        or any(
            candidate.phase is not SearchCandidatePhase.SUCCEEDED for candidate in state.candidates
        )
    ):
        return WalkForwardQueueTransition(
            SearchStateResolution(
                SearchStateDecision.REJECT,
                state,
                rejection_reason="all training candidates must succeed before OOS dispatch",
            )
        )

    training_scores = training_scores_from_search_queue(
        plan,
        training_trials,
        training_queue_bindings,
        state,
        training_results_by_attempt,
    )
    expected_selection = select_walk_forward_oos_tasks(plan, folds, training_scores)
    if selection != expected_selection:
        raise ValueError("OOS selection differs from the complete deterministic training evidence")
    _validate_oos_materialization(selection, oos_trials)

    if observed_fingerprints == expected_all:
        resolution = SearchStateResolution(
            SearchStateDecision.REPLAY_EXISTING,
            state,
            candidate_index=len(training_fingerprints),
        )
    else:
        resolution = append_search_candidates(state, oos_fingerprints, now=now)
    if resolution.decision is SearchStateDecision.REJECT:
        return WalkForwardQueueTransition(resolution)
    oos_bindings = tuple(
        WalkForwardQueueTaskBinding(
            candidate_index=len(training_fingerprints) + index,
            task_fingerprint=task.fingerprint,
            trial_fingerprint=trial.trial_id,
            fold_index=task.fold_index,
            parameter_candidate_index=task.candidate_index,
            purpose="out_of_sample",
        )
        for index, (task, trial) in enumerate(
            zip(selection.oos_tasks, oos_trials.trials, strict=True)
        )
    )
    return WalkForwardQueueTransition(resolution, oos_bindings)


def oos_results_from_search_queue(
    plan: WalkForwardTrainingPlan,
    selection: WalkForwardSelection,
    training_queue_bindings: tuple[WalkForwardQueueTaskBinding, ...],
    oos_trials: MaterializedWalkForwardTrials,
    oos_queue_bindings: tuple[WalkForwardQueueTaskBinding, ...],
    state: SearchExecutionState,
    results_by_attempt: Mapping[str, WalkForwardQueueResultEvidence],
) -> tuple[WalkForwardOosResult, ...]:
    """Rehydrate the complete OOS result set from selected durable queue slots.

    This accepts only the appended OOS suffix, and only when every slot has a
    successful attempt whose completion digest and owner-resolved authoritative
    Nautilus manifest agree on experiment, trial, attempt, and exact test window.
    Training queue results are never included in the returned aggregate input.
    """

    if not isinstance(plan, WalkForwardTrainingPlan):
        raise TypeError("plan must be a WalkForwardTrainingPlan")
    if not isinstance(selection, WalkForwardSelection):
        raise TypeError("selection must be a WalkForwardSelection")
    if selection.training_plan_fingerprint != plan.fingerprint:
        raise ValueError("selection differs from the immutable training plan")
    if not isinstance(training_queue_bindings, tuple) or tuple(
        binding.purpose for binding in training_queue_bindings
    ) != ("training",) * len(training_queue_bindings):
        raise ValueError("training queue bindings must contain only training tasks")
    expected_training_tasks = tuple(task.fingerprint for task in plan.tasks)
    if tuple(binding.task_fingerprint for binding in training_queue_bindings) != (
        expected_training_tasks
    ):
        raise ValueError("training queue bindings differ from the exact immutable task order")
    if not isinstance(oos_trials, MaterializedWalkForwardTrials):
        raise TypeError("oos_trials must be MaterializedWalkForwardTrials")
    _validate_oos_materialization(selection, oos_trials)
    if not isinstance(state, SearchExecutionState):
        raise TypeError("state must be a SearchExecutionState")
    if state.experiment_fingerprint != plan.experiment_fingerprint:
        raise ValueError("search state differs from the walk-forward experiment")
    expected_task_fingerprints = tuple(task.fingerprint for task in selection.oos_tasks)
    if (
        not isinstance(oos_queue_bindings, tuple)
        or tuple(binding.task_fingerprint for binding in oos_queue_bindings)
        != expected_task_fingerprints
    ):
        raise ValueError("OOS queue bindings differ from the exact selected task order")
    if any(binding.purpose != "out_of_sample" for binding in oos_queue_bindings):
        raise ValueError("OOS queue contains a non-OOS task binding")
    if not isinstance(results_by_attempt, Mapping):
        raise TypeError("results_by_attempt must be an owner-resolved attempt mapping")

    if not oos_queue_bindings:
        raise ValueError("OOS queue bindings must not be empty")
    unique_training_trials = tuple(
        dict.fromkeys(binding.trial_fingerprint for binding in training_queue_bindings)
    )
    training_count = len(unique_training_trials)
    if oos_queue_bindings[0].candidate_index != training_count:
        raise ValueError("OOS queue does not begin directly after the immutable training prefix")
    if tuple(binding.candidate_index for binding in oos_queue_bindings) != tuple(
        range(training_count, training_count + len(oos_queue_bindings))
    ):
        raise ValueError("OOS queue indices must be one contiguous appended suffix")
    expected_count = training_count + len(selection.oos_tasks)
    if len(state.candidates) != expected_count:
        raise ValueError("durable search queue does not contain the exact training and OOS phases")
    training_candidates = state.candidates[:training_count]
    if (
        tuple(candidate.trial_fingerprint for candidate in training_candidates)
        != unique_training_trials
    ):
        raise ValueError("durable training queue prefix differs from the immutable task bindings")
    if any(
        candidate.phase is not SearchCandidatePhase.SUCCEEDED for candidate in training_candidates
    ):
        raise ValueError("every training candidate must remain durably successful during OOS")

    expected_attempts: set[str] = set()
    receipts: list[WalkForwardOosResult] = []
    for index, (queue_binding, task, window_binding) in enumerate(
        zip(
            oos_queue_bindings,
            selection.oos_tasks,
            oos_trials.bindings,
            strict=True,
        )
    ):
        expected_index = training_count + index
        candidate = state.candidates[expected_index]
        if (
            queue_binding.candidate_index != expected_index
            or queue_binding.trial_fingerprint != candidate.trial_fingerprint
            or queue_binding.trial_fingerprint != window_binding.trial_fingerprint
            or queue_binding.fold_index != task.fold_index
            or queue_binding.parameter_candidate_index != task.candidate_index
            or window_binding.task_fingerprint != task.fingerprint
        ):
            raise ValueError("OOS queue slot differs from the exact selected trial binding")
        if candidate.phase is not SearchCandidatePhase.SUCCEEDED or candidate.attempt_id is None:
            raise ValueError("every selected OOS candidate must have a successful durable attempt")
        expected_attempts.add(candidate.attempt_id)
        evidence = results_by_attempt.get(candidate.attempt_id)
        if evidence is None:
            raise ValueError("owner-resolved OOS result manifest is missing")
        manifest = evidence.manifest
        if (
            manifest.attempt_id != candidate.attempt_id
            or manifest.trial_id != queue_binding.trial_fingerprint
            or manifest.experiment_fingerprint != plan.experiment_fingerprint
            or evidence.search_result_fingerprint != candidate.result_fingerprint
        ):
            raise ValueError("resolved OOS manifest differs from the persisted search receipt")
        receipts.append(
            oos_result_from_manifest(window_binding, manifest, metric_id=plan.metric_id)
        )
    if set(results_by_attempt) != expected_attempts:
        raise ValueError("resolved OOS manifests must exactly cover selected successful attempts")
    return collect_walk_forward_oos_results(selection, receipts, metric_id=plan.metric_id)


def _validate_training_materialization(
    plan: WalkForwardTrainingPlan,
    training_trials: MaterializedWalkForwardTrials,
) -> None:
    if not isinstance(plan, WalkForwardTrainingPlan):
        raise TypeError("plan must be a WalkForwardTrainingPlan")
    if not isinstance(training_trials, MaterializedWalkForwardTrials):
        raise TypeError("training_trials must be MaterializedWalkForwardTrials")
    if tuple(binding.task_fingerprint for binding in training_trials.bindings) != tuple(
        task.fingerprint for task in plan.tasks
    ):
        raise ValueError("training trial bindings differ from the exact immutable task order")
    if any(binding.purpose != "training" for binding in training_trials.bindings):
        raise ValueError("training materialization contains a non-training binding")


def _validate_oos_materialization(
    selection: WalkForwardSelection,
    oos_trials: MaterializedWalkForwardTrials,
) -> None:
    if not isinstance(oos_trials, MaterializedWalkForwardTrials):
        raise TypeError("oos_trials must be MaterializedWalkForwardTrials")
    if tuple(binding.task_fingerprint for binding in oos_trials.bindings) != tuple(
        task.fingerprint for task in selection.oos_tasks
    ):
        raise ValueError("OOS trial bindings differ from the exact selected task order")
    if any(binding.purpose != "out_of_sample" for binding in oos_trials.bindings):
        raise ValueError("OOS materialization contains a non-OOS binding")


__all__ = [
    "WalkForwardQueueResultEvidence",
    "WalkForwardQueueTaskBinding",
    "WalkForwardQueueTransition",
    "append_selected_oos_queue",
    "initialize_walk_forward_training_queue",
    "oos_results_from_search_queue",
    "training_scores_from_search_queue",
]
