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
from app.strategy_lab_v2.contracts import (
    TRIAL_SEED_DERIVATION_VERSION,
    TrialRandomization,
    TrialSeedPolicy,
)


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
    randomization: TrialRandomization

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate_index, int)
            or isinstance(self.candidate_index, bool)
            or self.candidate_index < 0
        ):
            raise ValueError("candidate_index must be non-negative")
        if not isinstance(self.randomization, TrialRandomization):
            raise TypeError("trial design requires typed TrialRandomization provenance")
        object.__setattr__(self, "parameters", freeze_json(self.parameters))
        object.__setattr__(self, "scenario", freeze_json(self.scenario))

    @property
    def seed(self) -> int:
        return self.randomization.seed

    @property
    def replicate_index(self) -> int:
        return self.randomization.replicate_index


def build_trial_designs(
    parameter_sets: Sequence[Mapping[str, Any]],
    scenarios: Sequence[Mapping[str, Any]],
    *,
    seed: int,
    seed_policy: TrialSeedPolicy = TrialSeedPolicy.PER_CANDIDATE,
    replicate_count: int = 1,
    scope_fingerprint: str | None = None,
    max_trials: int = 100_000,
) -> tuple[TrialDesign, ...]:
    """Build deterministic seed assignments without claiming paired random draws.

    The default retains the existing per-candidate seed derivation. The explicit
    shared policy assigns one initial seed to each scope/scenario/replicate group
    across parameter rows; engine stream compatibility is not implied.
    """

    if not parameter_sets or not scenarios:
        raise ValueError("trial construction requires parameters and at least one scenario")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")
    seed_policy = TrialSeedPolicy(seed_policy)
    if (
        not isinstance(replicate_count, int)
        or isinstance(replicate_count, bool)
        or replicate_count < 1
    ):
        raise ValueError("replicate_count must be a positive integer")
    if not isinstance(max_trials, int) or isinstance(max_trials, bool) or max_trials < 1:
        raise ValueError("max_trials must be positive")
    if scope_fingerprint is not None and (
        not isinstance(scope_fingerprint, str) or not scope_fingerprint
    ):
        raise ValueError("scope_fingerprint must be a non-empty SHA-256 digest")
    if seed_policy is TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE:
        if scope_fingerprint is None:
            raise ValueError("shared seed policy requires a fixed-input scope_fingerprint")
        parameter_keys = [canonical_json(freeze_json(item)) for item in parameter_sets]
        scenario_keys = [canonical_json(freeze_json(item)) for item in scenarios]
        if len(parameter_keys) != len(set(parameter_keys)):
            raise ValueError("shared seed policy requires unique parameter sets")
        if len(scenario_keys) != len(set(scenario_keys)):
            raise ValueError("shared seed policy requires unique scenarios")
    total = len(parameter_sets) * len(scenarios) * replicate_count
    if total > max_trials:
        raise ValueError(f"trial design contains more than max_trials={max_trials} candidates")
    designs: list[TrialDesign] = []
    seed_groups_by_value: dict[int, str] = {}
    derivation_version = TRIAL_SEED_DERIVATION_VERSION
    for parameter_index, parameters in enumerate(parameter_sets):
        for scenario_index, scenario in enumerate(scenarios):
            for replicate_index in range(replicate_count):
                candidate_identity = {
                    "experiment_seed": seed,
                    "parameter_index": parameter_index,
                    "scenario_index": scenario_index,
                    "parameters": parameters,
                    "scenario": scenario,
                }
                identity: dict[str, Any]
                if seed_policy is TrialSeedPolicy.SHARED_PER_SCENARIO_REPLICATE:
                    identity = {
                        "derivation_version": derivation_version,
                        "policy": seed_policy.value,
                        "scope_fingerprint": scope_fingerprint,
                        "master_seed": seed,
                        "scenario": scenario,
                        "replicate_index": replicate_index,
                    }
                elif replicate_count == 1 and scope_fingerprint is None:
                    identity = candidate_identity
                else:
                    identity = {
                        **candidate_identity,
                        "replicate_index": replicate_index,
                        "scope_fingerprint": scope_fingerprint,
                        "derivation_version": derivation_version,
                    }
                seed_group_fingerprint = content_digest(identity)
                derived_seed = int(seed_group_fingerprint.split(":", 1)[1][:16], 16) & (
                    (1 << 63) - 1
                )
                prior_group = seed_groups_by_value.setdefault(derived_seed, seed_group_fingerprint)
                if prior_group != seed_group_fingerprint:
                    raise ValueError(
                        "derived trial seed collision across distinct randomization groups"
                    )
                randomization = TrialRandomization(
                    master_seed=seed,
                    seed=derived_seed,
                    policy=seed_policy,
                    replicate_index=replicate_index,
                    scope_fingerprint=scope_fingerprint,
                    seed_group_fingerprint=seed_group_fingerprint,
                    replicate_count=replicate_count,
                    derivation_version=derivation_version,
                )
                designs.append(
                    TrialDesign(
                        candidate_index=len(designs),
                        parameters=parameters,
                        scenario=scenario,
                        randomization=randomization,
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
        for name in ("train_periods", "test_periods", "step_periods"):
            _require_integer(getattr(self, name), name, minimum=1)
        for name in ("gap_periods", "embargo_periods"):
            _require_integer(getattr(self, name), name, minimum=0)
        try:
            mode = WalkForwardMode(self.mode)
        except (TypeError, ValueError) as error:
            raise ValueError("mode must be anchored or rolling") from error
        object.__setattr__(self, "mode", mode)
        if self.step_periods < self.test_periods:
            raise ValueError("step_periods must not overlap out-of-sample test windows")


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    fold_index: int
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    excluded_indices: tuple[int, ...]

    def __post_init__(self) -> None:
        _require_integer(self.fold_index, "fold_index", minimum=0)
        for name in ("train_indices", "test_indices", "excluded_indices"):
            values = tuple(getattr(self, name))
            if name != "excluded_indices" and not values:
                raise ValueError(f"{name} must not be empty")
            for index in values:
                _require_integer(index, name, minimum=0)
            if any(left >= right for left, right in zip(values, values[1:])):
                raise ValueError(f"{name} must be strictly increasing")
            object.__setattr__(self, name, values)
        train = set(self.train_indices)
        test = set(self.test_indices)
        excluded = set(self.excluded_indices)
        if self.train_indices[-1] >= self.test_indices[0]:
            raise ValueError("training observations must precede the OOS test window")
        if train & test or train & excluded or test & excluded:
            raise ValueError("train, test, and excluded indices must be disjoint")
        fold_span = set(range(self.train_indices[0], self.test_indices[0]))
        if fold_span != (train | excluded) & fold_span:
            raise ValueError(
                "every pre-test observation in the fold span must be trained or excluded"
            )

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

    _require_integer(observation_count, "observation_count", minimum=1)
    if not isinstance(spec, WalkForwardSpec):
        raise TypeError("spec must be a WalkForwardSpec")
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

    if not folds:
        raise ValueError("at least one walk-forward fold is required")
    if any(not isinstance(fold, WalkForwardFold) for fold in folds):
        raise TypeError("folds must contain WalkForwardFold values")
    test_indices = sorted(index for fold in folds for index in fold.test_indices)
    if len(set(test_indices)) != len(test_indices):
        raise ValueError("walk-forward test windows overlap; OOS aggregation would double count")
    referenced_indices = {
        index
        for fold in folds
        for index in (*fold.train_indices, *fold.test_indices, *fold.excluded_indices)
    }
    if referenced_indices and max(referenced_indices) >= len(observations):
        raise ValueError("walk-forward fold references observations outside the input series")
    return tuple(observations[index] for index in test_indices)


def _require_integer(value: object, name: str, *, minimum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        qualifier = "positive" if minimum == 1 else "non-negative"
        raise ValueError(f"{name} must be a {qualifier} integer")
    return value
