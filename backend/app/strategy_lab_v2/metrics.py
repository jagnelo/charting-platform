"""Versioned Decimal metric calculations over authoritative result series."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.strategy_lab_v2.contracts import MetricBasis, MetricValue

METRIC_DEFINITION_VERSION = "strategy-lab.metrics.v1"


def _value(
    name: str,
    value: Decimal | None,
    *,
    unit: str,
    basis: MetricBasis,
    sample_size: int,
    annualization_basis: str | None = None,
    null_reason: str | None = None,
) -> MetricValue:
    return MetricValue(
        name=name,
        value=value,
        unit=unit,
        definition_version=METRIC_DEFINITION_VERSION,
        basis=basis,
        sample_size=sample_size,
        annualization_basis=annualization_basis,
        null_reason=null_reason,
    )


def _validate_decimal_series(values: Sequence[Decimal], field_name: str) -> tuple[Decimal, ...]:
    series = tuple(values)
    if any(not isinstance(value, Decimal) or not value.is_finite() for value in series):
        raise ValueError(f"{field_name} must contain only finite Decimal values")
    return series


def calculate_performance_metrics(
    equity_curve: Sequence[Decimal],
    *,
    initial_capital: Decimal,
    periods_per_year: int,
    risk_free_return_per_period: Decimal = Decimal(0),
    basis: MetricBasis = MetricBasis.NET,
) -> tuple[MetricValue, ...]:
    """Calculate basic return/risk metrics from simulator account-equity samples.

    The input series must come from native engine account/equity output. This
    module intentionally does not synthesize fills or model execution.
    """

    curve = _validate_decimal_series(equity_curve, "equity_curve")
    if (
        not isinstance(initial_capital, Decimal)
        or not initial_capital.is_finite()
        or initial_capital <= 0
    ):
        raise ValueError("initial_capital must be a finite positive Decimal")
    if (
        not isinstance(periods_per_year, int)
        or isinstance(periods_per_year, bool)
        or periods_per_year < 1
    ):
        raise ValueError("periods_per_year must be positive")
    if (
        not isinstance(risk_free_return_per_period, Decimal)
        or not risk_free_return_per_period.is_finite()
    ):
        raise ValueError("risk-free return must be finite")
    if any(value < 0 for value in curve):
        raise ValueError("equity curve cannot contain negative account equity")
    if not curve:
        raise ValueError("equity_curve must contain at least one observation")

    return_values: list[Decimal] = []
    previous = initial_capital
    for current in curve:
        if previous == 0:
            if current > 0:
                raise ValueError("equity cannot recover from zero without a new capital event")
            break
        return_values.append(current / previous - Decimal(1))
        previous = current
    returns = tuple(return_values)
    annualization_basis = f"{periods_per_year} observed periods per year"
    final_equity = curve[-1]
    total_return = final_equity / initial_capital - Decimal(1)
    peak = initial_capital
    max_drawdown = Decimal(0)
    for equity in curve:
        peak = max(peak, equity)
        if peak > 0:
            max_drawdown = min(max_drawdown, equity / peak - Decimal(1))

    metrics = [
        _value(
            "total_return",
            total_return,
            unit="fraction",
            basis=basis,
            sample_size=len(curve),
        ),
        _value(
            "maximum_drawdown",
            max_drawdown,
            unit="fraction",
            basis=basis,
            sample_size=len(curve),
        ),
    ]

    if returns and final_equity > 0:
        annualized_return = (final_equity / initial_capital) ** (
            Decimal(periods_per_year) / Decimal(len(returns))
        ) - Decimal(1)
        metrics.append(
            _value(
                "annualized_return",
                annualized_return,
                unit="fraction",
                basis=basis,
                sample_size=len(returns),
                annualization_basis=annualization_basis,
            )
        )
    else:
        metrics.append(
            _value(
                "annualized_return",
                None,
                unit="fraction",
                basis=basis,
                sample_size=len(returns),
                annualization_basis=annualization_basis,
                null_reason="non-positive terminal equity or no return observations",
            )
        )

    if len(returns) < 2:
        metrics.extend(
            (
                _value(
                    "annualized_volatility",
                    None,
                    unit="fraction",
                    basis=basis,
                    sample_size=len(returns),
                    annualization_basis=annualization_basis,
                    null_reason="at least two return observations are required",
                ),
                _value(
                    "sharpe_ratio",
                    None,
                    unit="ratio",
                    basis=basis,
                    sample_size=len(returns),
                    annualization_basis=annualization_basis,
                    null_reason="at least two return observations are required",
                ),
                _value(
                    "sortino_ratio",
                    None,
                    unit="ratio",
                    basis=basis,
                    sample_size=len(returns),
                    annualization_basis=annualization_basis,
                    null_reason="at least two return observations are required",
                ),
            )
        )
        return tuple(metrics)

    mean_return = sum(returns, Decimal(0)) / Decimal(len(returns))
    sample_variance = sum(((value - mean_return) ** 2 for value in returns), Decimal(0)) / Decimal(
        len(returns) - 1
    )
    annualized_volatility = (sample_variance * Decimal(periods_per_year)).sqrt()
    metrics.append(
        _value(
            "annualized_volatility",
            annualized_volatility,
            unit="fraction",
            basis=basis,
            sample_size=len(returns),
            annualization_basis=annualization_basis,
        )
    )
    if sample_variance == 0:
        sharpe = None
        sharpe_null_reason = "return observations have zero sample variance"
    else:
        sharpe = (
            (mean_return - risk_free_return_per_period)
            / sample_variance.sqrt()
            * Decimal(periods_per_year).sqrt()
        )
        sharpe_null_reason = None
    metrics.append(
        _value(
            "sharpe_ratio",
            sharpe,
            unit="ratio",
            basis=basis,
            sample_size=len(returns),
            annualization_basis=annualization_basis,
            null_reason=sharpe_null_reason,
        )
    )

    downside = tuple(min(value - risk_free_return_per_period, Decimal(0)) for value in returns)
    downside_deviation = (
        sum((value**2 for value in downside), Decimal(0)) / Decimal(len(returns))
    ).sqrt()
    if downside_deviation == 0:
        sortino = None
        sortino_null_reason = "no downside deviation below the periodic target"
    else:
        sortino = (
            (mean_return - risk_free_return_per_period)
            / downside_deviation
            * Decimal(periods_per_year).sqrt()
        )
        sortino_null_reason = None
    metrics.append(
        _value(
            "sortino_ratio",
            sortino,
            unit="ratio",
            basis=basis,
            sample_size=len(returns),
            annualization_basis=annualization_basis,
            null_reason=sortino_null_reason,
        )
    )
    return tuple(metrics)


def calculate_trade_metrics(
    trade_pnls: Sequence[Decimal], *, basis: MetricBasis = MetricBasis.NET
) -> tuple[MetricValue, ...]:
    """Summarize completed trade P&L values supplied by the authoritative engine."""

    pnls = _validate_decimal_series(trade_pnls, "trade_pnls")
    count = len(pnls)
    if count == 0:
        return (
            _value(
                "trade_count",
                Decimal(0),
                unit="trades",
                basis=basis,
                sample_size=0,
            ),
            _value(
                "win_rate",
                None,
                unit="fraction",
                basis=basis,
                sample_size=0,
                null_reason="no completed trades",
            ),
            _value(
                "average_trade_pnl",
                None,
                unit="currency",
                basis=basis,
                sample_size=0,
                null_reason="no completed trades",
            ),
            _value(
                "profit_factor",
                None,
                unit="ratio",
                basis=basis,
                sample_size=0,
                null_reason="no completed trades",
            ),
        )

    wins = tuple(value for value in pnls if value > 0)
    losses = tuple(value for value in pnls if value < 0)
    gross_profit = sum(wins, Decimal(0))
    gross_loss = -sum(losses, Decimal(0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    return (
        _value("trade_count", Decimal(count), unit="trades", basis=basis, sample_size=count),
        _value(
            "win_rate",
            Decimal(len(wins)) / Decimal(count),
            unit="fraction",
            basis=basis,
            sample_size=count,
        ),
        _value(
            "average_trade_pnl",
            sum(pnls, Decimal(0)) / Decimal(count),
            unit="currency",
            basis=basis,
            sample_size=count,
        ),
        _value(
            "profit_factor",
            profit_factor,
            unit="ratio",
            basis=basis,
            sample_size=count,
            null_reason="no losing trades" if profit_factor is None else None,
        ),
    )
