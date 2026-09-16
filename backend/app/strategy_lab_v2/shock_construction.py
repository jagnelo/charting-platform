"""Deterministic construction of explicit stress-shock definitions.

This module expands a caller-supplied matrix of typed shock legs into stable,
content-addressed scenario definitions.  It does not apply shocks to market
data, infer cross-asset effects, or calculate stressed account equity; those
operations remain owned by the engine/account adapter that produces stress
observations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from itertools import product

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.decimal_math import DECIMAL_PRECISION, deterministic_decimal_math

SHOCK_CONSTRUCTION_DEFINITION_VERSION = (
    f"strategy-lab.shock-construction.v1.decimal{DECIMAL_PRECISION}-half-even"
)


def _finite(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field_name} must be a finite Decimal")


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class ShockOperation(StrEnum):
    ABSOLUTE = "absolute"
    RELATIVE = "relative"
    MULTIPLIER = "multiplier"
    BASIS_POINTS = "basis_points"


@dataclass(frozen=True, slots=True)
class ShockDimension:
    """One explicit shock axis and its allowed values."""

    field: str
    operation: ShockOperation
    values: tuple[Decimal, ...]
    unit: str
    scope: str = "instrument"

    def __post_init__(self) -> None:
        _nonempty(self.field, "field")
        if not isinstance(self.operation, ShockOperation):
            raise TypeError("operation must be a ShockOperation")
        values = tuple(self.values)
        if not values:
            raise ValueError("shock dimension requires at least one value")
        for value in values:
            _finite(value, "shock value")
        if len(values) != len(set(values)):
            raise ValueError("shock dimension values must be unique")
        _nonempty(self.unit, "unit")
        _nonempty(self.scope, "scope")
        object.__setattr__(self, "values", values)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ShockLeg:
    """One concrete operation in a fully expanded shock scenario."""

    field: str
    operation: ShockOperation
    value: Decimal
    unit: str
    scope: str

    def __post_init__(self) -> None:
        _nonempty(self.field, "field")
        if not isinstance(self.operation, ShockOperation):
            raise TypeError("operation must be a ShockOperation")
        _finite(self.value, "value")
        _nonempty(self.unit, "unit")
        _nonempty(self.scope, "scope")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ShockDefinition:
    """A complete explicit scenario definition, not its applied outcome."""

    scenario_id: str
    legs: tuple[ShockLeg, ...]
    definition_version: str = SHOCK_CONSTRUCTION_DEFINITION_VERSION

    def __post_init__(self) -> None:
        _nonempty(self.scenario_id, "scenario_id")
        legs = tuple(self.legs)
        if not legs:
            raise ValueError("shock definitions require at least one leg")
        if any(not isinstance(item, ShockLeg) for item in legs):
            raise TypeError("legs must contain ShockLeg values")
        keys = [(item.scope, item.field) for item in legs]
        if len(keys) != len(set(keys)):
            raise ValueError("shock legs must be unique per scope and field")
        _nonempty(self.definition_version, "definition_version")
        object.__setattr__(
            self,
            "legs",
            tuple(sorted(legs, key=lambda item: (item.scope, item.field))),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ShockScenarioPlan:
    """Stable expanded shock definitions with a construction identity."""

    definitions: tuple[ShockDefinition, ...]
    construction_version: str = SHOCK_CONSTRUCTION_DEFINITION_VERSION

    def __post_init__(self) -> None:
        definitions = tuple(self.definitions)
        if not definitions:
            raise ValueError("shock scenario plans require at least one definition")
        if any(not isinstance(item, ShockDefinition) for item in definitions):
            raise TypeError("definitions must contain ShockDefinition values")
        scenario_ids = [item.scenario_id for item in definitions]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("shock scenario ids must be unique")
        _nonempty(self.construction_version, "construction_version")
        object.__setattr__(
            self,
            "definitions",
            tuple(sorted(definitions, key=lambda item: item.scenario_id)),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@deterministic_decimal_math
def expand_shock_matrix(
    dimensions: Mapping[str, ShockDimension],
    *,
    max_scenarios: int = 10_000,
    scenario_prefix: str = "scenario",
) -> ShockScenarioPlan:
    """Expand explicit dimensions into stable scenario definitions.

    Dimension keys must equal their declared fields.  Cartesian-product order
    is canonicalized by field name; no value is synthesized or transformed.
    """

    if not dimensions:
        raise ValueError("shock construction requires at least one dimension")
    if (
        not isinstance(max_scenarios, int)
        or isinstance(max_scenarios, bool)
        or max_scenarios < 1
    ):
        raise ValueError("max_scenarios must be a positive integer")
    _nonempty(scenario_prefix, "scenario_prefix")
    ordered_names = tuple(sorted(dimensions))
    if any(not isinstance(name, str) or not name.strip() for name in ordered_names):
        raise ValueError("shock dimension names must be non-empty strings")
    ordered_dimensions: list[ShockDimension] = []
    for name in ordered_names:
        dimension = dimensions[name]
        if not isinstance(dimension, ShockDimension):
            raise TypeError("shock dimensions must contain ShockDimension values")
        if dimension.field != name:
            raise ValueError("shock dimension key must match its field")
        ordered_dimensions.append(dimension)
    total = 1
    for dimension in ordered_dimensions:
        total *= len(dimension.values)
        if total > max_scenarios:
            raise ValueError(f"shock matrix exceeds max_scenarios={max_scenarios}")

    definitions: list[ShockDefinition] = []
    for index, values in enumerate(product(*(dimension.values for dimension in ordered_dimensions))):
        legs = tuple(
            ShockLeg(
                field=dimension.field,
                operation=dimension.operation,
                value=value,
                unit=dimension.unit,
                scope=dimension.scope,
            )
            for dimension, value in zip(ordered_dimensions, values, strict=True)
        )
        definitions.append(ShockDefinition(f"{scenario_prefix}-{index:06d}", legs))
    return ShockScenarioPlan(tuple(definitions))
