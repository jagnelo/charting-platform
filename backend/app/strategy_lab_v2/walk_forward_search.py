"""Training-only selection and frozen OOS task contracts for walk-forward search."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.experiments import (
    WalkForwardFold,
    WalkForwardSpec,
    build_walk_forward_folds,
)


class SelectionDirection(StrEnum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


def _nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True, slots=True)
class WalkForwardTrainingTask:
    """One candidate evaluated using only a fold's training observations."""

    fold_index: int
    candidate_index: int
    candidate_fingerprint: str
    training_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.fold_index, int)
            or isinstance(self.fold_index, bool)
            or self.fold_index < 0
        ):
            raise ValueError("fold_index must be a non-negative integer")
        if (
            not isinstance(self.candidate_index, int)
            or isinstance(self.candidate_index, bool)
            or self.candidate_index < 0
        ):
            raise ValueError("candidate_index must be a non-negative integer")
        require_sha256_digest(
            self.candidate_fingerprint,
            field_name="candidate_fingerprint",
        )
        indices = tuple(self.training_indices)
        if not indices or any(
            not isinstance(index, int) or isinstance(index, bool) or index < 0 for index in indices
        ):
            raise ValueError("training_indices must contain non-negative integers")
        if any(left >= right for left, right in zip(indices, indices[1:])):
            raise ValueError("training_indices must be strictly increasing")
        object.__setattr__(self, "training_indices", indices)

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "schema": "strategy-lab.walk-forward-training-task.v1",
                "fold_index": self.fold_index,
                "candidate_index": self.candidate_index,
                "candidate_fingerprint": self.candidate_fingerprint,
                "training_indices": self.training_indices,
            }
        )


@dataclass(frozen=True, slots=True)
class WalkForwardTrainingPlan:
    """Immutable candidate-by-fold training task matrix and selection rule."""

    experiment_fingerprint: str
    metric_id: str
    direction: SelectionDirection
    candidate_fingerprints: tuple[str, ...]
    fold_fingerprints: tuple[str, ...]
    tasks: tuple[WalkForwardTrainingTask, ...]

    def __post_init__(self) -> None:
        require_sha256_digest(self.experiment_fingerprint, field_name="experiment_fingerprint")
        _nonempty(self.metric_id, "metric_id")
        if not isinstance(self.direction, SelectionDirection):
            raise TypeError("direction must be a SelectionDirection")
        candidates = tuple(self.candidate_fingerprints)
        folds = tuple(self.fold_fingerprints)
        tasks = tuple(self.tasks)
        if not candidates or not folds or not tasks:
            raise ValueError("walk-forward training plan requires candidates, folds, and tasks")
        for fingerprint in candidates:
            require_sha256_digest(fingerprint, field_name="candidate_fingerprint")
        for fingerprint in folds:
            require_sha256_digest(fingerprint, field_name="fold_fingerprint")
        if len(candidates) != len(set(candidates)):
            raise ValueError("candidate trial fingerprints must be unique")
        if len(folds) != len(set(folds)):
            raise ValueError("walk-forward fold fingerprints must be unique")
        if any(not isinstance(task, WalkForwardTrainingTask) for task in tasks):
            raise TypeError("tasks must contain WalkForwardTrainingTask values")
        expected_pairs = {
            (fold_index, candidate_index)
            for fold_index in range(len(folds))
            for candidate_index in range(len(candidates))
        }
        observed_pairs = {(task.fold_index, task.candidate_index) for task in tasks}
        if observed_pairs != expected_pairs or len(observed_pairs) != len(tasks):
            raise ValueError("training tasks must cover every unique fold/candidate pair")
        for task in tasks:
            if task.fold_index >= len(folds) or task.candidate_index >= len(candidates):
                raise ValueError("training task references an unknown fold or candidate")
            if task.candidate_fingerprint != candidates[task.candidate_index]:
                raise ValueError("training task candidate identity differs from its plan")
        object.__setattr__(self, "candidate_fingerprints", candidates)
        object.__setattr__(self, "fold_fingerprints", folds)
        object.__setattr__(
            self,
            "tasks",
            tuple(sorted(tasks, key=lambda item: (item.fold_index, item.candidate_index))),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WalkForwardExecutionDefinition:
    """Restart-stable, immutable inputs from which all walk-forward phases derive.

    Candidate trials remain owner-scoped domain resources; this record pins
    their order together with the exact observation calendar and fold rule so a
    worker coordinator can reconstruct identical training and OOS tasks after
    process loss.
    """

    experiment_fingerprint: str
    candidate_fingerprints: tuple[str, ...]
    observation_boundaries: tuple[datetime, ...]
    spec: WalkForwardSpec
    metric_id: str
    direction: SelectionDirection
    max_tasks: int = 100_000

    def __post_init__(self) -> None:
        require_sha256_digest(self.experiment_fingerprint, field_name="experiment_fingerprint")
        candidates = tuple(self.candidate_fingerprints)
        if not candidates:
            raise ValueError("walk-forward execution requires base candidate trials")
        for fingerprint in candidates:
            require_sha256_digest(fingerprint, field_name="candidate_fingerprint")
        if len(candidates) != len(set(candidates)):
            raise ValueError("walk-forward base candidate fingerprints must be unique")
        boundaries = tuple(self.observation_boundaries)
        if len(boundaries) < 2:
            raise ValueError("observation_boundaries must contain at least two timestamps")
        for boundary in boundaries:
            if (
                not isinstance(boundary, datetime)
                or boundary.tzinfo is None
                or boundary.utcoffset() is None
            ):
                raise ValueError("observation boundaries must be timezone-aware datetimes")
        boundaries = tuple(boundary.astimezone(UTC) for boundary in boundaries)
        if any(left >= right for left, right in zip(boundaries, boundaries[1:])):
            raise ValueError("observation boundaries must be strictly increasing")
        if not isinstance(self.spec, WalkForwardSpec):
            raise TypeError("spec must be a WalkForwardSpec")
        if not isinstance(self.direction, SelectionDirection):
            raise TypeError("direction must be a SelectionDirection")
        if not isinstance(self.metric_id, str) or not self.metric_id.strip():
            raise ValueError("metric_id must not be empty")
        if (
            not isinstance(self.max_tasks, int)
            or isinstance(self.max_tasks, bool)
            or self.max_tasks < 1
        ):
            raise ValueError("max_tasks must be a positive integer")
        folds = build_walk_forward_folds(len(boundaries) - 1, self.spec)
        build_walk_forward_training_plan(
            self.experiment_fingerprint,
            candidates,
            folds,
            metric_id=self.metric_id,
            direction=self.direction,
            max_tasks=self.max_tasks,
        )
        object.__setattr__(self, "candidate_fingerprints", candidates)
        object.__setattr__(self, "observation_boundaries", boundaries)

    @property
    def folds(self) -> tuple[WalkForwardFold, ...]:
        return build_walk_forward_folds(len(self.observation_boundaries) - 1, self.spec)

    @property
    def training_plan(self) -> WalkForwardTrainingPlan:
        return build_walk_forward_training_plan(
            self.experiment_fingerprint,
            self.candidate_fingerprints,
            self.folds,
            metric_id=self.metric_id,
            direction=self.direction,
            max_tasks=self.max_tasks,
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WalkForwardTrainingScore:
    """Content-bound metric evidence for one training task."""

    training_task_fingerprint: str
    metric_id: str
    value: Decimal
    result_fingerprint: str

    def __post_init__(self) -> None:
        require_sha256_digest(
            self.training_task_fingerprint, field_name="training_task_fingerprint"
        )
        _nonempty(self.metric_id, "metric_id")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("training score value must be a finite Decimal")
        require_sha256_digest(self.result_fingerprint, field_name="result_fingerprint")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WalkForwardOosTask:
    """Frozen OOS evaluation of the candidate selected from training evidence."""

    fold_index: int
    fold_fingerprint: str
    candidate_index: int
    candidate_fingerprint: str
    test_indices: tuple[int, ...]
    training_selection_fingerprint: str

    def __post_init__(self) -> None:
        for name in ("fold_index", "candidate_index"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in (
            "fold_fingerprint",
            "candidate_fingerprint",
            "training_selection_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        indices = tuple(self.test_indices)
        if not indices or any(
            not isinstance(index, int) or isinstance(index, bool) or index < 0 for index in indices
        ):
            raise ValueError("test_indices must contain non-negative integers")
        if any(left >= right for left, right in zip(indices, indices[1:])):
            raise ValueError("test_indices must be strictly increasing")
        object.__setattr__(self, "test_indices", indices)

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "schema": "strategy-lab.walk-forward-oos-task.v1",
                "fold_index": self.fold_index,
                "fold_fingerprint": self.fold_fingerprint,
                "candidate_index": self.candidate_index,
                "candidate_fingerprint": self.candidate_fingerprint,
                "test_indices": self.test_indices,
                "training_selection_fingerprint": self.training_selection_fingerprint,
            }
        )


@dataclass(frozen=True, slots=True)
class WalkForwardSelection:
    """Deterministic per-fold selections and the resulting OOS task set."""

    training_plan_fingerprint: str
    score_evidence_fingerprint: str
    oos_tasks: tuple[WalkForwardOosTask, ...]

    def __post_init__(self) -> None:
        require_sha256_digest(
            self.training_plan_fingerprint, field_name="training_plan_fingerprint"
        )
        require_sha256_digest(
            self.score_evidence_fingerprint, field_name="score_evidence_fingerprint"
        )
        tasks = tuple(self.oos_tasks)
        if not tasks or any(not isinstance(task, WalkForwardOosTask) for task in tasks):
            raise ValueError("walk-forward selection requires OOS tasks")
        if len({task.fold_index for task in tasks}) != len(tasks):
            raise ValueError("walk-forward selection must contain exactly one OOS task per fold")
        if tuple(sorted(task.fold_index for task in tasks)) != tuple(range(len(tasks))):
            raise ValueError("walk-forward selection fold indices must be contiguous")
        if any(
            task.training_selection_fingerprint != self.score_evidence_fingerprint for task in tasks
        ):
            raise ValueError("OOS tasks must bind the selection's exact training evidence")
        object.__setattr__(
            self, "oos_tasks", tuple(sorted(tasks, key=lambda item: item.fold_index))
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class WalkForwardOosResult:
    """Verified OOS result receipt; never eligible as training selection evidence."""

    oos_task_fingerprint: str
    result_fingerprint: str
    metric_id: str
    value: Decimal

    def __post_init__(self) -> None:
        require_sha256_digest(self.oos_task_fingerprint, field_name="oos_task_fingerprint")
        require_sha256_digest(self.result_fingerprint, field_name="result_fingerprint")
        _nonempty(self.metric_id, "metric_id")
        if not isinstance(self.value, Decimal) or not self.value.is_finite():
            raise ValueError("OOS result value must be a finite Decimal")


def build_walk_forward_training_plan(
    experiment_fingerprint: str,
    candidate_fingerprints: tuple[str, ...],
    folds: tuple[WalkForwardFold, ...],
    *,
    metric_id: str,
    direction: SelectionDirection,
    max_tasks: int = 100_000,
) -> WalkForwardTrainingPlan:
    """Create one training-only evaluation task per candidate and fold."""

    require_sha256_digest(experiment_fingerprint, field_name="experiment_fingerprint")
    if not isinstance(candidate_fingerprints, tuple) or not candidate_fingerprints:
        raise ValueError("candidate_fingerprints must be a non-empty tuple")
    if not isinstance(folds, tuple) or not folds:
        raise ValueError("folds must be a non-empty tuple")
    if any(not isinstance(fold, WalkForwardFold) for fold in folds):
        raise TypeError("folds must contain WalkForwardFold values")
    if tuple(fold.fold_index for fold in folds) != tuple(range(len(folds))):
        raise ValueError("walk-forward fold indices must be contiguous and ordered")
    if not isinstance(max_tasks, int) or isinstance(max_tasks, bool) or max_tasks < 1:
        raise ValueError("max_tasks must be a positive integer")
    task_count = len(candidate_fingerprints) * len(folds)
    if task_count > max_tasks:
        raise ValueError(f"walk-forward training plan exceeds max_tasks={max_tasks}")
    fold_fingerprints = tuple(content_digest(fold) for fold in folds)
    tasks = tuple(
        WalkForwardTrainingTask(
            fold_index=fold.fold_index,
            candidate_index=candidate_index,
            candidate_fingerprint=candidate_fingerprint,
            training_indices=fold.train_indices,
        )
        for fold in folds
        for candidate_index, candidate_fingerprint in enumerate(candidate_fingerprints)
    )
    return WalkForwardTrainingPlan(
        experiment_fingerprint,
        metric_id,
        direction,
        candidate_fingerprints,
        fold_fingerprints,
        tasks,
    )


def select_walk_forward_oos_tasks(
    plan: WalkForwardTrainingPlan,
    folds: tuple[WalkForwardFold, ...],
    scores: Sequence[WalkForwardTrainingScore],
) -> WalkForwardSelection:
    """Select one candidate per fold using only exact planned training scores."""

    if not isinstance(plan, WalkForwardTrainingPlan):
        raise TypeError("plan must be a WalkForwardTrainingPlan")
    if not isinstance(folds, tuple) or any(not isinstance(fold, WalkForwardFold) for fold in folds):
        raise ValueError("selection requires typed fold values")
    if tuple(content_digest(fold) for fold in folds) != plan.fold_fingerprints:
        raise ValueError("selection folds differ from the immutable training plan")
    if len(folds) != len(plan.fold_fingerprints):
        raise ValueError("selection requires the exact immutable fold sequence")
    if not isinstance(scores, Sequence) or not scores:
        raise ValueError("training selection requires score evidence for every task")
    if any(not isinstance(score, WalkForwardTrainingScore) for score in scores):
        raise TypeError("scores must contain WalkForwardTrainingScore values")
    by_task = {score.training_task_fingerprint: score for score in scores}
    if len(by_task) != len(scores):
        raise ValueError("training task scores must be unique")
    expected = {task.fingerprint: task for task in plan.tasks}
    if set(by_task) != set(expected):
        raise ValueError("training evidence must exactly cover the immutable task plan")
    if any(score.metric_id != plan.metric_id for score in scores):
        raise ValueError("training score metric differs from the declared selection metric")
    scores_by_fold: dict[int, list[tuple[int, Decimal]]] = {}
    for task_fingerprint, score in by_task.items():
        task = expected[task_fingerprint]
        scores_by_fold.setdefault(task.fold_index, []).append((task.candidate_index, score.value))
    score_evidence_fingerprint = content_digest(
        tuple(
            sorted(
                (task_fingerprint, score.fingerprint) for task_fingerprint, score in by_task.items()
            )
        )
    )
    selected: list[WalkForwardOosTask] = []
    for fold in folds:
        candidate_scores = scores_by_fold[fold.fold_index]
        if plan.direction is SelectionDirection.MAXIMIZE:
            selected_candidate = min(candidate_scores, key=lambda item: (-item[1], item[0]))[0]
        else:
            selected_candidate = min(candidate_scores, key=lambda item: (item[1], item[0]))[0]
        selected.append(
            WalkForwardOosTask(
                fold_index=fold.fold_index,
                fold_fingerprint=content_digest(fold),
                candidate_index=selected_candidate,
                candidate_fingerprint=plan.candidate_fingerprints[selected_candidate],
                test_indices=fold.test_indices,
                training_selection_fingerprint=score_evidence_fingerprint,
            )
        )
    return WalkForwardSelection(plan.fingerprint, score_evidence_fingerprint, tuple(selected))


def collect_walk_forward_oos_results(
    selection: WalkForwardSelection,
    results: Sequence[WalkForwardOosResult],
    *,
    metric_id: str,
) -> tuple[WalkForwardOosResult, ...]:
    """Accept exactly the selected candidates' OOS receipts in fold order."""

    if not isinstance(selection, WalkForwardSelection):
        raise TypeError("selection must be a WalkForwardSelection")
    _nonempty(metric_id, "metric_id")
    if not isinstance(results, Sequence) or not results:
        raise ValueError("OOS aggregation requires a result for every selected fold")
    if any(not isinstance(result, WalkForwardOosResult) for result in results):
        raise TypeError("results must contain WalkForwardOosResult values")
    by_task = {result.oos_task_fingerprint: result for result in results}
    if len(by_task) != len(results):
        raise ValueError("OOS result task identities must be unique")
    expected = {task.fingerprint for task in selection.oos_tasks}
    if set(by_task) != expected:
        raise ValueError("OOS result evidence must exactly cover the selected task set")
    if any(result.metric_id != metric_id for result in results):
        raise ValueError("OOS result metric differs from the requested aggregation metric")
    return tuple(by_task[task.fingerprint] for task in selection.oos_tasks)


__all__ = [
    "SelectionDirection",
    "WalkForwardExecutionDefinition",
    "WalkForwardOosResult",
    "WalkForwardOosTask",
    "WalkForwardSelection",
    "WalkForwardTrainingPlan",
    "WalkForwardTrainingScore",
    "WalkForwardTrainingTask",
    "build_walk_forward_training_plan",
    "collect_walk_forward_oos_results",
    "select_walk_forward_oos_tasks",
]
