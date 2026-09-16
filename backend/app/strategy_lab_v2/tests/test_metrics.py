from __future__ import annotations

from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    METRIC_CALCULATION_CONTRACT_VERSION,
    MetricBasis,
    MetricCalculationDefinition,
    MetricEvidenceReference,
    MetricValue,
)
from app.strategy_lab_v2.metrics import (
    METRIC_DEFINITION_VERSION,
    calculate_performance_metrics,
    calculate_trade_metrics,
)


def _by_name(values: tuple[object, ...]) -> dict[str, object]:
    return {item.name: item for item in values}  # type: ignore[attr-defined]


def _metric_dividend(numerator: int, denominator: int) -> Decimal:
    with localcontext() as decimal_context:
        decimal_context.prec = 34
        return Decimal(numerator) / Decimal(denominator)


def test_performance_metrics_report_currency_drawdown_recovery_and_empirical_tail() -> None:
    metrics = _by_name(
        calculate_performance_metrics(
            (Decimal("110"), Decimal("100"), Decimal("120")),
            initial_capital=Decimal("100"),
            base_currency="usd",
            periods_per_year=3,
            historical_confidence_level=Decimal("0.95"),
            basis=MetricBasis.NET,
        )
    )

    assert metrics["total_pnl"].value == Decimal("20")  # type: ignore[attr-defined]
    assert metrics["total_pnl"].unit == "currency:USD"  # type: ignore[attr-defined]
    assert metrics["total_return"].value == Decimal("0.2")  # type: ignore[attr-defined]
    assert metrics["maximum_drawdown_duration"].value == Decimal("1")  # type: ignore[attr-defined]
    assert metrics["recovery_factor"].value == Decimal("2.0")  # type: ignore[attr-defined]
    with localcontext() as decimal_context:
        decimal_context.prec = 34
        expected_loss = -(Decimal(100) / Decimal(110) - Decimal(1))
    assert metrics["historical_value_at_risk"].value == expected_loss  # type: ignore[attr-defined]
    assert metrics["historical_expected_shortfall"].value == expected_loss  # type: ignore[attr-defined]
    assert metrics["historical_expected_shortfall"].calculation_basis.startswith(  # type: ignore[attr-defined]
        "non-negative empirical mean loss of 1 worst observations at 0.95 confidence"
    )
    assert all(
        item.definition_version == METRIC_DEFINITION_VERSION
        for item in calculate_performance_metrics(
            (Decimal("110"), Decimal("100"), Decimal("120")),
            initial_capital=Decimal("100"),
            base_currency="USD",
            periods_per_year=3,
        )
    )


def test_performance_tail_metrics_clip_positive_returns_and_single_samples_are_null() -> None:
    positive = _by_name(
        calculate_performance_metrics(
            (Decimal("110"), Decimal("121")),
            initial_capital=Decimal("100"),
            base_currency="USD",
            periods_per_year=252,
        )
    )
    assert positive["historical_value_at_risk"].value == Decimal(0)  # type: ignore[attr-defined]
    assert positive["historical_expected_shortfall"].value == Decimal(0)  # type: ignore[attr-defined]

    one_sample = _by_name(
        calculate_performance_metrics(
            (Decimal("90"),),
            initial_capital=Decimal("100"),
            base_currency="USD",
            periods_per_year=252,
        )
    )
    assert one_sample["historical_value_at_risk"].value is None  # type: ignore[attr-defined]
    assert one_sample["historical_value_at_risk"].null_reason == (  # type: ignore[attr-defined]
        "at least two return observations are required"
    )
    assert one_sample["calmar_ratio"].value is not None  # type: ignore[attr-defined]
    assert one_sample["maximum_drawdown"].value == Decimal("-0.1")  # type: ignore[attr-defined]


def test_equity_curve_uses_post_start_fixed_cadence_marks_not_opening_balance() -> None:
    metrics = _by_name(
        calculate_performance_metrics(
            (Decimal("110"), Decimal("121")),
            initial_capital=Decimal("100"),
            base_currency="USD",
            periods_per_year=252,
        )
    )

    assert metrics["annualized_return"].sample_size == 2  # type: ignore[attr-defined]
    assert metrics["annualized_volatility"].sample_size == 2  # type: ignore[attr-defined]
    assert metrics["sharpe_ratio"].sample_size == 2  # type: ignore[attr-defined]
    assert metrics["annualized_return"].annualization_basis == "252 observed periods per year"  # type: ignore[attr-defined]


def test_structured_calculation_identity_excludes_values_and_run_evidence() -> None:
    first = _by_name(
        calculate_performance_metrics(
            (Decimal("110"), Decimal("104"), Decimal("117")),
            initial_capital=Decimal("100"),
            base_currency="USD",
            periods_per_year=252,
            risk_free_return_per_period=Decimal("0.001"),
        )
    )
    second = _by_name(
        calculate_performance_metrics(
            (Decimal("112"), Decimal("103"), Decimal("110"), Decimal("119")),
            initial_capital=Decimal("100"),
            base_currency="USD",
            periods_per_year=252,
            risk_free_return_per_period=Decimal("0.001"),
        )
    )

    first_sharpe = first["sharpe_ratio"]
    second_sharpe = second["sharpe_ratio"]
    assert first_sharpe.calculation_definition.contract_version == (  # type: ignore[attr-defined]
        METRIC_CALCULATION_CONTRACT_VERSION
    )
    assert first_sharpe.calculation_definition.formula_id == (  # type: ignore[attr-defined]
        "strategy-lab.metrics/sharpe_ratio"
    )
    assert first_sharpe.calculation_definition.parameters[  # type: ignore[attr-defined]
        "risk_free_return_per_period"
    ] == Decimal("0.001")
    assert first_sharpe.calculation_fingerprint == second_sharpe.calculation_fingerprint  # type: ignore[attr-defined]
    assert first_sharpe.value != second_sharpe.value  # type: ignore[attr-defined]
    assert first_sharpe.sample_size != second_sharpe.sample_size  # type: ignore[attr-defined]
    assert first_sharpe.evidence_references != second_sharpe.evidence_references  # type: ignore[attr-defined]
    assert first_sharpe.evidence_references[0].role == "calculator_input"  # type: ignore[attr-defined]

    changed_risk_free = _by_name(
        calculate_performance_metrics(
            (Decimal("110"), Decimal("104"), Decimal("117")),
            initial_capital=Decimal("100"),
            base_currency="USD",
            periods_per_year=252,
            risk_free_return_per_period=Decimal("0.002"),
        )
    )
    assert (
        first_sharpe.calculation_fingerprint  # type: ignore[attr-defined]
        != changed_risk_free["sharpe_ratio"].calculation_fingerprint  # type: ignore[attr-defined]
    )
    assert (
        first["total_return"].calculation_fingerprint  # type: ignore[attr-defined]
        == changed_risk_free["total_return"].calculation_fingerprint  # type: ignore[attr-defined]
    )

    changed_annualization = _by_name(
        calculate_performance_metrics(
            (Decimal("110"), Decimal("104"), Decimal("117")),
            initial_capital=Decimal("100"),
            base_currency="USD",
            periods_per_year=12,
            risk_free_return_per_period=Decimal("0.001"),
        )
    )
    assert (
        first["total_return"].calculation_fingerprint  # type: ignore[attr-defined]
        == changed_annualization["total_return"].calculation_fingerprint  # type: ignore[attr-defined]
    )
    assert (
        first["annualized_return"].calculation_fingerprint  # type: ignore[attr-defined]
        != changed_annualization["annualized_return"].calculation_fingerprint  # type: ignore[attr-defined]
    )
    assert first["annualized_return"].value != changed_annualization["annualized_return"].value  # type: ignore[attr-defined]


def test_calculation_definition_is_versioned_immutable_and_legacy_is_fail_closed() -> None:
    first = MetricCalculationDefinition(
        "test.return",
        METRIC_CALCULATION_CONTRACT_VERSION,
        {"confidence": Decimal("0.95"), "labels": ["close", "to-close"]},
    )
    second = MetricCalculationDefinition(
        "test.return",
        METRIC_CALCULATION_CONTRACT_VERSION,
        {"confidence": Decimal("0.975"), "labels": ["close", "to-close"]},
    )
    assert first.fingerprint != second.fingerprint
    assert first.parameters["labels"] == ("close", "to-close")
    with pytest.raises(TypeError):
        first.parameters["confidence"] = Decimal("0.9")  # type: ignore[index]

    evidence = MetricEvidenceReference("test_observations", content_digest([1, 2, 3]))
    legacy = MetricValue(
        "return",
        Decimal("0.1"),
        "fraction",
        "strategy-lab.metrics.v2",
        MetricBasis.NET,
        3,
    )
    assert legacy.calculation_fingerprint is None
    assert evidence.digest == content_digest([1, 2, 3])


def test_trade_metrics_cover_expectancy_quality_streaks_and_explicit_currency() -> None:
    metrics = _by_name(
        calculate_trade_metrics(
            (
                Decimal("20"),
                Decimal("-10"),
                Decimal("0"),
                Decimal("30"),
                Decimal("-15"),
                Decimal("-5"),
            ),
            base_currency="EUR",
            basis=MetricBasis.GROSS,
        )
    )

    assert metrics["trade_count"].value == Decimal(6)  # type: ignore[attr-defined]
    assert metrics["winning_trade_pnl"].value == Decimal(50)  # type: ignore[attr-defined]
    assert metrics["losing_trade_pnl_magnitude"].value == Decimal(30)  # type: ignore[attr-defined]
    assert metrics["win_rate"].value == _metric_dividend(2, 6)  # type: ignore[attr-defined]
    assert metrics["break_even_rate"].value == _metric_dividend(1, 6)  # type: ignore[attr-defined]
    assert metrics["average_trade_pnl"].value == _metric_dividend(20, 6)  # type: ignore[attr-defined]
    assert metrics["average_winning_trade_pnl"].value == Decimal(25)  # type: ignore[attr-defined]
    assert metrics["average_losing_trade_pnl"].value == Decimal(-10)  # type: ignore[attr-defined]
    assert metrics["largest_winning_trade_pnl"].value == Decimal(30)  # type: ignore[attr-defined]
    assert metrics["largest_losing_trade_pnl"].value == Decimal(-15)  # type: ignore[attr-defined]
    assert metrics["win_loss_ratio"].value == Decimal("2.5")  # type: ignore[attr-defined]
    assert metrics["profit_factor"].value == _metric_dividend(50, 30)  # type: ignore[attr-defined]
    assert metrics["max_consecutive_wins"].value == Decimal(1)  # type: ignore[attr-defined]
    assert metrics["max_consecutive_losses"].value == Decimal(2)  # type: ignore[attr-defined]
    assert metrics["average_trade_pnl"].unit == "currency:EUR"  # type: ignore[attr-defined]
    assert metrics["average_trade_pnl"].basis is MetricBasis.GROSS  # type: ignore[attr-defined]


def test_trade_metrics_have_defined_nulls_for_no_wins_or_no_losses() -> None:
    only_losses = _by_name(
        calculate_trade_metrics((Decimal("-2"), Decimal("0")), base_currency="USD")
    )
    assert only_losses["average_winning_trade_pnl"].value is None  # type: ignore[attr-defined]
    assert only_losses["average_winning_trade_pnl"].null_reason == "no winning trades"  # type: ignore[attr-defined]
    assert only_losses["win_loss_ratio"].value is None  # type: ignore[attr-defined]
    assert only_losses["win_loss_ratio"].null_reason == "no winning trades"  # type: ignore[attr-defined]

    only_wins = _by_name(calculate_trade_metrics((Decimal("2"), Decimal("3")), base_currency="USD"))
    assert only_wins["profit_factor"].value is None  # type: ignore[attr-defined]
    assert only_wins["profit_factor"].null_reason == "no losing trades"  # type: ignore[attr-defined]
    assert only_wins["win_loss_ratio"].value is None  # type: ignore[attr-defined]

    no_trades = _by_name(calculate_trade_metrics((), base_currency="USD"))
    assert no_trades["trade_count"].value == Decimal(0)  # type: ignore[attr-defined]
    assert no_trades["win_rate"].value is None  # type: ignore[attr-defined]
    assert no_trades["winning_trade_pnl"].value == Decimal(0)  # type: ignore[attr-defined]


def test_metrics_reject_ambiguous_currency_and_invalid_tail_confidence() -> None:
    with pytest.raises(ValueError, match="three-letter"):
        calculate_trade_metrics((Decimal(1),), base_currency="US$")
    with pytest.raises(ValueError, match="strictly between"):
        calculate_performance_metrics(
            (Decimal("101"), Decimal("102")),
            initial_capital=Decimal("100"),
            base_currency="USD",
            periods_per_year=252,
            historical_confidence_level=Decimal(1),
        )


def test_metric_methods_record_parameters_and_ignore_ambient_decimal_context() -> None:
    equity_curve = (Decimal("110"), Decimal("100"), Decimal("120"))
    baseline = calculate_performance_metrics(
        equity_curve,
        initial_capital=Decimal("100"),
        base_currency="USD",
        periods_per_year=252,
        risk_free_return_per_period=Decimal("0.001"),
    )
    with localcontext() as decimal_context:
        decimal_context.prec = 6
        decimal_context.rounding = ROUND_DOWN
        constrained = calculate_performance_metrics(
            equity_curve,
            initial_capital=Decimal("100"),
            base_currency="USD",
            periods_per_year=252,
            risk_free_return_per_period=Decimal("0.001"),
        )
    assert constrained == baseline

    by_name = _by_name(baseline)
    assert "risk-free target=0.001" in by_name["sharpe_ratio"].calculation_basis  # type: ignore[attr-defined]
    assert "downside target=0.001" in by_name["sortino_ratio"].calculation_basis  # type: ignore[attr-defined]
    assert all(item.calculation_basis for item in baseline)  # type: ignore[attr-defined]


def test_metric_basis_rejects_values_outside_the_gross_net_contract() -> None:
    with pytest.raises(TypeError, match="MetricBasis"):
        calculate_trade_metrics((Decimal("1"),), base_currency="USD", basis="nonsense")  # type: ignore[arg-type]
