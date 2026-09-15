"""Versioned Decimal metric calculations over authoritative result series."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import ROUND_CEILING, Decimal

from app.strategy_lab_v2.allocation import PortfolioExposureSnapshot
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    MetricBasis,
    MetricValue,
)
from app.strategy_lab_v2.decimal_math import DECIMAL_PRECISION, deterministic_decimal_math
from app.strategy_lab_v2.observations import (
    ComponentPnlObservation,
    CostReportStatus,
    ExecutionCostKind,
    FillCostObservation,
    ObservationPoint,
    PortfolioPnlObservation,
)

METRIC_DEFINITION_VERSION = "strategy-lab.metrics.v3"
_METRIC_FORMULAS = {
    "total_pnl": "terminal equity minus initial capital; external cash flows are not modeled",
    "total_return": "terminal equity divided by initial capital minus one",
    "maximum_drawdown": "minimum observed equity divided by running peak minus one",
    "maximum_drawdown_duration": "longest count of sampled observations below the running peak",
    "ulcer_index": "square root of the mean squared observed drawdown fractions",
    "annualized_return": "terminal equity growth compounded by periods_per_year / return_count",
    "calmar_ratio": "annualized return divided by the absolute maximum drawdown fraction",
    "recovery_factor": "net account P&L in base currency divided by maximum peak-to-trough loss in base currency",
    "annualized_volatility": "sample standard deviation of simple returns multiplied by square root of periods_per_year",
    "sharpe_ratio": "mean simple return less the periodic risk-free target, divided by sample standard deviation and annualized by square root of periods_per_year",
    "sortino_ratio": "mean simple return less the periodic target, divided by downside RMS and annualized by square root of periods_per_year",
    "historical_value_at_risk": "non-negative loss at the empirical nearest-rank lower-tail boundary",
    "historical_expected_shortfall": "non-negative mean loss across the empirical nearest-rank worst tail",
    "trade_count": "number of completed engine-reported trades",
    "winning_trade_pnl": "sum of positive engine-reported trade P&L values",
    "losing_trade_pnl_magnitude": "absolute sum of negative engine-reported trade P&L values",
    "win_rate": "profitable completed trades divided by completed trade count",
    "break_even_rate": "zero-P&L completed trades divided by completed trade count",
    "average_trade_pnl": "arithmetic mean of completed engine-reported trade P&L values",
    "average_winning_trade_pnl": "arithmetic mean of positive engine-reported trade P&L values",
    "average_losing_trade_pnl": "arithmetic mean of negative engine-reported trade P&L values",
    "largest_winning_trade_pnl": "maximum positive engine-reported trade P&L value",
    "largest_losing_trade_pnl": "minimum negative engine-reported trade P&L value",
    "win_loss_ratio": "average winning trade P&L divided by absolute average losing trade P&L",
    "profit_factor": "sum of positive trade P&L divided by absolute sum of negative trade P&L",
    "max_consecutive_wins": "longest contiguous sequence of positive trade P&L observations",
    "max_consecutive_losses": "longest contiguous sequence of negative trade P&L observations",
}


def _value(
    name: str,
    value: Decimal | None,
    *,
    unit: str,
    basis: MetricBasis,
    sample_size: int,
    annualization_basis: str | None = None,
    calculation_basis: str | None = None,
    null_reason: str | None = None,
) -> MetricValue:
    if calculation_basis is None:
        try:
            calculation_basis = _METRIC_FORMULAS[name]
        except KeyError as error:
            raise ValueError(f"no calculation-basis definition registered for {name!r}") from error
    decimal_context_basis = (
        f"Decimal precision={DECIMAL_PRECISION}; rounding=ROUND_HALF_EVEN"
    )
    if calculation_basis is None:
        calculation_basis = decimal_context_basis
    else:
        calculation_basis = f"{calculation_basis}; {decimal_context_basis}"
    return MetricValue(
        name=name,
        value=value,
        unit=unit,
        definition_version=METRIC_DEFINITION_VERSION,
        basis=basis,
        sample_size=sample_size,
        annualization_basis=annualization_basis,
        calculation_basis=calculation_basis,
        null_reason=null_reason,
    )


def _validate_decimal_series(values: Sequence[Decimal], field_name: str) -> tuple[Decimal, ...]:
    series = tuple(values)
    if any(not isinstance(value, Decimal) or not value.is_finite() for value in series):
        raise ValueError(f"{field_name} must contain only finite Decimal values")
    return series


def _currency_code(value: str) -> str:
    if not isinstance(value, str) or len(value) != 3 or not value.isascii() or not value.isalpha():
        raise ValueError("base_currency must be a three-letter ISO-style code")
    return value.upper()


@deterministic_decimal_math
def calculate_performance_metrics(
    equity_curve: Sequence[Decimal],
    *,
    initial_capital: Decimal,
    base_currency: str,
    periods_per_year: int,
    risk_free_return_per_period: Decimal = Decimal(0),
    historical_confidence_level: Decimal = Decimal("0.95"),
    basis: MetricBasis = MetricBasis.NET,
) -> tuple[MetricValue, ...]:
    """Calculate versioned account return, drawdown, and tail-risk summaries.

    The input series must contain only equally spaced post-start marks from
    native engine account/equity output; do not include the opening balance,
    which is supplied separately as `initial_capital`. `periods_per_year` must
    match that sampling cadence. Timestamped/irregular observations are not
    modeled here. This module intentionally does not synthesize fills or model
    execution. Arithmetic uses a fixed 34-digit ROUND_HALF_EVEN Decimal context. Historical
    tail metrics use the empirical nearest-rank worst-tail observation set, with
    `ceil(n * (1 - confidence))` observations and no interpolation. P&L and
    returns assume the series contains no external deposits or withdrawals.
    """

    curve = _validate_decimal_series(equity_curve, "equity_curve")
    currency = _currency_code(base_currency)
    if not isinstance(basis, MetricBasis):
        raise TypeError("basis must be a MetricBasis")
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
        or risk_free_return_per_period <= Decimal(-1)
    ):
        raise ValueError("risk-free return must be finite and greater than -1")
    if (
        not isinstance(historical_confidence_level, Decimal)
        or not historical_confidence_level.is_finite()
        or historical_confidence_level <= 0
        or historical_confidence_level >= 1
    ):
        raise ValueError("historical_confidence_level must be strictly between zero and one")
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
    max_drawdown_amount = Decimal(0)
    drawdowns: list[Decimal] = []
    current_drawdown_duration = 0
    max_drawdown_duration = 0
    for equity in curve:
        peak = max(peak, equity)
        if peak > 0:
            drawdown = equity / peak - Decimal(1)
            drawdowns.append(drawdown)
            max_drawdown = min(max_drawdown, drawdown)
            max_drawdown_amount = max(max_drawdown_amount, peak - equity)
            if drawdown < 0:
                current_drawdown_duration += 1
                max_drawdown_duration = max(max_drawdown_duration, current_drawdown_duration)
            else:
                current_drawdown_duration = 0

    ulcer_index = (
        sum((drawdown**2 for drawdown in drawdowns), Decimal(0)) / Decimal(len(drawdowns))
    ).sqrt()

    metrics = [
        _value(
            "total_pnl",
            final_equity - initial_capital,
            unit=f"currency:{currency}",
            basis=basis,
            sample_size=len(curve),
            calculation_basis="terminal equity minus initial capital; no external cash flows",
        ),
        _value(
            "total_return",
            total_return,
            unit="fraction",
            basis=basis,
            sample_size=len(curve),
            calculation_basis="terminal equity divided by initial capital minus one",
        ),
        _value(
            "maximum_drawdown",
            max_drawdown,
            unit="fraction",
            basis=basis,
            sample_size=len(curve),
            calculation_basis="equity versus running peak, including initial capital",
        ),
        _value(
            "maximum_drawdown_duration",
            Decimal(max_drawdown_duration),
            unit="periods",
            basis=basis,
            sample_size=len(curve),
            calculation_basis="consecutive sampled observations below running peak",
        ),
        _value(
            "ulcer_index",
            ulcer_index,
            unit="fraction",
            basis=basis,
            sample_size=len(curve),
            calculation_basis="square root of mean squared observed drawdown fractions",
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
        annualized_return = None
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

    calmar_null_reason: str | None
    recovery_null_reason: str | None
    if max_drawdown == 0:
        calmar = None
        calmar_null_reason = "maximum drawdown is zero"
        recovery_factor = None
        recovery_null_reason = "maximum drawdown is zero"
    else:
        calmar = (
            None
            if annualized_return is None
            else annualized_return / abs(max_drawdown)
        )
        calmar_null_reason = (
            "annualized return is unavailable" if calmar is None else None
        )
        recovery_factor = (final_equity - initial_capital) / max_drawdown_amount
        recovery_null_reason = None
    metrics.extend(
        (
            _value(
                "calmar_ratio",
                calmar,
                unit="ratio",
                basis=basis,
                sample_size=len(returns),
                annualization_basis=annualization_basis,
                calculation_basis=(
                    "annualized return divided by the absolute maximum drawdown fraction"
                ),
                null_reason=calmar_null_reason,
            ),
            _value(
                "recovery_factor",
                recovery_factor,
                unit="ratio",
                basis=basis,
                sample_size=len(curve),
                calculation_basis=(
                    "net account P&L in base currency divided by maximum peak-to-trough loss in base currency"
                ),
                null_reason=recovery_null_reason,
            ),
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
                _value(
                    "historical_value_at_risk",
                    None,
                    unit="fraction",
                    basis=basis,
                    sample_size=len(returns),
                    null_reason="at least two return observations are required",
                ),
                _value(
                    "historical_expected_shortfall",
                    None,
                    unit="fraction",
                    basis=basis,
                    sample_size=len(returns),
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
            calculation_basis=(
                "mean simple return less periodic risk-free target="
                f"{risk_free_return_per_period}; divided by sample standard deviation"
            ),
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
            calculation_basis=(
                "mean simple return less periodic downside target="
                f"{risk_free_return_per_period}; divided by root mean square downside"
            ),
            null_reason=sortino_null_reason,
        )
    )
    tail_observation_count = max(
        1,
        int(
            (Decimal(len(returns)) * (Decimal(1) - historical_confidence_level)).to_integral_value(
                rounding=ROUND_CEILING
            )
        ),
    )
    worst_returns = sorted(returns)[:tail_observation_count]
    value_at_risk = max(Decimal(0), -worst_returns[-1])
    expected_shortfall = max(
        Decimal(0), -sum(worst_returns, Decimal(0)) / Decimal(tail_observation_count)
    )
    metrics.extend(
        (
            _value(
                "historical_value_at_risk",
                value_at_risk,
                unit="fraction",
                basis=basis,
                sample_size=len(returns),
                calculation_basis=(
                    f"non-negative empirical nearest-rank tail loss at "
                    f"{historical_confidence_level} confidence"
                ),
            ),
            _value(
                "historical_expected_shortfall",
                expected_shortfall,
                unit="fraction",
                basis=basis,
                sample_size=len(returns),
                calculation_basis=(
                    f"non-negative empirical mean loss of {tail_observation_count} worst observations at "
                    f"{historical_confidence_level} confidence"
                ),
            ),
        )
    )
    return tuple(metrics)


@deterministic_decimal_math
def calculate_trade_metrics(
    trade_pnls: Sequence[Decimal], *, base_currency: str, basis: MetricBasis = MetricBasis.NET
) -> tuple[MetricValue, ...]:
    """Summarize engine-reported trade P&L with an explicit currency and basis."""

    pnls = _validate_decimal_series(trade_pnls, "trade_pnls")
    currency = _currency_code(base_currency)
    if not isinstance(basis, MetricBasis):
        raise TypeError("basis must be a MetricBasis")
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
                "winning_trade_pnl",
                Decimal(0),
                unit=f"currency:{currency}",
                basis=basis,
                sample_size=0,
            ),
            _value(
                "losing_trade_pnl_magnitude",
                Decimal(0),
                unit=f"currency:{currency}",
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
                "break_even_rate",
                None,
                unit="fraction",
                basis=basis,
                sample_size=0,
                null_reason="no completed trades",
            ),
            _value(
                "average_trade_pnl",
                None,
                unit=f"currency:{currency}",
                basis=basis,
                sample_size=0,
                null_reason="no completed trades",
            ),
            _value(
                "average_winning_trade_pnl",
                None,
                unit=f"currency:{currency}",
                basis=basis,
                sample_size=0,
                null_reason="no completed trades",
            ),
            _value(
                "average_losing_trade_pnl",
                None,
                unit=f"currency:{currency}",
                basis=basis,
                sample_size=0,
                null_reason="no completed trades",
            ),
            _value(
                "largest_winning_trade_pnl",
                None,
                unit=f"currency:{currency}",
                basis=basis,
                sample_size=0,
                null_reason="no completed trades",
            ),
            _value(
                "largest_losing_trade_pnl",
                None,
                unit=f"currency:{currency}",
                basis=basis,
                sample_size=0,
                null_reason="no completed trades",
            ),
            _value(
                "win_loss_ratio",
                None,
                unit="ratio",
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
            _value(
                "max_consecutive_wins",
                Decimal(0),
                unit="trades",
                basis=basis,
                sample_size=0,
            ),
            _value(
                "max_consecutive_losses",
                Decimal(0),
                unit="trades",
                basis=basis,
                sample_size=0,
            ),
        )

    wins = tuple(value for value in pnls if value > 0)
    losses = tuple(value for value in pnls if value < 0)
    break_even_count = count - len(wins) - len(losses)
    gross_profit = sum(wins, Decimal(0))
    gross_loss = -sum(losses, Decimal(0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    average_win = sum(wins, Decimal(0)) / Decimal(len(wins)) if wins else None
    average_loss = sum(losses, Decimal(0)) / Decimal(len(losses)) if losses else None
    win_loss_ratio = (
        average_win / abs(average_loss)
        if average_win is not None and average_loss is not None
        else None
    )
    max_consecutive_wins = 0
    max_consecutive_losses = 0
    current_wins = 0
    current_losses = 0
    for pnl in pnls:
        current_wins = current_wins + 1 if pnl > 0 else 0
        current_losses = current_losses + 1 if pnl < 0 else 0
        max_consecutive_wins = max(max_consecutive_wins, current_wins)
        max_consecutive_losses = max(max_consecutive_losses, current_losses)
    return (
        _value("trade_count", Decimal(count), unit="trades", basis=basis, sample_size=count),
        _value(
            "winning_trade_pnl",
            gross_profit,
            unit=f"currency:{currency}",
            basis=basis,
            sample_size=count,
        ),
        _value(
            "losing_trade_pnl_magnitude",
            gross_loss,
            unit=f"currency:{currency}",
            basis=basis,
            sample_size=count,
        ),
        _value(
            "win_rate",
            Decimal(len(wins)) / Decimal(count),
            unit="fraction",
            basis=basis,
            sample_size=count,
        ),
        _value(
            "break_even_rate",
            Decimal(break_even_count) / Decimal(count),
            unit="fraction",
            basis=basis,
            sample_size=count,
        ),
        _value(
            "average_trade_pnl",
            sum(pnls, Decimal(0)) / Decimal(count),
            unit=f"currency:{currency}",
            basis=basis,
            sample_size=count,
        ),
        _value(
            "average_winning_trade_pnl",
            average_win,
            unit=f"currency:{currency}",
            basis=basis,
            sample_size=len(wins),
            null_reason="no winning trades" if average_win is None else None,
        ),
        _value(
            "average_losing_trade_pnl",
            average_loss,
            unit=f"currency:{currency}",
            basis=basis,
            sample_size=len(losses),
            null_reason="no losing trades" if average_loss is None else None,
        ),
        _value(
            "largest_winning_trade_pnl",
            max(wins) if wins else None,
            unit=f"currency:{currency}",
            basis=basis,
            sample_size=len(wins),
            null_reason="no winning trades" if not wins else None,
        ),
        _value(
            "largest_losing_trade_pnl",
            min(losses) if losses else None,
            unit=f"currency:{currency}",
            basis=basis,
            sample_size=len(losses),
            null_reason="no losing trades" if not losses else None,
        ),
        _value(
            "win_loss_ratio",
            win_loss_ratio,
            unit="ratio",
            basis=basis,
            sample_size=count,
            null_reason=(
                "no winning trades"
                if not wins
                else "no losing trades" if not losses else None
            ),
        ),
        _value(
            "profit_factor",
            profit_factor,
            unit="ratio",
            basis=basis,
            sample_size=count,
            null_reason="no losing trades" if profit_factor is None else None,
        ),
        _value(
            "max_consecutive_wins",
            Decimal(max_consecutive_wins),
            unit="trades",
            basis=basis,
            sample_size=count,
        ),
        _value(
            "max_consecutive_losses",
            Decimal(max_consecutive_losses),
            unit="trades",
            basis=basis,
            sample_size=count,
        ),
    )


@deterministic_decimal_math
def calculate_exposure_utilization_metrics(
    observations: Sequence[PortfolioExposureSnapshot],
) -> tuple[MetricValue, ...]:
    """Summarize event-sampled cash-equity notional exposure to account equity.

    These are equally sample-weighted event marks, not time-weighted utilization
    or margin usage. The registered cash-equity valuation must be present for
    each observed instrument; other product risk models fail closed.
    """

    marks = tuple(observations)
    if not marks:
        raise ValueError("at least one portfolio exposure observation is required")
    if any(not isinstance(item, PortfolioExposureSnapshot) for item in marks):
        raise TypeError("observations must contain PortfolioExposureSnapshot values")
    portfolio_fingerprint = marks[0].portfolio_fingerprint
    run_attempt_id = marks[0].run_attempt_id
    base_currency = marks[0].base_currency
    points = tuple(ObservationPoint(item.event_time, item.event_sequence) for item in marks)
    if any(item.portfolio_fingerprint != portfolio_fingerprint for item in marks):
        raise ValueError("all exposure observations must belong to the same portfolio version")
    if any(item.run_attempt_id != run_attempt_id for item in marks):
        raise ValueError("all exposure observations must belong to the same run attempt")
    if any(item.base_currency != base_currency for item in marks):
        raise ValueError("all exposure observations must use the same base currency")
    if any(current <= previous for previous, current in zip(points, points[1:])):
        raise ValueError("exposure observations must be strictly ordered by event time and sequence")
    observation_digest = content_digest(marks)

    gross_ratios: list[Decimal] = []
    net_ratios: list[Decimal] = []
    cash_ratios: list[Decimal] = []
    for mark in marks:
        risk_models = {item.instrument_id: item.risk_model for item in mark.instrument_risk_models}
        required_instruments = {item.instrument_id for item in mark.positions}
        for instrument_id in required_instruments:
            risk_model = risk_models.get(instrument_id)
            if risk_model is None:
                raise ValueError(f"instrument {instrument_id!r} has no risk-model evidence")
            if risk_model != CASH_EQUITY_NOTIONAL_RISK_MODEL:
                raise ValueError(
                    f"instrument {instrument_id!r} uses an unsupported exposure risk model"
                )
        gross = sum(
            (abs(item.signed_base_risk_exposure) for item in mark.positions), Decimal(0)
        )
        net = sum(
            (item.signed_base_risk_exposure for item in mark.positions), Decimal(0)
        )
        gross_ratios.append(gross / mark.account_equity)
        net_ratios.append(net / mark.account_equity)
        cash_ratios.append(mark.account_cash_balance / mark.account_equity)

    sample_size = len(marks)
    return (
        _value(
            "average_gross_notional_to_equity",
            sum(gross_ratios, Decimal(0)) / Decimal(sample_size),
            unit="ratio",
            basis=MetricBasis.GROSS,
            sample_size=sample_size,
            calculation_basis=(
                "equally sample-weighted mean of cash-equity gross signed-base-notional "
                "exposure divided by contemporaneous account equity; not margin usage; "
                f"observations {observation_digest}"
            ),
        ),
        _value(
            "maximum_gross_notional_to_equity",
            max(gross_ratios),
            unit="ratio",
            basis=MetricBasis.GROSS,
            sample_size=sample_size,
            calculation_basis=(
                "maximum observed cash-equity gross signed-base-notional exposure "
                "divided by contemporaneous account equity; not margin usage; "
                f"observations {observation_digest}"
            ),
        ),
        _value(
            "average_net_notional_to_equity",
            sum(net_ratios, Decimal(0)) / Decimal(sample_size),
            unit="ratio",
            basis=MetricBasis.NET,
            sample_size=sample_size,
            calculation_basis=(
                "equally sample-weighted mean of signed account exposure divided by "
                f"contemporaneous account equity; observations {observation_digest}"
            ),
        ),
        _value(
            "maximum_absolute_net_notional_to_equity",
            max((abs(item) for item in net_ratios), default=Decimal(0)),
            unit="ratio",
            basis=MetricBasis.NET,
            sample_size=sample_size,
            calculation_basis=(
                "maximum absolute observed signed account exposure divided by "
                f"contemporaneous account equity; observations {observation_digest}"
            ),
        ),
        _value(
            "average_cash_balance_to_equity",
            sum(cash_ratios, Decimal(0)) / Decimal(sample_size),
            unit="ratio",
            basis=MetricBasis.NET,
            sample_size=sample_size,
            calculation_basis=(
                "equally sample-weighted mean account cash balance divided by "
                f"contemporaneous account equity; observations {observation_digest}"
            ),
        ),
    )


@deterministic_decimal_math
def calculate_execution_cost_metrics(
    fills: Sequence[FillCostObservation],
    *,
    base_currency: str,
) -> tuple[MetricValue, ...]:
    """Aggregate engine-reported fill notional and signed cash-effect costs.

    Cost effects are signed account cash flows: expenses are negative, rebates
    positive, and slippage must cite its explicit benchmark definition. Net cost
    is the negated total cash effect. Basis points use the supplied base-currency
    fill notionals as denominator; no costs or slippage are inferred here.
    """

    fill_values = tuple(fills)
    if any(not isinstance(item, FillCostObservation) for item in fill_values):
        raise TypeError("fills must contain FillCostObservation values")
    fill_ids = [item.fill_id for item in fill_values]
    if len(fill_ids) != len(set(fill_ids)):
        raise ValueError("fill ids must be unique in an execution-cost sample")
    fill_values = tuple(sorted(fill_values, key=lambda item: (item.point, item.fill_id)))
    currency = _currency_code(base_currency)
    if fill_values:
        portfolio_fingerprint = fill_values[0].portfolio_fingerprint
        run_attempt_id = fill_values[0].run_attempt_id
        if any(item.portfolio_fingerprint != portfolio_fingerprint for item in fill_values):
            raise ValueError("all fill observations must belong to the same portfolio version")
        if any(item.run_attempt_id != run_attempt_id for item in fill_values):
            raise ValueError("all fill observations must belong to the same run attempt")
        if any(item.base_currency != currency for item in fill_values):
            raise ValueError("all fills must use the requested account base currency")
    observation_digest = content_digest(fill_values)

    notional = sum((item.traded_base_notional for item in fill_values), Decimal(0))
    cash_effects: dict[ExecutionCostKind, Decimal] = {
        kind: Decimal(0) for kind in ExecutionCostKind
    }
    category_counts: dict[ExecutionCostKind, int] = {kind: 0 for kind in ExecutionCostKind}
    component_effects: dict[str, Decimal] = {}
    component_notionals: dict[str, Decimal] = {}
    component_cost_counts: dict[str, int] = {}
    component_cost_complete: dict[str, bool] = {}
    all_cost_count = 0
    complete_fill_count = 0
    partial_fill_count = 0
    unavailable_fill_count = 0
    for fill in fill_values:
        component_notionals[fill.component_id] = (
            component_notionals.get(fill.component_id, Decimal(0)) + fill.traded_base_notional
        )
        component_effects.setdefault(fill.component_id, Decimal(0))
        component_cost_counts.setdefault(fill.component_id, 0)
        component_cost_complete[fill.component_id] = (
            component_cost_complete.get(fill.component_id, True)
            and fill.cost_report_status is CostReportStatus.COMPLETE
        )
        if fill.cost_report_status is CostReportStatus.COMPLETE:
            complete_fill_count += 1
        elif fill.cost_report_status is CostReportStatus.PARTIAL:
            partial_fill_count += 1
        else:
            unavailable_fill_count += 1
        for cost in fill.costs:
            cash_effects[cost.kind] += cost.base_cash_effect
            category_counts[cost.kind] += 1
            all_cost_count += 1
            component_effects[fill.component_id] -= cost.base_cash_effect
            component_cost_counts[fill.component_id] += 1

    cost_reporting_complete = partial_fill_count == 0 and unavailable_fill_count == 0
    net_cost = (
        -sum(cash_effects.values(), Decimal(0)) if cost_reporting_complete else None
    )
    cost_bps = (
        None
        if notional == 0 or net_cost is None
        else net_cost / notional * Decimal(10000)
    )
    metrics = [
        _value(
            "fill_count",
            Decimal(len(fill_values)),
            unit="fills",
            basis=MetricBasis.NET,
            sample_size=len(fill_values),
            calculation_basis=(
                f"count of unique engine-reported fills; observations {observation_digest}"
            ),
        ),
        _value(
            "complete_cost_report_fill_count",
            Decimal(complete_fill_count),
            unit="fills",
            basis=MetricBasis.NET,
            sample_size=len(fill_values),
            calculation_basis="count of fills with explicitly complete engine cost reports",
        ),
        _value(
            "partial_cost_report_fill_count",
            Decimal(partial_fill_count),
            unit="fills",
            basis=MetricBasis.NET,
            sample_size=len(fill_values),
            calculation_basis="count of fills with explicitly partial engine cost reports",
        ),
        _value(
            "unavailable_cost_report_fill_count",
            Decimal(unavailable_fill_count),
            unit="fills",
            basis=MetricBasis.NET,
            sample_size=len(fill_values),
            calculation_basis="count of fills with unavailable engine cost reports",
        ),
        _value(
            "traded_base_notional",
            notional,
            unit=f"currency:{currency}",
            basis=MetricBasis.GROSS,
            sample_size=len(fill_values),
            calculation_basis=(
                "sum of engine-reported absolute fill notionals in account base currency; "
                f"observations {observation_digest}"
            ),
        ),
        _value(
            "net_execution_cost",
            net_cost,
            unit=f"currency:{currency}",
            basis=MetricBasis.NET,
            sample_size=all_cost_count,
            calculation_basis=(
                "negative sum of engine-reported fill cash effects converted to account base currency; "
                f"observations {observation_digest}"
            ),
            null_reason=(
                "one or more fill cost reports are incomplete"
                if net_cost is None
                else None
            ),
        ),
        _value(
            "execution_cost_basis_points",
            cost_bps,
            unit="basis_points",
            basis=MetricBasis.NET,
            sample_size=len(fill_values),
            calculation_basis=(
                "net execution cost divided by engine-reported traded base notional times 10000; "
                f"observations {observation_digest}"
            ),
            null_reason=(
                "no traded fill notional"
                if notional == 0
                else "one or more fill cost reports are incomplete"
                if cost_bps is None
                else None
            ),
        ),
    ]
    for kind in ExecutionCostKind:
        metrics.append(
            _value(
                f"reported_{kind.value}_cash_effect",
                cash_effects[kind],
                unit=f"currency:{currency}",
                basis=MetricBasis.NET,
                sample_size=category_counts[kind],
                calculation_basis=(
                    f"sum of engine-reported {kind.value} cash effects in account base currency; "
                    f"negative is expense and positive is credit; incomplete reports may omit amounts; "
                    f"observations {observation_digest}"
                ),
            )
        )
    for component_id in sorted(component_effects):
        component_cost = (
            component_effects[component_id]
            if component_cost_complete[component_id]
            else None
        )
        component_notional = component_notionals[component_id]
        component_bps = (
            None
            if component_cost is None
            else component_cost / component_notional * Decimal(10000)
        )
        metrics.extend(
            (
                _value(
                    f"component_execution_cost:{component_id}",
                    component_cost,
                    unit=f"currency:{currency}",
                    basis=MetricBasis.NET,
                    sample_size=component_cost_counts[component_id],
                    calculation_basis=(
                        "negative sum of engine-reported fill cash effects attributed to this component; "
                        f"observations {observation_digest}"
                    ),
                    null_reason=(
                        "one or more component fill cost reports are incomplete"
                        if component_cost is None
                        else None
                    ),
                ),
                _value(
                    f"component_execution_cost_basis_points:{component_id}",
                    component_bps,
                    unit="basis_points",
                    basis=MetricBasis.NET,
                    sample_size=len(
                        [item for item in fill_values if item.component_id == component_id]
                    ),
                    calculation_basis=(
                        "component net execution cost divided by component traded base notional times 10000; "
                        f"observations {observation_digest}"
                    ),
                    null_reason=(
                        "one or more component fill cost reports are incomplete"
                        if component_bps is None
                        else None
                    ),
                ),
            )
        )
    return tuple(metrics)


@deterministic_decimal_math
def calculate_component_attribution_metrics(
    portfolio_pnl: PortfolioPnlObservation,
    component_pnl: Sequence[ComponentPnlObservation],
) -> tuple[MetricValue, ...]:
    """Calculate reconciled run-level component attribution from engine output.

    The components must cover the portfolio gross and net P&L exactly, including
    an explicit `__unallocated__` observation when any result is unassigned.
    Component P&L and its attributed costs/rebates are never inferred from
    position sizes or static capital weights.
    """

    if not isinstance(portfolio_pnl, PortfolioPnlObservation):
        raise TypeError("portfolio_pnl must be a PortfolioPnlObservation")
    components = tuple(component_pnl)
    if not components:
        raise ValueError("component P&L attribution observations are required")
    if any(not isinstance(item, ComponentPnlObservation) for item in components):
        raise TypeError("component_pnl must contain ComponentPnlObservation values")
    component_ids = [item.component_id for item in components]
    if len(component_ids) != len(set(component_ids)):
        raise ValueError("run-level component attribution must be unique per component")
    components = tuple(sorted(components, key=lambda item: item.component_id))
    expected_ids = set(portfolio_pnl.component_ids)
    observed_ids = set(component_ids)
    if not expected_ids.issubset(observed_ids):
        raise ValueError("component P&L attribution is missing declared portfolio components")
    if observed_ids - expected_ids - {"__unallocated__"}:
        raise ValueError("component P&L attribution contains an undeclared portfolio component")
    for item in components:
        if item.portfolio_fingerprint != portfolio_pnl.portfolio_fingerprint:
            raise ValueError("component P&L must belong to the account portfolio version")
        if item.run_attempt_id != portfolio_pnl.run_attempt_id:
            raise ValueError("component P&L must belong to the same run attempt")
        if item.point != portfolio_pnl.point:
            raise ValueError("component and portfolio P&L must use the same result event point")
        if item.base_currency != portfolio_pnl.base_currency:
            raise ValueError("component P&L must use the portfolio account base currency")
        if item.result_bundle_digest != portfolio_pnl.result_bundle_digest:
            raise ValueError("component P&L must bind the portfolio result evidence bundle")
    component_gross = sum((item.gross_pnl for item in components), Decimal(0))
    component_net = sum((item.net_pnl for item in components), Decimal(0))
    if component_gross != portfolio_pnl.gross_pnl:
        raise ValueError("component gross P&L does not reconcile to portfolio gross P&L")
    if component_net != portfolio_pnl.net_pnl:
        raise ValueError("component net P&L does not reconcile to portfolio net P&L")

    currency = portfolio_pnl.base_currency
    metrics = [
        _value(
            "portfolio_attributed_gross_pnl",
            component_gross,
            unit=f"currency:{currency}",
            basis=MetricBasis.GROSS,
            sample_size=1,
            calculation_basis=(
                "sum of engine-attributed component gross P&L, exactly reconciled to "
                f"portfolio result evidence {portfolio_pnl.engine_evidence_digest}; "
                f"result bundle {portfolio_pnl.result_bundle_digest}"
            ),
        ),
        _value(
            "portfolio_attributed_net_pnl",
            component_net,
            unit=f"currency:{currency}",
            basis=MetricBasis.NET,
            sample_size=1,
            calculation_basis=(
                "sum of engine-attributed component net P&L, exactly reconciled to "
                f"portfolio result evidence {portfolio_pnl.engine_evidence_digest}; "
                f"result bundle {portfolio_pnl.result_bundle_digest}"
            ),
        ),
    ]
    for item in sorted(components, key=lambda value: value.component_id):
        method_digest = item.attribution_method_digest
        metrics.extend(
            (
                _value(
                    f"component_gross_pnl:{item.component_id}",
                    item.gross_pnl,
                    unit=f"currency:{currency}",
                    basis=MetricBasis.GROSS,
                    sample_size=1,
                    calculation_basis=(
                        "engine-reported run-level gross P&L using attribution method "
                        f"{method_digest}; evidence {item.engine_evidence_digest}"
                    ),
                ),
                _value(
                    f"component_net_pnl:{item.component_id}",
                    item.net_pnl,
                    unit=f"currency:{currency}",
                    basis=MetricBasis.NET,
                    sample_size=1,
                    calculation_basis=(
                        "engine-reported run-level net P&L after the explicitly attributed "
                        f"costs and rebates; method {method_digest}; evidence {item.engine_evidence_digest}"
                    ),
                ),
                _value(
                    f"component_net_pnl_contribution:{item.component_id}",
                    None
                    if portfolio_pnl.net_pnl == 0
                    else item.net_pnl / portfolio_pnl.net_pnl,
                    unit="fraction",
                    basis=MetricBasis.NET,
                    sample_size=1,
                    calculation_basis=(
                        "engine-attributed component net P&L divided by reconciled portfolio net P&L"
                    ),
                    null_reason=(
                        "portfolio net P&L is zero" if portfolio_pnl.net_pnl == 0 else None
                    ),
                ),
            )
        )
    return tuple(metrics)
