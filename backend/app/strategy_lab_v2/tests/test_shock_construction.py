from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from app.strategy_lab_v2.shock_construction import (
    ShockDefinition,
    ShockDimension,
    ShockLeg,
    ShockOperation,
    ShockScenarioPlan,
    expand_shock_matrix,
)


def _dimensions():
    return {
        "equity_return": ShockDimension(
            "equity_return",
            ShockOperation.RELATIVE,
            (Decimal("-0.1"), Decimal("0")),
            "fraction",
        ),
        "volatility": ShockDimension(
            "volatility",
            ShockOperation.BASIS_POINTS,
            (Decimal("25"), Decimal("50")),
            "bps",
        ),
    }


def test_shock_matrix_expands_explicit_dimensions_deterministically() -> None:
    plan = expand_shock_matrix(_dimensions(), scenario_prefix="stress")

    assert isinstance(plan, ShockScenarioPlan)
    assert [item.scenario_id for item in plan.definitions] == [
        "stress-000000",
        "stress-000001",
        "stress-000002",
        "stress-000003",
    ]
    assert [(item.field, item.value) for item in plan.definitions[0].legs] == [
        ("equity_return", Decimal("-0.1")),
        ("volatility", Decimal("25")),
    ]

    reordered = expand_shock_matrix(
        {name: _dimensions()[name] for name in reversed(tuple(_dimensions()))},
        scenario_prefix="stress",
    )
    assert reordered == plan


def test_shock_construction_preserves_identity_without_applying_values() -> None:
    plan = expand_shock_matrix(_dimensions())
    assert plan.definitions[0].fingerprint.startswith("sha256:")
    assert all(item.definition_version for item in plan.definitions)
    assert plan.fingerprint.startswith("sha256:")


def test_shock_construction_rejects_ambiguous_or_unbounded_inputs() -> None:
    with pytest.raises(ValueError, match="key must match"):
        expand_shock_matrix(
            {
                "return": ShockDimension(
                    "other", ShockOperation.RELATIVE, (Decimal("0.1"),), "fraction"
                )
            }
        )
    with pytest.raises(ValueError, match="exceeds"):
        expand_shock_matrix(_dimensions(), max_scenarios=3)
    with pytest.raises(ValueError, match="at least one value"):
        ShockDimension("return", ShockOperation.RELATIVE, (), "fraction")
    with pytest.raises(ValueError, match="unique per scope"):
        ShockDefinition(
            "duplicate",
            (
                ShockLeg("return", ShockOperation.RELATIVE, Decimal("0.1"), "fraction", "account"),
                ShockLeg("return", ShockOperation.ABSOLUTE, Decimal("1"), "USD", "account"),
            ),
        )


def test_shock_construction_requires_typed_values() -> None:
    with pytest.raises(TypeError, match="operation"):
        ShockDimension("return", "relative", (Decimal("0.1"),), "fraction")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite"):
        ShockLeg(
            "return", ShockOperation.RELATIVE, Decimal("NaN"), "fraction", "instrument"
        )
    with pytest.raises(ValueError, match="scenario_prefix"):
        expand_shock_matrix(_dimensions(), scenario_prefix=" ")


def test_shock_construction_is_independent_of_decimal_context() -> None:
    baseline = expand_shock_matrix(_dimensions())
    with localcontext() as decimal_context:
        decimal_context.prec = 6
        decimal_context.rounding = ROUND_DOWN
        constrained = expand_shock_matrix(_dimensions())
    assert constrained == baseline
