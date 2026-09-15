"""Deterministic search expansion and leakage-aware walk-forward windows."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum
from itertools import product
from typing import Any

from app.strategy_lab_v2.canonical import canonical_json, content_digest, freeze_json


class ExpansionMethod(StrEnum):
    GRID = "grid"
    RANDOM = "random"
    LATIN_HYPERCUBE = "latin_hypercube"


class WalkForwardMode(StrEnum):
    ANCHORED = "anchored"
    ROLLING = "rolling"


@dataclass(frozen=True, slots=True)
class SearchDimension:
    name: str
    choices: tuple[Any, ...] = ()
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    grid_steps: int | None = None
    integral: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("search dimension name must not be empty")
        has_bounds = self.minimum is not None or self.maximum is not None
        if bool(self.choices) == has_bounds:
            raise ValueError("dimension must define either choices or numeric bounds")
        if self.choices:
            frozen = tuple(freeze_json(value) for value in self.choices)
            keys = [canonical_json(value) for value in frozen]
            if len(set(keys)) != len(keys):
                raise ValueError("search dimension choices must be unique")
            if self.grid_steps is not None:
                raise ValueError("grid_steps applies only to numeric dimensions")
            object.__setattr__(self, "choices", frozen)
            return
        if self.minimum is None or self.maximum is None:
            raise ValueError("both numeric bounds are required")
        if not isinstance(self.minimum, Decimal) or not isinstance(self.maximum, Decimal):
            raise ValueError("numeric search bounds must be Decimal values")
        if not self.minimum.is_finite() or not self.maximum.is_finite():
            raise ValueError("search bounds must be finite")
        if self.minimum >= self.maximum:
            raise ValueError("minimum must be lower than maximum")
        if self.grid_steps is not None and (
            not isinstance(self.grid_steps, int)
            or isinstance(self.grid_steps, bool)
            or self.grid_steps < 2
        ):
            raise ValueError("numeric grid_steps must be at least two")
        if self.integral and (
            self.minimum != self.minimum.to_integral_value()
            or self.maximum != self.maximum.to_integral_value()
        ):
            raise ValueError("integral search bounds must be whole numbers")

    def grid_values(self) -> tuple[Any, ...]:
        if self.choices:
            return self.choices
        assert self.minimum is not None and self.maximum is not None
        steps = self.grid_steps or 2
        if self.integral:
            low, high = int(self.minimum), int(self.maximum)
            count = min(steps, high - low + 1)
            if count == 1:
                return (low,)
            span = high - low
            return tuple(low + (span * index // (count - 1)) for index in range(count))
        return tuple(
            self.minimum + (self.maximum - self.minimum) * Decimal(index) / Decimal(steps - 1)
            for index in range(steps)
        )

    def sample(self, unit_interval: Decimal) -> Any:
        if not isinstance(unit_interval, Decimal):
            raise ValueError("sample coordinate must be a Decimal")
        if not Decimal(0) <= unit_interval < Decimal(1):
            raise ValueError("sample coordinate must be in [0, 1)")
        if self.choices:
            index = int(unit_interval * len(self.choices))
            return self.choices[min(index, len(self.choices) - 1)]
        assert self.minimum is not None and self.maximum is not None
        if self.integral:
            low, high = int(self.minimum), int(self.maximum)
            return min(
                high,
                low
                + int(
                    (unit_interval * Decimal(high - low + 1)).to_integral_value(
                        rounding=ROUND_FLOOR
                    )
                ),
            )
        return self.minimum + (self.maximum - self.minimum) * unit_interval


@dataclass(frozen=True, slots=True)
class SearchDesign:
    dimensions: tuple[SearchDimension, ...]

    def __post_init__(self) -> None:
        names = [item.name for item in self.dimensions]
        if not names:
            raise ValueError("search design must contain at least one dimension")
        if len(set(names)) != len(names):
            raise ValueError("search dimension names must be unique")
        object.__setattr__(self, "dimensions", tuple(sorted(self.dimensions, key=lambda x: x.name)))


def _hash_integer(seed: int, *parts: object) -> int:
    material = canonical_json([seed, *parts]).encode("utf-8")
    return int.from_bytes(hashlib.sha256(material).digest(), "big")


def _unit_interval(seed: int, *parts: object) -> Decimal:
    numerator = _hash_integer(seed, *parts)
    return Decimal(numerator) / Decimal(1 << 256)


def _permutation(length: int, seed: int, dimension: str) -> list[int]:
    values = list(range(length))
    for index in range(length - 1, 0, -1):
        other = _hash_integer(seed, "lhs-permutation", dimension, index) % (index + 1)
        values[index], values[other] = values[other], values[index]
    return values


def expand_parameter_sets(
    design: SearchDesign,
    method: ExpansionMethod,
    *,
    count: int | None = None,
    seed: int = 0,
    max_trials: int = 100_000,
) -> tuple[Mapping[str, Any], ...]:
    """Expand a search in stable key order without relying on global RNG state."""

    if max_trials < 1:
        raise ValueError("max_trials must be positive")
    method = ExpansionMethod(method)
    dimensions = design.dimensions
    if method is ExpansionMethod.GRID:
        if count is not None:
            raise ValueError("grid expansion does not accept a sample count")
        value_sets = [dimension.grid_values() for dimension in dimensions]
        total = 1
        for value_set in value_sets:
            total *= len(value_set)
            if total > max_trials:
                raise ValueError(f"grid contains more than max_trials={max_trials} combinations")
        rows = product(*value_sets)
        return tuple(
            freeze_json({dimension.name: value for dimension, value in zip(dimensions, row)})
            for row in rows
        )

    if count is None or count < 1:
        raise ValueError("random and Latin-hypercube expansion require positive count")
    if count > max_trials:
        raise ValueError(f"count exceeds max_trials={max_trials}")

    if method is ExpansionMethod.RANDOM:
        return tuple(
            freeze_json(
                {
                    dimension.name: dimension.sample(
                        _unit_interval(seed, "random", trial_index, dimension.name)
                    )
                    for dimension in dimensions
                }
            )
            for trial_index in range(count)
        )

    if method is ExpansionMethod.LATIN_HYPERCUBE:
        permutations = {
            dimension.name: _permutation(count, seed, dimension.name) for dimension in dimensions
        }
        return tuple(
            freeze_json(
                {
                    dimension.name: dimension.sample(
                        (
                            Decimal(permutations[dimension.name][trial_index])
                            + _unit_interval(seed, "lhs-jitter", dimension.name, trial_index)
                        )
                        / Decimal(count)
                    )
                    for dimension in dimensions
                }
            )
            for trial_index in range(count)
        )

    raise ValueError(f"unsupported expansion method: {method}")


def expand_scenario_matrix(
    dimensions: Mapping[str, Sequence[Any]], *, max_scenarios: int = 10_000
) -> tuple[Mapping[str, Any], ...]:
    """Build stable scenario combinations; an empty matrix means one baseline scenario."""

    if not dimensions:
        return (freeze_json({}),)
    if max_scenarios < 1:
        raise ValueError("max_scenarios must be positive")
    if any(not isinstance(name, str) for name in dimensions):
        raise ValueError("scenario dimension names must be strings")
    names = sorted(dimensions)
    values = []
    total = 1
    for name in names:
        if not name.strip() or not dimensions[name]:
            raise ValueError("scenario dimensions need names and at least one value")
        choices = tuple(freeze_json(value) for value in dimensions[name])
        total *= len(choices)
        if total > max_scenarios:
            raise ValueError(f"scenario matrix exceeds max_scenarios={max_scenarios}")
        values.append(choices)
    return tuple(
        freeze_json({name: value for name, value in zip(names, row)}) for row in product(*values)
    )


@dataclass(frozen=True, slots=True)
class TrialDesign:
    candidate_index: int
    parameters: Mapping[str, Any]
    scenario: Mapping[str, Any]
    seed: int

    def __post_init__(self) -> None:
        if self.candidate_index < 0:
            raise ValueError("candidate_index must be non-negative")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))
        object.__setattr__(self, "scenario", freeze_json(self.scenario))


def build_trial_designs(
    parameter_sets: Sequence[Mapping[str, Any]],
    scenarios: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    max_trials: int = 100_000,
) -> tuple[TrialDesign, ...]:
    """Cross parameter draws and scenarios with stable per-candidate random seeds."""

    if not parameter_sets or not scenarios:
        raise ValueError("trial construction requires parameters and at least one scenario")
    if max_trials < 1:
        raise ValueError("max_trials must be positive")
    total = len(parameter_sets) * len(scenarios)
    if total > max_trials:
        raise ValueError(f"trial design contains more than max_trials={max_trials} candidates")
    designs: list[TrialDesign] = []
    for parameter_index, parameters in enumerate(parameter_sets):
        for scenario_index, scenario in enumerate(scenarios):
            identity = {
                "experiment_seed": seed,
                "parameter_index": parameter_index,
                "scenario_index": scenario_index,
                "parameters": parameters,
                "scenario": scenario,
            }
            derived_seed = int(content_digest(identity).split(":", 1)[1][:16], 16) & ((1 << 63) - 1)
            designs.append(
                TrialDesign(
                    candidate_index=len(designs),
                    parameters=parameters,
                    scenario=scenario,
                    seed=derived_seed,
                )
            )
    return tuple(designs)


@dataclass(frozen=True, slots=True)
class WalkForwardSpec:
    train_periods: int
    test_periods: int
    step_periods: int
    mode: WalkForwardMode
    gap_periods: int = 0
    embargo_periods: int = 0

    def __post_init__(self) -> None:
        if min(self.train_periods, self.test_periods, self.step_periods) < 1:
            raise ValueError("train, test, and step periods must be positive")
        if self.gap_periods < 0 or self.embargo_periods < 0:
            raise ValueError("gap and embargo periods must be non-negative")
        if self.step_periods < self.test_periods:
            raise ValueError("step_periods must not overlap out-of-sample test windows")


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold_index: int
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    excluded_indices: tuple[int, ...]

    @property
    def train_start(self) -> int:
        return self.train_indices[0]

    @property
    def train_end(self) -> int:
        return self.train_indices[-1] + 1

    @property
    def test_start(self) -> int:
        return self.test_indices[0]

    @property
    def test_end(self) -> int:
        return self.test_indices[-1] + 1


def build_walk_forward_folds(
    observation_count: int, spec: WalkForwardSpec
) -> tuple[WalkForwardFold, ...]:
    """Create chronological train/test folds with purge gaps and prior-test embargo."""

    if observation_count < 1:
        raise ValueError("observation_count must be positive")
    first_test_start = spec.train_periods + spec.gap_periods
    test_starts = range(
        first_test_start,
        observation_count - spec.test_periods + 1,
        spec.step_periods,
    )
    folds: list[WalkForwardFold] = []
    forbidden: set[int] = set()
    for test_start in test_starts:
        train_cutoff = test_start - spec.gap_periods
        candidates = [index for index in range(train_cutoff) if index not in forbidden]
        if len(candidates) < spec.train_periods:
            continue
        train = (
            candidates
            if spec.mode is WalkForwardMode.ANCHORED
            else candidates[-spec.train_periods :]
        )
        test = list(range(test_start, test_start + spec.test_periods))
        excluded = sorted(
            index
            for index in (forbidden | set(range(train_cutoff, test_start)))
            if index < test_start
        )
        folds.append(
            WalkForwardFold(
                fold_index=len(folds),
                train_indices=tuple(train),
                test_indices=tuple(test),
                excluded_indices=tuple(excluded),
            )
        )
        embargo_end = min(observation_count, test[-1] + 1 + spec.embargo_periods)
        forbidden.update(range(test[0], embargo_end))
    if not folds:
        raise ValueError("history is too short for one complete walk-forward fold")
    return tuple(folds)


def aggregate_out_of_sample(
    folds: Sequence[WalkForwardFold], observations: Sequence[Any]
) -> tuple[Any, ...]:
    """Return observations from test indices only, once each, in chronological order."""

    test_indices = sorted(index for fold in folds for index in fold.test_indices)
    if len(set(test_indices)) != len(test_indices):
        raise ValueError("walk-forward test windows overlap; OOS aggregation would double count")
    if test_indices and test_indices[-1] >= len(observations):
        raise ValueError("walk-forward fold references observations outside the input series")
    return tuple(observations[index] for index in test_indices)
