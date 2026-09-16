"""Versioned Decimal metric calculations over authoritative result series."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Any

from app.strategy_lab_v2.allocation import PortfolioExposureSnapshot
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    METRIC_CALCULATION_CONTRACT_VERSION,
    KeyedRandomStreamPairingReceipt,
    MetricBasis,
    MetricCalculationDefinition,
    MetricEvidenceReference,
    MetricValue,
    RollingMetricPoint,
    SessionReturnDistribution,
)
from app.strategy_lab_v2.decimal_math import DECIMAL_PRECISION, deterministic_decimal_math
from app.strategy_lab_v2.observations import (
    AccountCapitalMarginObservation,
    AccountEquityIntervalObservation,
    ComponentPnlObservation,
    CostReportStatus,
    ExecutionCostKind,
    ExternalCashFlowReportStatus,
    FillCostObservation,
    FinancingCostReport,
    ObservationPoint,
    PortfolioPnlObservation,
)
from app.strategy_lab_v2.pairing import (
    PairedMetricObservation,
)
from app.strategy_lab_v2.rebalance import (
    RebalanceCadence,
    SessionCalendarSnapshot,
    TradingSession,
    calendar_period_key,
    require_complete_calendar_period_coverage,
)

METRIC_DEFINITION_VERSION = "strategy-lab.metrics.v6"
DEFAULT_SESSION_RETURN_QUANTILE_PROBABILITIES = (
    Decimal("0.05"),
    Decimal("0.25"),
    Decimal("0.50"),
    Decimal("0.75"),
    Decimal("0.95"),
)
DEFAULT_SESSION_RETURN_CONFIDENCE_LEVELS = (Decimal("0.95"),)
_METRIC_FORMULAS = {
    "total_pnl": "terminal equity minus initial capital; external cash flows are not modeled",
    "total_return": "terminal equity divided by initial capital minus one",
    "maximum_drawdown": "minimum observed equity divided by running peak minus one",
    "maximum_drawdown_duration": "longest count of sampled observations below the running peak",
    "ulcer_index": "square root of the mean squared observed drawdown fractions",
    "annualized_return": "terminal equity growth compounded by periods_per_year / return_count",
    "time_weighted_return": "geometrically linked subperiod returns excluding external cash-flow jumps",
    "time_weighted_annualized_return": "time-weighted growth compounded over elapsed UTC duration",
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
    "average_initial_margin_utilization": "equally sample-weighted mean of initial margin requirement divided by supplied initial margin capacity",
    "maximum_initial_margin_utilization": "maximum observed initial margin requirement divided by supplied initial margin capacity",
    "average_maintenance_margin_utilization": "equally sample-weighted mean of maintenance margin requirement divided by supplied maintenance margin capacity",
    "maximum_maintenance_margin_utilization": "maximum observed maintenance margin requirement divided by supplied maintenance margin capacity",
    "average_initial_margin_requirement_to_equity": "equally sample-weighted mean of initial margin requirement divided by contemporaneous account equity",
    "maximum_initial_margin_requirement_to_equity": "maximum observed initial margin requirement divided by contemporaneous account equity",
    "average_maintenance_margin_requirement_to_equity": "equally sample-weighted mean of maintenance margin requirement divided by contemporaneous account equity",
    "maximum_maintenance_margin_requirement_to_equity": "maximum observed maintenance margin requirement divided by contemporaneous account equity",
    "financing_event_count": "count of engine-reported financing cash-effect events",
    "complete_financing_report_count": "count of financing reports explicitly marked complete",
    "partial_financing_report_count": "count of financing reports explicitly marked partial",
    "unavailable_financing_report_count": "count of financing reports explicitly marked unavailable",
    "reported_financing_cash_effect": "sum of engine-reported financing cash effects in account base currency",
    "gross_financing_cost": "absolute sum of negative engine-reported financing cash effects in account base currency",
    "reported_financing_credit": "sum of positive engine-reported financing cash effects in account base currency",
    "net_financing_cost": "negative sum of engine-reported financing cash effects in account base currency",
    "paired_observation_count": "count of exactly aligned baseline and variant metric observations",
    "paired_baseline_mean": "arithmetic mean of aligned baseline metric observations",
    "paired_variant_mean": "arithmetic mean of aligned variant metric observations",
    "paired_mean_delta": "arithmetic mean of aligned variant minus baseline metric deltas",
    "paired_median_delta": "one-based nearest-rank median of aligned variant minus baseline metric deltas",
    "paired_minimum_delta": "minimum aligned variant minus baseline metric delta",
    "paired_maximum_delta": "maximum aligned variant minus baseline metric delta",
    "paired_delta_sample_stddev": "sample standard deviation of aligned variant minus baseline metric deltas",
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
    formula_id: str | None = None,
    calculation_parameters: dict[str, Any] | None = None,
    evidence_references: Sequence[MetricEvidenceReference] = (),
) -> MetricValue:
    if calculation_basis is None:
        try:
            calculation_basis = _METRIC_FORMULAS[name]
        except KeyError as error:
            raise ValueError(f"no calculation-basis definition registered for {name!r}") from error
    decimal_context_basis = f"Decimal precision={DECIMAL_PRECISION}; rounding=ROUND_HALF_EVEN"
    if calculation_basis is None:
        calculation_basis = decimal_context_basis
    else:
        calculation_basis = f"{calculation_basis}; {decimal_context_basis}"
    parameters: dict[str, Any] = {
        "decimal_precision": DECIMAL_PRECISION,
        "decimal_rounding": "ROUND_HALF_EVEN",
    }
    if calculation_parameters is not None:
        overlapping_parameters = parameters.keys() & calculation_parameters.keys()
        if overlapping_parameters:
            raise ValueError(
                "calculation parameters cannot override numeric context fields: "
                f"{', '.join(sorted(overlapping_parameters))}"
            )
        parameters.update(calculation_parameters)
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
        calculation_definition=MetricCalculationDefinition(
            formula_id=formula_id or f"metric.{name}",
            contract_version=METRIC_CALCULATION_CONTRACT_VERSION,
            parameters=parameters,
        ),
        evidence_references=tuple(evidence_references),
    )


def _finalize_metric_values(
    metrics: Sequence[MetricValue],
    *,
    evidence_references: Sequence[MetricEvidenceReference] = (),
    evidence_references_by_metric: Mapping[str, Sequence[MetricEvidenceReference]] | None = None,
    common_calculation_parameters: Mapping[str, Any] | None = None,
    calculation_parameters_by_metric: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[MetricValue, ...]:
    """Bind family-stable formula IDs and explicit context to calculated values.

    Dynamic dimensions in metric names use the first colon-delimited token as
    their formula family (for example, ``component_net_pnl:alpha``). Parameters
    are supplied by the calculator, never inferred from display strings.
    """

    common_parameters = common_calculation_parameters or {}
    parameters_by_metric = calculation_parameters_by_metric or {}
    references_by_metric = evidence_references_by_metric or {}
    finalized: list[MetricValue] = []
    for metric in metrics:
        definition = metric.calculation_definition
        if definition is None:
            raise ValueError("calculated metrics must have a structured calculation definition")
        formula_family = metric.name.partition(":")[0]
        parameters = dict(definition.parameters)
        parameters.update(common_parameters)
        parameters.update(
            parameters_by_metric.get(metric.name, parameters_by_metric.get(formula_family, {}))
        )
        finalized.append(
            replace(
                metric,
                calculation_definition=MetricCalculationDefinition(
                    formula_id=f"strategy-lab.metrics/{formula_family}",
                    contract_version=definition.contract_version,
                    parameters=parameters,
                ),
                evidence_references=(
                    *metric.evidence_references,
                    *evidence_references,
                    *references_by_metric.get(
                        metric.name,
                        references_by_metric.get(formula_family, ()),
                    ),
                ),
            )
        )
    return tuple(finalized)


def _validate_decimal_series(values: Sequence[Decimal], field_name: str) -> tuple[Decimal, ...]:
    series = tuple(values)
    if any(not isinstance(value, Decimal) or not value.is_finite() for value in series):
        raise ValueError(f"{field_name} must contain only finite Decimal values")
    return series


def _ceil_probability_count(count: int, probability: Decimal, *, complement: bool = False) -> int:
    numerator, denominator = probability.as_integer_ratio()
    if complement:
        numerator = denominator - numerator
    product_numerator = count * numerator
    return (product_numerator + denominator - 1) // denominator


def _decimal_token(value: Decimal) -> str:
    token = format(value, "f")
    return token.rstrip("0").rstrip(".") if "." in token else token


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
    input_digest = content_digest({"equity_curve": curve, "initial_capital": initial_capital})

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
        calmar = None if annualized_return is None else annualized_return / abs(max_drawdown)
        calmar_null_reason = "annualized return is unavailable" if calmar is None else None
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
        return _finalize_metric_values(
            metrics,
            evidence_references=(MetricEvidenceReference("calculator_input", input_digest),),
            common_calculation_parameters={
                "external_cash_flow_assumption": "no_external_cash_flows",
            },
            calculation_parameters_by_metric={
                "annualized_return": {"periods_per_year": periods_per_year},
                "calmar_ratio": {"periods_per_year": periods_per_year},
                "annualized_volatility": {"periods_per_year": periods_per_year},
                "sharpe_ratio": {
                    "periods_per_year": periods_per_year,
                    "risk_free_return_per_period": risk_free_return_per_period,
                },
                "sortino_ratio": {
                    "periods_per_year": periods_per_year,
                    "risk_free_return_per_period": risk_free_return_per_period,
                },
                "historical_value_at_risk": {
                    "confidence_level": historical_confidence_level,
                    "tail_rule": "ceil(n * (1 - confidence)); nearest-rank; no interpolation",
                },
                "historical_expected_shortfall": {
                    "confidence_level": historical_confidence_level,
                    "tail_rule": "ceil(n * (1 - confidence)); mean worst tail; no interpolation",
                },
            },
        )

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
    return _finalize_metric_values(
        metrics,
        evidence_references=(MetricEvidenceReference("calculator_input", input_digest),),
        common_calculation_parameters={
            "external_cash_flow_assumption": "no_external_cash_flows",
        },
        calculation_parameters_by_metric={
            "annualized_return": {"periods_per_year": periods_per_year},
            "calmar_ratio": {"periods_per_year": periods_per_year},
            "annualized_volatility": {"periods_per_year": periods_per_year},
            "sharpe_ratio": {
                "periods_per_year": periods_per_year,
                "risk_free_return_per_period": risk_free_return_per_period,
            },
            "sortino_ratio": {
                "periods_per_year": periods_per_year,
                "risk_free_return_per_period": risk_free_return_per_period,
            },
            "historical_value_at_risk": {
                "confidence_level": historical_confidence_level,
                "tail_rule": "ceil(n * (1 - confidence)); nearest-rank; no interpolation",
            },
            "historical_expected_shortfall": {
                "confidence_level": historical_confidence_level,
                "tail_rule": "ceil(n * (1 - confidence)); mean worst tail; no interpolation",
            },
        },
    )


@deterministic_decimal_math
def calculate_trade_metrics(
    trade_pnls: Sequence[Decimal], *, base_currency: str, basis: MetricBasis = MetricBasis.NET
) -> tuple[MetricValue, ...]:
    """Summarize engine-reported trade P&L with an explicit currency and basis."""

    pnls = _validate_decimal_series(trade_pnls, "trade_pnls")
    currency = _currency_code(base_currency)
    input_digest = content_digest({"ordered_trade_pnls": pnls})
    if not isinstance(basis, MetricBasis):
        raise TypeError("basis must be a MetricBasis")
    count = len(pnls)
    if count == 0:
        return _finalize_metric_values(
            (
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
            ),
            evidence_references=(MetricEvidenceReference("calculator_input", input_digest),),
            calculation_parameters_by_metric={
                "max_consecutive_wins": {"input_order": "ordered_trade_sequence"},
                "max_consecutive_losses": {"input_order": "ordered_trade_sequence"},
            },
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
    return _finalize_metric_values(
        (
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
                    "no winning trades" if not wins else "no losing trades" if not losses else None
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
        ),
        evidence_references=(MetricEvidenceReference("calculator_input", input_digest),),
        calculation_parameters_by_metric={
            "max_consecutive_wins": {"input_order": "ordered_trade_sequence"},
            "max_consecutive_losses": {"input_order": "ordered_trade_sequence"},
        },
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
        raise ValueError(
            "exposure observations must be strictly ordered by event time and sequence"
        )
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
        gross = sum((abs(item.signed_base_risk_exposure) for item in mark.positions), Decimal(0))
        net = sum((item.signed_base_risk_exposure for item in mark.positions), Decimal(0))
        gross_ratios.append(gross / mark.account_equity)
        net_ratios.append(net / mark.account_equity)
        cash_ratios.append(mark.account_cash_balance / mark.account_equity)

    sample_size = len(marks)
    return _finalize_metric_values(
        (
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
        ),
        evidence_references=(MetricEvidenceReference("exposure_observations", observation_digest),),
        common_calculation_parameters={
            "risk_model": CASH_EQUITY_NOTIONAL_RISK_MODEL,
            "valuation_basis": "signed_base_notional_over_contemporaneous_account_equity",
        },
    )


@deterministic_decimal_math
def calculate_capital_margin_utilization_metrics(
    observations: Sequence[AccountCapitalMarginObservation],
) -> tuple[MetricValue, ...]:
    """Summarize engine-reported margin requirements and capital capacity.

    The ratios are equally sample-weighted event marks. Requirements and
    capacities must be supplied by the authoritative account/product adapter;
    this calculator deliberately does not infer margin, leverage, or buying
    power from position notionals. Ratios above one remain diagnostic values
    and are not converted into a breach or profitability verdict.
    """

    marks = tuple(observations)
    if not marks:
        raise ValueError("at least one capital and margin observation is required")
    if any(not isinstance(item, AccountCapitalMarginObservation) for item in marks):
        raise TypeError("observations must contain AccountCapitalMarginObservation values")
    portfolio_fingerprint = marks[0].portfolio_fingerprint
    run_attempt_id = marks[0].run_attempt_id
    base_currency = marks[0].base_currency
    points = tuple(item.point for item in marks)
    if any(item.portfolio_fingerprint != portfolio_fingerprint for item in marks):
        raise ValueError("all capital and margin observations must use the same portfolio version")
    if any(item.run_attempt_id != run_attempt_id for item in marks):
        raise ValueError("all capital and margin observations must belong to the same run attempt")
    if any(item.base_currency != base_currency for item in marks):
        raise ValueError("all capital and margin observations must use the same base currency")
    if any(current <= previous for previous, current in zip(points, points[1:])):
        raise ValueError(
            "capital and margin observations must be strictly ordered by event time and sequence"
        )

    observation_digest = content_digest(marks)
    initial_utilization = [
        item.initial_margin_requirement / item.initial_margin_capacity for item in marks
    ]
    maintenance_utilization = [
        item.maintenance_margin_requirement / item.maintenance_margin_capacity for item in marks
    ]
    initial_to_equity = [
        item.initial_margin_requirement / item.account_equity for item in marks
    ]
    maintenance_to_equity = [
        item.maintenance_margin_requirement / item.account_equity for item in marks
    ]
    sample_size = len(marks)

    def average(values: Sequence[Decimal]) -> Decimal:
        return sum(values, Decimal(0)) / Decimal(sample_size)

    calculation_parameters = {
        "valuation_basis": "engine_reported_margin_requirements_and_capacities",
        "sample_weighting": "equal_event_marks",
        "notional_inference": "forbidden",
    }
    return _finalize_metric_values(
        (
            _value(
                "average_initial_margin_utilization",
                average(initial_utilization),
                unit="ratio",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "equally sample-weighted mean of engine-reported initial margin "
                    "requirement divided by supplied initial margin capacity; "
                    f"observations {observation_digest}"
                ),
            ),
            _value(
                "maximum_initial_margin_utilization",
                max(initial_utilization),
                unit="ratio",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "maximum observed engine-reported initial margin requirement divided "
                    f"by supplied initial margin capacity; observations {observation_digest}"
                ),
            ),
            _value(
                "average_maintenance_margin_utilization",
                average(maintenance_utilization),
                unit="ratio",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "equally sample-weighted mean of engine-reported maintenance margin "
                    "requirement divided by supplied maintenance margin capacity; "
                    f"observations {observation_digest}"
                ),
            ),
            _value(
                "maximum_maintenance_margin_utilization",
                max(maintenance_utilization),
                unit="ratio",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "maximum observed engine-reported maintenance margin requirement divided "
                    f"by supplied maintenance margin capacity; observations {observation_digest}"
                ),
            ),
            _value(
                "average_initial_margin_requirement_to_equity",
                average(initial_to_equity),
                unit="ratio",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "equally sample-weighted mean of engine-reported initial margin "
                    "requirement divided by contemporaneous account equity; "
                    f"observations {observation_digest}"
                ),
            ),
            _value(
                "maximum_initial_margin_requirement_to_equity",
                max(initial_to_equity),
                unit="ratio",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "maximum observed engine-reported initial margin requirement divided "
                    f"by contemporaneous account equity; observations {observation_digest}"
                ),
            ),
            _value(
                "average_maintenance_margin_requirement_to_equity",
                average(maintenance_to_equity),
                unit="ratio",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "equally sample-weighted mean of engine-reported maintenance margin "
                    "requirement divided by contemporaneous account equity; "
                    f"observations {observation_digest}"
                ),
            ),
            _value(
                "maximum_maintenance_margin_requirement_to_equity",
                max(maintenance_to_equity),
                unit="ratio",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "maximum observed engine-reported maintenance margin requirement divided "
                    f"by contemporaneous account equity; observations {observation_digest}"
                ),
            ),
        ),
        evidence_references=(
            MetricEvidenceReference("capital_margin_observations", observation_digest),
        ),
        common_calculation_parameters=calculation_parameters,
    )


@deterministic_decimal_math
def calculate_financing_cost_metrics(
    reports: Sequence[FinancingCostReport],
) -> tuple[MetricValue, ...]:
    """Summarize explicitly reported financing cash effects.

    Financing is intentionally a separate evidence path from fill costs. A
    complete report can publish a signed net cash effect; partial or
    unavailable reports retain coverage counts and reported components but
    withhold the derived net cost so omitted funding events cannot look free.
    """

    report_values = tuple(reports)
    if not report_values:
        raise ValueError("at least one financing cost report is required")
    if any(not isinstance(item, FinancingCostReport) for item in report_values):
        raise TypeError("reports must contain FinancingCostReport values")
    portfolio_fingerprint = report_values[0].portfolio_fingerprint
    run_attempt_id = report_values[0].run_attempt_id
    currency = report_values[0].base_currency
    previous_end: ObservationPoint | None = None
    for report in report_values:
        if report.portfolio_fingerprint != portfolio_fingerprint:
            raise ValueError("all financing reports must use the same portfolio version")
        if report.run_attempt_id != run_attempt_id:
            raise ValueError("all financing reports must belong to the same run attempt")
        if report.base_currency != currency:
            raise ValueError("all financing reports must use the same base currency")
        if previous_end is not None and report.start_point < previous_end:
            raise ValueError("financing reports must be ordered and must not overlap")
        previous_end = report.end_point

    observation_digest = content_digest(report_values)
    observations = tuple(
        observation
        for report in report_values
        for observation in report.observations
    )
    if len({item.financing_event_id for item in observations}) != len(observations):
        raise ValueError("financing event ids must be unique across reports")
    cash_effect = sum((item.base_cash_effect for item in observations), Decimal(0))
    gross_cost = -sum(
        (item.base_cash_effect for item in observations if item.base_cash_effect < 0),
        Decimal(0),
    )
    reported_credit = sum(
        (item.base_cash_effect for item in observations if item.base_cash_effect > 0),
        Decimal(0),
    )
    complete_count = sum(
        report.report_status is CostReportStatus.COMPLETE for report in report_values
    )
    partial_count = sum(report.report_status is CostReportStatus.PARTIAL for report in report_values)
    unavailable_count = sum(
        report.report_status is CostReportStatus.UNAVAILABLE for report in report_values
    )
    complete = partial_count == 0 and unavailable_count == 0
    sample_size = len(observations)
    incompleteness_reason = "one or more financing reports are incomplete"
    net_cash_value = -cash_effect if complete else None
    gross_cost_value = gross_cost if complete else None
    metrics = (
        _value(
            "financing_event_count",
            Decimal(sample_size),
            unit="events",
            basis=MetricBasis.NET,
            sample_size=sample_size,
            calculation_basis=(
                "count of unique engine-reported financing events; "
                f"observations {observation_digest}"
            ),
        ),
        _value(
            "complete_financing_report_count",
            Decimal(complete_count),
            unit="reports",
            basis=MetricBasis.NET,
            sample_size=len(report_values),
            calculation_basis="count of financing reports explicitly marked complete",
        ),
        _value(
            "partial_financing_report_count",
            Decimal(partial_count),
            unit="reports",
            basis=MetricBasis.NET,
            sample_size=len(report_values),
            calculation_basis="count of financing reports explicitly marked partial",
        ),
        _value(
            "unavailable_financing_report_count",
            Decimal(unavailable_count),
            unit="reports",
            basis=MetricBasis.NET,
            sample_size=len(report_values),
            calculation_basis="count of financing reports explicitly marked unavailable",
        ),
        _value(
            "reported_financing_cash_effect",
            cash_effect,
            unit=f"currency:{currency}",
            basis=MetricBasis.NET,
            sample_size=sample_size,
            calculation_basis=(
                "sum of engine-reported financing cash effects in account base currency; "
                "negative is expense and positive is credit; incomplete reports may omit amounts; "
                f"observations {observation_digest}"
            ),
        ),
        _value(
            "gross_financing_cost",
            gross_cost_value,
            unit=f"currency:{currency}",
            basis=MetricBasis.GROSS,
            sample_size=sample_size,
            calculation_basis=(
                "absolute sum of negative engine-reported financing cash effects in account base currency; "
                f"observations {observation_digest}"
            ),
            null_reason=incompleteness_reason if not complete else None,
        ),
        _value(
            "reported_financing_credit",
            reported_credit,
            unit=f"currency:{currency}",
            basis=MetricBasis.NET,
            sample_size=sample_size,
            calculation_basis=(
                "sum of positive engine-reported financing cash effects in account base currency; "
                f"incomplete reports may omit amounts; observations {observation_digest}"
            ),
        ),
        _value(
            "net_financing_cost",
            net_cash_value,
            unit=f"currency:{currency}",
            basis=MetricBasis.NET,
            sample_size=sample_size,
            calculation_basis=(
                "negative sum of engine-reported financing cash effects in account base currency; "
                f"observations {observation_digest}"
            ),
            null_reason=incompleteness_reason if not complete else None,
        ),
    )
    return _finalize_metric_values(
        metrics,
        evidence_references=(
            MetricEvidenceReference("financing_cost_reports", observation_digest),
        ),
        common_calculation_parameters={
            "financing_scope": "outside_fill_reports",
            "cost_report_policy": "null_net_cost_unless_all_reports_complete",
        },
    )


@deterministic_decimal_math
def calculate_paired_metric_metrics(
    observations: Sequence[PairedMetricObservation],
    *,
    metric_name: str,
    unit: str,
    basis: MetricBasis,
    pairing_receipt: KeyedRandomStreamPairingReceipt,
) -> tuple[MetricValue, ...]:
    """Summarize exactly aligned baseline/variant metric observations.

    This calculator is intentionally descriptive. The required verified
    pairing receipt establishes random-stream provenance, while the keyed
    observations establish the metric alignment. The output does not rank
    candidates, estimate significance, or claim an inferential model.
    """

    if not isinstance(metric_name, str) or not metric_name.strip():
        raise ValueError("metric_name must not be empty")
    if not isinstance(unit, str) or not unit.strip():
        raise ValueError("unit must not be empty")
    if not isinstance(basis, MetricBasis):
        raise TypeError("basis must be a MetricBasis")
    if not isinstance(pairing_receipt, KeyedRandomStreamPairingReceipt):
        raise TypeError("pairing_receipt must use KeyedRandomStreamPairingReceipt")

    values = tuple(observations)
    if not values:
        raise ValueError("at least one paired metric observation is required")
    if any(not isinstance(item, PairedMetricObservation) for item in values):
        raise TypeError("observations must contain PairedMetricObservation values")
    ordered = tuple(sorted(values, key=lambda item: item.observation_key))
    keys = tuple(item.observation_key for item in ordered)
    if len(keys) != len(set(keys)):
        raise ValueError("paired metric observation keys must be unique")
    observation_digest = content_digest(ordered)
    baseline_values = tuple(item.baseline_value for item in ordered)
    variant_values = tuple(item.variant_value for item in ordered)
    deltas = tuple(item.variant_value - item.baseline_value for item in ordered)
    sample_size = len(ordered)
    baseline_mean = sum(baseline_values, Decimal(0)) / Decimal(sample_size)
    variant_mean = sum(variant_values, Decimal(0)) / Decimal(sample_size)
    mean_delta = sum(deltas, Decimal(0)) / Decimal(sample_size)
    sorted_deltas = tuple(sorted(deltas))
    median_rank = max(
        1,
        int(
            (Decimal(sample_size) * Decimal("0.5")).to_integral_value(
                rounding=ROUND_CEILING
            )
        ),
    )
    median_delta = sorted_deltas[median_rank - 1]
    sample_variance = (
        sum(((value - mean_delta) ** 2 for value in deltas), Decimal(0))
        / Decimal(sample_size - 1)
        if sample_size > 1
        else None
    )
    sample_stddev = None if sample_variance is None else sample_variance.sqrt()
    common_basis = (
        f"metric={metric_name}; exactly keyed-aligned observations {observation_digest}; "
        f"verified pairing receipt {pairing_receipt.fingerprint}"
    )
    metrics = (
        _value(
            "paired_observation_count",
            Decimal(sample_size),
            unit="observations",
            basis=basis,
            sample_size=sample_size,
            calculation_basis=f"count of exactly aligned paired metric observations; {common_basis}",
        ),
        _value(
            "paired_baseline_mean",
            baseline_mean,
            unit=unit,
            basis=basis,
            sample_size=sample_size,
            calculation_basis=f"arithmetic mean of aligned baseline values; {common_basis}",
        ),
        _value(
            "paired_variant_mean",
            variant_mean,
            unit=unit,
            basis=basis,
            sample_size=sample_size,
            calculation_basis=f"arithmetic mean of aligned variant values; {common_basis}",
        ),
        _value(
            "paired_mean_delta",
            mean_delta,
            unit=unit,
            basis=basis,
            sample_size=sample_size,
            calculation_basis=f"arithmetic mean of aligned variant minus baseline deltas; {common_basis}",
        ),
        _value(
            "paired_median_delta",
            median_delta,
            unit=unit,
            basis=basis,
            sample_size=sample_size,
            calculation_basis=(
                "one-based nearest-rank median of aligned variant minus baseline deltas; "
                f"{common_basis}"
            ),
        ),
        _value(
            "paired_minimum_delta",
            min(deltas),
            unit=unit,
            basis=basis,
            sample_size=sample_size,
            calculation_basis=f"minimum aligned variant minus baseline delta; {common_basis}",
        ),
        _value(
            "paired_maximum_delta",
            max(deltas),
            unit=unit,
            basis=basis,
            sample_size=sample_size,
            calculation_basis=f"maximum aligned variant minus baseline delta; {common_basis}",
        ),
        _value(
            "paired_delta_sample_stddev",
            sample_stddev,
            unit=unit,
            basis=basis,
            sample_size=sample_size,
            calculation_basis=f"sample standard deviation of aligned deltas; {common_basis}",
            null_reason="at least two paired observations are required" if sample_stddev is None else None,
        ),
    )
    return _finalize_metric_values(
        metrics,
        evidence_references=(
            MetricEvidenceReference("paired_metric_observations", observation_digest),
            MetricEvidenceReference("pairing_receipt", pairing_receipt.fingerprint),
        ),
        common_calculation_parameters={
            "metric_name": metric_name,
            "observation_order": "sorted_by_observation_key",
            "inference_policy": "descriptive_only_no_ranking_or_significance",
            "pairing_receipt_verifier": pairing_receipt.verifier_version,
        },
    )


def _validated_equity_intervals(
    observations: Sequence[AccountEquityIntervalObservation],
    calendar: SessionCalendarSnapshot,
) -> tuple[
    tuple[AccountEquityIntervalObservation, ...],
    dict[date, TradingSession],
]:
    intervals = tuple(observations)
    if not intervals:
        raise ValueError("at least one account equity interval is required")
    if any(not isinstance(item, AccountEquityIntervalObservation) for item in intervals):
        raise TypeError("observations must contain AccountEquityIntervalObservation values")
    if not isinstance(calendar, SessionCalendarSnapshot):
        raise TypeError("calendar must be a SessionCalendarSnapshot")

    portfolio_fingerprint = intervals[0].portfolio_fingerprint
    run_attempt_id = intervals[0].run_attempt_id
    currency = intervals[0].base_currency
    calendar_fingerprint = calendar.fingerprint
    session_by_label = {
        day.session.session_label: day.session for day in calendar.days if day.session is not None
    }
    observed_labels: set[date] = set()
    previous: AccountEquityIntervalObservation | None = None
    for item in intervals:
        if item.portfolio_fingerprint != portfolio_fingerprint:
            raise ValueError("all account equity intervals must use the same portfolio version")
        if item.run_attempt_id != run_attempt_id:
            raise ValueError("all account equity intervals must belong to the same run attempt")
        if item.base_currency != currency:
            raise ValueError("all account equity intervals must use the same base currency")
        if item.calendar_fingerprint != calendar_fingerprint:
            raise ValueError("account equity intervals must bind the supplied calendar version")
        session = session_by_label.get(item.session_label)
        if session is None:
            raise ValueError("account equity interval session label is not a trading date")
        if item.end_point.event_time != session.close_time:
            raise ValueError("account equity interval must end at its official session close")
        if item.session_label in observed_labels:
            raise ValueError("account equity intervals must be unique per session label")
        if previous is not None:
            if item.end_point <= previous.end_point:
                raise ValueError("account equity intervals must be strictly ordered")
            if item.start_point != previous.end_point:
                raise ValueError("account equity intervals must form one contiguous mark chain")
            if item.starting_equity != previous.ending_equity:
                raise ValueError("contiguous account equity intervals must reconcile their marks")
        observed_labels.add(item.session_label)
        previous = item
    return intervals, session_by_label


def _time_weighted_interval_result(
    interval: AccountEquityIntervalObservation,
) -> tuple[Decimal, tuple[Decimal, ...]] | None:
    """Return one interval's growth and normalized wealth marks, if evidenced."""

    if interval.external_cash_flow_occurred is True and not interval.external_cash_flow_boundaries:
        return None
    previous_equity = interval.starting_equity
    growth = Decimal(1)
    wealth_marks = [Decimal(1)]
    for boundary in interval.external_cash_flow_boundaries:
        if previous_equity <= 0:
            return None
        growth_to_boundary = boundary.pre_flow_equity / previous_equity
        growth *= growth_to_boundary
        wealth_marks.append(growth)
        previous_equity = boundary.post_flow_equity
    if previous_equity <= 0:
        if interval.ending_equity != 0:
            return None
        growth = Decimal(0)
    else:
        growth *= interval.ending_equity / previous_equity
    wealth_marks.append(growth)
    return growth, tuple(wealth_marks)


def _time_weighted_interval_results(
    intervals: Sequence[AccountEquityIntervalObservation],
) -> tuple[tuple[Decimal, tuple[Decimal, ...]], ...] | None:
    """Return all flow-adjusted interval results, or ``None`` when incomplete."""

    results: list[tuple[Decimal, tuple[Decimal, ...]]] = []
    for interval in intervals:
        result = _time_weighted_interval_result(interval)
        if result is None:
            return None
        results.append(result)
    return tuple(results)


@deterministic_decimal_math
def calculate_calendar_period_metrics(
    observations: Sequence[AccountEquityIntervalObservation],
    *,
    calendar: SessionCalendarSnapshot,
    cadence: RebalanceCadence,
) -> tuple[MetricValue, ...]:
    """Aggregate linked prior-mark-to-session-close equity intervals by calendar.

    Net P&L reconciles account equity changes after explicitly reported external
    cash flows. Period returns are emitted only for complete periods with no
    external flow; a time-weighted return method is not inferred.
    A period is marked complete only when observations start at the preceding
    actual session close and reach the period's final session close. Calendar
    evidence must therefore include at least one prior session for a complete
    first observed period.
    """

    intervals, session_by_label = _validated_equity_intervals(observations, calendar)
    if not isinstance(cadence, RebalanceCadence):
        raise TypeError("cadence must be a RebalanceCadence")
    require_complete_calendar_period_coverage(calendar, cadence)

    currency = intervals[0].base_currency
    calendar_fingerprint = calendar.fingerprint
    groups: dict[str, list[AccountEquityIntervalObservation]] = {}
    for item in intervals:
        groups.setdefault(calendar_period_key(item.session_label, cadence), []).append(item)

    calendar_sessions_by_period: dict[str, list[TradingSession]] = {}
    calendar_sessions: list[TradingSession] = []
    for day in calendar.days:
        if day.session is not None:
            calendar_sessions.append(day.session)
            period = calendar_period_key(day.label, cadence)
            calendar_sessions_by_period.setdefault(period, []).append(day.session)
    calendar_session_index = {
        session.session_label: index for index, session in enumerate(calendar_sessions)
    }

    metrics: list[MetricValue] = []
    for period in sorted(groups, key=lambda value: groups[value][0].session_label):
        period_intervals = groups[period]
        expected_sessions = calendar_sessions_by_period[period]
        first_expected_session = expected_sessions[0]
        last_expected_session = expected_sessions[-1]
        first_interval = period_intervals[0]
        last_interval = period_intervals[-1]
        first_session_index = calendar_session_index[first_expected_session.session_label]
        preceding_session = (
            calendar_sessions[first_session_index - 1] if first_session_index > 0 else None
        )
        period_complete = (
            first_interval.session_label == first_expected_session.session_label
            and preceding_session is not None
            and first_interval.start_point.event_time == preceding_session.close_time
            and last_interval.session_label == last_expected_session.session_label
            and last_interval.end_point.event_time == last_expected_session.close_time
        )
        flow_reports_complete = all(
            item.external_cash_flow_report_status is ExternalCashFlowReportStatus.COMPLETE
            for item in period_intervals
        )
        has_external_flows = any(
            item.external_cash_flow_occurred is True for item in period_intervals
        )
        net_pnl = (
            sum(
                (
                    item.ending_equity
                    - item.starting_equity
                    - (
                        item.external_cash_flow
                        if item.external_cash_flow is not None
                        else Decimal(0)
                    )
                    for item in period_intervals
                ),
                Decimal(0),
            )
            if flow_reports_complete
            else None
        )
        net_pnl_null_reason = (
            "one or more external cash-flow reports are incomplete"
            if not flow_reports_complete
            else None
        )
        return_null_reason = (
            "calendar period coverage is incomplete"
            if not period_complete
            else "one or more external cash-flow reports are incomplete"
            if not flow_reports_complete
            else "period contains external cash flows; boundary-aware return evidence is unavailable"
            if has_external_flows
            else None
        )
        if period_complete and flow_reports_complete and has_external_flows:
            weighted_results = _time_weighted_interval_results(period_intervals)
            if weighted_results is None:
                period_return = None
                return_null_reason = (
                    "external cash-flow boundary valuations are required for every reported event"
                )
            else:
                period_growth = Decimal(1)
                for interval_growth, _ in weighted_results:
                    period_growth *= interval_growth
                period_return = period_growth - Decimal(1)
                return_null_reason = None
        else:
            period_return = (
                None
                if return_null_reason is not None
                else last_interval.ending_equity / first_interval.starting_equity - Decimal(1)
            )
        return_calculation_basis = (
            "geometrically linked pre/post-flow subperiod returns; "
            if has_external_flows
            else "closing account equity divided by the first interval opening equity minus one; "
        )
        observation_digest = content_digest(tuple(period_intervals))
        basis = (
            f"{cadence.value} calendar period {period}; opening mark {first_interval.start_point.event_time.isoformat()}; "
            f"closing session {last_interval.session_label.isoformat()}; calendar {calendar_fingerprint}; "
            f"period_complete={str(period_complete).lower()}; observations {observation_digest}"
        )
        metrics.extend(
            _finalize_metric_values(
                (
                    _value(
                        f"calendar_period_net_pnl:{cadence.value}:{period}",
                        net_pnl,
                        unit=f"currency:{currency}",
                        basis=MetricBasis.NET,
                        sample_size=len(period_intervals),
                        calculation_basis=(
                            "sum of linked session-close account equity changes less explicitly reported "
                            f"external cash flows; {basis}"
                        ),
                        null_reason=net_pnl_null_reason,
                    ),
                    _value(
                        f"calendar_period_return:{cadence.value}:{period}",
                        period_return,
                        unit="fraction",
                        basis=MetricBasis.NET,
                        sample_size=len(period_intervals),
                        calculation_basis=f"{return_calculation_basis}{basis}",
                        null_reason=return_null_reason,
                    ),
                    _value(
                        f"calendar_period_complete:{cadence.value}:{period}",
                        Decimal(1) if period_complete else Decimal(0),
                        unit="boolean",
                        basis=MetricBasis.NET,
                        sample_size=len(period_intervals),
                        calculation_basis=(
                            "one means marks span the preceding actual session close through "
                            f"the last actual session close; {basis}"
                        ),
                    ),
                ),
                evidence_references=(
                    MetricEvidenceReference("calendar_period_intervals", observation_digest),
                    MetricEvidenceReference("session_calendar", calendar_fingerprint),
                ),
                common_calculation_parameters={
                    "calendar_cadence": cadence.value,
                    "coverage_convention": "preceding_actual_close_through_period_final_close",
                    "external_cash_flow_policy": (
                        "subtract reported flows from net pnl; require explicit pre/post boundaries for flow-bearing returns"
                    ),
                },
            )
        )
    return tuple(metrics)


@deterministic_decimal_math
def calculate_time_weighted_return_metrics(
    observations: Sequence[AccountEquityIntervalObservation],
    *,
    calendar: SessionCalendarSnapshot,
    annualization_days: Decimal = Decimal("365.2425"),
    basis: MetricBasis = MetricBasis.NET,
) -> tuple[MetricValue, ...]:
    """Link returns while explicitly removing external cash-flow jumps.

    Every interval with ``external_cash_flow_occurred=True`` must carry one
    :class:`ExternalCashFlowBoundaryObservation` per event. The pre/post marks
    make the event's cash jump observable and keep it out of the geometric
    return chain. Incomplete native flow reports or missing boundaries withhold
    both metrics rather than falling back to a cash-flow-adjusted P&L.

    ``annualization_days`` is an explicit elapsed-time convention, so irregular
    interval spacing is never silently treated as a fixed session cadence.
    """

    if not isinstance(basis, MetricBasis):
        raise TypeError("basis must be a MetricBasis")
    if (
        not isinstance(annualization_days, Decimal)
        or not annualization_days.is_finite()
        or annualization_days <= 0
    ):
        raise ValueError("annualization_days must be a finite positive Decimal")

    intervals, _ = _validated_equity_intervals(observations, calendar)
    observation_digest = content_digest(intervals)
    flow_reports_complete = all(
        item.external_cash_flow_report_status is ExternalCashFlowReportStatus.COMPLETE
        for item in intervals
    )
    annualization_basis = f"elapsed UTC duration; {annualization_days} days per year"
    null_reason: str | None = None
    linked_growth: Decimal | None = None
    if not flow_reports_complete:
        null_reason = "one or more external cash-flow reports are incomplete"
    else:
        weighted_results = _time_weighted_interval_results(intervals)
        if weighted_results is None:
            null_reason = (
                "external cash-flow boundary valuations are required for every reported event"
            )
        else:
            linked_growth = Decimal(1)
            for interval_growth, _ in weighted_results:
                linked_growth *= interval_growth

    elapsed = intervals[-1].end_point.event_time - intervals[0].start_point.event_time
    elapsed_seconds = Decimal(elapsed.days * 86_400 + elapsed.seconds) + Decimal(
        elapsed.microseconds
    ) / Decimal(1_000_000)
    if null_reason is None and elapsed_seconds <= 0:
        null_reason = "elapsed observation duration must be positive"
    time_weighted_return = None if linked_growth is None else linked_growth - Decimal(1)
    if null_reason is not None:
        annualized_return = None
        annualized_null_reason = null_reason
    elif linked_growth is None or linked_growth <= 0:
        annualized_return = None
        annualized_null_reason = "non-positive linked growth prevents annualization"
    else:
        year_seconds = annualization_days * Decimal(86_400)
        annualized_return = linked_growth ** (year_seconds / elapsed_seconds) - Decimal(1)
        annualized_null_reason = None

    basis_text = (
        "geometrically linked pre/post-flow subperiod returns; "
        f"observations={observation_digest}; calendar={calendar.fingerprint}; "
        f"elapsed_seconds={elapsed_seconds}"
    )
    return _finalize_metric_values(
        (
            _value(
                "time_weighted_return",
                time_weighted_return,
                unit="fraction",
                basis=basis,
                sample_size=len(intervals),
                calculation_basis=(
                    "geometric linking of returns between explicit pre-flow and post-flow marks; "
                    f"{basis_text}"
                ),
                null_reason=null_reason,
            ),
            _value(
                "time_weighted_annualized_return",
                annualized_return,
                unit="fraction",
                basis=basis,
                sample_size=len(intervals),
                annualization_basis=annualization_basis,
                calculation_basis=(
                    "time-weighted growth compounded by elapsed UTC duration; " f"{basis_text}"
                ),
                null_reason=annualized_null_reason,
            ),
        ),
        evidence_references=(
            MetricEvidenceReference("account_equity_intervals", observation_digest),
            MetricEvidenceReference("session_calendar", calendar.fingerprint),
        ),
        common_calculation_parameters={
            "return_convention": "geometrically_linked_subperiod_returns",
            "external_cash_flow_policy": "requires_complete_reports_and_explicit_pre_post_boundaries",
            "annualization_days": annualization_days,
        },
    )


@deterministic_decimal_math
def calculate_rolling_equity_metrics(
    observations: Sequence[AccountEquityIntervalObservation],
    *,
    calendar: SessionCalendarSnapshot,
    window_sessions: int,
    periods_per_year: int,
    risk_free_return_per_period: Decimal,
    minimum_risk_observations: int = 2,
) -> tuple[RollingMetricPoint, ...]:
    """Calculate an explicit rolling metric point at each observed session close.

    Each window consists of ``window_sessions`` complete close-to-close account
    equity intervals plus its preceding actual session close as the opening mark.
    Missing sessions never collapse into adjacent samples. Periods per year and
    the periodic risk-free target are caller-supplied conventions. Return and
    equity-path risk metrics are withheld if any external cash-flow events
    occurred or their report is incomplete; net P&L remains available when flow
    reports are complete, after subtracting the reported net flows.
    """

    if (
        not isinstance(window_sessions, int)
        or isinstance(window_sessions, bool)
        or window_sessions < 1
    ):
        raise ValueError("window_sessions must be a positive integer")
    if (
        not isinstance(periods_per_year, int)
        or isinstance(periods_per_year, bool)
        or periods_per_year < 1
    ):
        raise ValueError("periods_per_year must be a positive integer")
    if (
        not isinstance(minimum_risk_observations, int)
        or isinstance(minimum_risk_observations, bool)
        or minimum_risk_observations < 2
    ):
        raise ValueError("minimum_risk_observations must be an integer of at least two")
    if (
        not isinstance(risk_free_return_per_period, Decimal)
        or not risk_free_return_per_period.is_finite()
        or risk_free_return_per_period <= -1
    ):
        raise ValueError("risk_free_return_per_period must be finite and greater than -1")

    intervals, _ = _validated_equity_intervals(observations, calendar)
    portfolio_fingerprint = intervals[0].portfolio_fingerprint
    run_attempt_id = intervals[0].run_attempt_id
    calendar_fingerprint = calendar.fingerprint
    calendar_sessions = [day.session for day in calendar.days if day.session is not None]
    session_index = {
        session.session_label: index for index, session in enumerate(calendar_sessions)
    }
    interval_by_label = {item.session_label: item for item in intervals}
    annualization_basis = f"sample session-return convention: {periods_per_year} sessions per year"
    points: list[RollingMetricPoint] = []

    for endpoint in intervals:
        end_index = session_index[endpoint.session_label]
        first_window_index = end_index - window_sessions + 1
        window_start_session = (
            calendar_sessions[first_window_index] if first_window_index >= 0 else None
        )
        expected_sessions = calendar_sessions[max(0, first_window_index) : end_index + 1]
        window_intervals = tuple(
            interval_by_label[session.session_label]
            for session in expected_sessions
            if session.session_label in interval_by_label
        )
        observed_sessions = len(window_intervals)
        first_window_interval = (
            interval_by_label.get(window_start_session.session_label)
            if window_start_session is not None
            else None
        )
        window_start_point = (
            first_window_interval.start_point if first_window_interval is not None else None
        )
        preceding_session = (
            calendar_sessions[first_window_index - 1] if first_window_index > 0 else None
        )
        coverage_null_reason = None
        if first_window_index < 0 or len(expected_sessions) != window_sessions:
            coverage_null_reason = "calendar coverage does not include the complete rolling window"
        elif preceding_session is None:
            coverage_null_reason = "calendar coverage does not include the opening session close"
        elif observed_sessions != window_sessions:
            coverage_null_reason = "one or more expected session-close observations are missing"
        elif window_intervals[0].start_point.event_time != preceding_session.close_time:
            coverage_null_reason = (
                "rolling window opening mark does not match the preceding session close"
            )
        coverage_complete = coverage_null_reason is None

        flow_reports_complete = all(
            item.external_cash_flow_report_status is ExternalCashFlowReportStatus.COMPLETE
            for item in window_intervals
        )
        has_external_flows = any(
            item.external_cash_flow_occurred is True for item in window_intervals
        )
        flow_report_null_reason = (
            "one or more external cash-flow reports are incomplete"
            if not flow_reports_complete
            else None
        )
        weighted_results = None
        if flow_report_null_reason is None and has_external_flows:
            weighted_results = _time_weighted_interval_results(window_intervals)
        flow_return_null_reason = (
            flow_report_null_reason
            if flow_report_null_reason is not None
            else "external cash-flow boundary valuations are required for every reported event"
            if has_external_flows and weighted_results is None
            else None
        )
        observation_digest = content_digest(window_intervals)
        start_label = (
            window_start_session.session_label if window_start_session is not None else None
        )
        basis = (
            f"{window_sessions}-session window ending {endpoint.session_label.isoformat()}; "
            f"expected start={start_label.isoformat() if start_label is not None else 'outside calendar'}; "
            f"observed_sessions={observed_sessions}; coverage_complete={str(coverage_complete).lower()}; "
            f"calendar={calendar_fingerprint}; risk_free_return_per_period={risk_free_return_per_period}; "
            f"periods_per_year={periods_per_year}; observations={observation_digest}"
        )
        sample_size = observed_sessions

        if coverage_null_reason is not None:
            net_pnl = None
            net_pnl_null_reason = coverage_null_reason
        elif not flow_reports_complete:
            net_pnl = None
            net_pnl_null_reason = "one or more external cash-flow reports are incomplete"
        else:
            net_pnl = sum(
                (
                    item.ending_equity
                    - item.starting_equity
                    - (
                        item.external_cash_flow
                        if item.external_cash_flow is not None
                        else Decimal(0)
                    )
                    for item in window_intervals
                ),
                Decimal(0),
            )
            net_pnl_null_reason = None

        equity_metric_null_reason = coverage_null_reason or flow_return_null_reason
        if equity_metric_null_reason is not None:
            rolling_return = None
            annualized_volatility = None
            sharpe_ratio = None
            sortino_ratio = None
            maximum_drawdown = None
            maximum_drawdown_duration = None
            ulcer_index = None
            risk_null_reason = equity_metric_null_reason
            sharpe_null_reason = equity_metric_null_reason
            sortino_null_reason = equity_metric_null_reason
        else:
            first_interval = window_intervals[0]
            last_interval = window_intervals[-1]
            if weighted_results is None:
                rolling_return = (
                    last_interval.ending_equity / first_interval.starting_equity - Decimal(1)
                )
                returns = tuple(
                    item.ending_equity / item.starting_equity - Decimal(1)
                    for item in window_intervals
                )
                equity_values = (window_intervals[0].starting_equity,) + tuple(
                    item.ending_equity for item in window_intervals
                )
            else:
                rolling_growth = Decimal(1)
                equity_values_list = [Decimal(1)]
                returns_list: list[Decimal] = []
                for interval_growth, wealth_marks in weighted_results:
                    returns_list.append(interval_growth - Decimal(1))
                    equity_values_list.extend(
                        rolling_growth * mark for mark in wealth_marks[1:]
                    )
                    rolling_growth *= interval_growth
                rolling_return = rolling_growth - Decimal(1)
                returns = tuple(returns_list)
                equity_values = tuple(equity_values_list)
            if len(returns) < minimum_risk_observations:
                annualized_volatility = None
                sharpe_ratio = None
                sortino_ratio = None
                risk_null_reason = (
                    f"at least {minimum_risk_observations} return observations are required"
                )
                sharpe_null_reason = risk_null_reason
                sortino_null_reason = risk_null_reason
            else:
                mean_return = sum(returns, Decimal(0)) / Decimal(len(returns))
                sample_variance = sum(
                    ((value - mean_return) ** 2 for value in returns), Decimal(0)
                ) / Decimal(len(returns) - 1)
                annualized_volatility = (sample_variance * Decimal(periods_per_year)).sqrt()
                risk_null_reason = None
                if sample_variance == 0:
                    sharpe_ratio = None
                    sharpe_null_reason = "return observations have zero sample variance"
                else:
                    sharpe_ratio = (
                        (mean_return - risk_free_return_per_period)
                        / sample_variance.sqrt()
                        * Decimal(periods_per_year).sqrt()
                    )
                    sharpe_null_reason = None
                downside = tuple(
                    min(value - risk_free_return_per_period, Decimal(0)) for value in returns
                )
                downside_deviation = (
                    sum((value**2 for value in downside), Decimal(0)) / Decimal(len(returns))
                ).sqrt()
                if downside_deviation == 0:
                    sortino_ratio = None
                    sortino_null_reason = (
                        "no downside deviation below the periodic risk-free target"
                    )
                else:
                    sortino_ratio = (
                        (mean_return - risk_free_return_per_period)
                        / downside_deviation
                        * Decimal(periods_per_year).sqrt()
                    )
                    sortino_null_reason = None

            running_peak = equity_values[0]
            drawdowns: list[Decimal] = []
            current_drawdown_duration = 0
            maximum_drawdown_duration = 0
            for equity in equity_values[1:]:
                running_peak = max(running_peak, equity)
                drawdown = equity / running_peak - Decimal(1)
                drawdowns.append(drawdown)
                if drawdown < 0:
                    current_drawdown_duration += 1
                    maximum_drawdown_duration = max(
                        maximum_drawdown_duration, current_drawdown_duration
                    )
                else:
                    current_drawdown_duration = 0
            maximum_drawdown = min(drawdowns, default=Decimal(0))
            ulcer_index = (
                sum((drawdown**2 for drawdown in drawdowns), Decimal(0)) / Decimal(len(drawdowns))
            ).sqrt()

        metric_calculation_basis = basis
        return_calculation_basis = (
            "geometrically linked pre/post-flow subperiod returns; "
            if weighted_results is not None
            else "last close equity divided by first interval opening equity minus one; "
        )
        values: tuple[MetricValue, ...] = (
            _value(
                "rolling_net_pnl",
                net_pnl,
                unit=f"currency:{intervals[0].base_currency}",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "sum of ending-minus-starting equity less complete external cash flows; "
                    f"{metric_calculation_basis}"
                ),
                null_reason=net_pnl_null_reason,
            ),
            _value(
                "rolling_return",
                rolling_return,
                unit="fraction",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=f"{return_calculation_basis}{metric_calculation_basis}",
                null_reason=equity_metric_null_reason,
            ),
            _value(
                "rolling_annualized_volatility",
                annualized_volatility,
                unit="fraction",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                annualization_basis=annualization_basis,
                calculation_basis=(
                    "sample standard deviation of simple session returns multiplied by the square root "
                    f"of sessions per year; {metric_calculation_basis}"
                ),
                null_reason=risk_null_reason,
            ),
            _value(
                "rolling_sharpe_ratio",
                sharpe_ratio,
                unit="ratio",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                annualization_basis=annualization_basis,
                calculation_basis=(
                    "mean simple return less the explicit periodic risk-free target, divided by sample "
                    f"standard deviation and annualized; {metric_calculation_basis}"
                ),
                null_reason=sharpe_null_reason,
            ),
            _value(
                "rolling_sortino_ratio",
                sortino_ratio,
                unit="ratio",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                annualization_basis=annualization_basis,
                calculation_basis=(
                    "mean simple return less the explicit periodic risk-free target, divided by RMS "
                    f"downside and annualized; {metric_calculation_basis}"
                ),
                null_reason=sortino_null_reason,
            ),
            _value(
                "rolling_maximum_drawdown",
                maximum_drawdown,
                unit="fraction",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "minimum sampled close drawdown with the opening equity as initial peak; "
                    f"{metric_calculation_basis}"
                ),
                null_reason=equity_metric_null_reason,
            ),
            _value(
                "rolling_maximum_drawdown_duration",
                None if maximum_drawdown_duration is None else Decimal(maximum_drawdown_duration),
                unit="sessions",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "longest consecutive count of sampled closes below the running peak; "
                    f"{metric_calculation_basis}"
                ),
                null_reason=equity_metric_null_reason,
            ),
            _value(
                "rolling_ulcer_index",
                ulcer_index,
                unit="fraction",
                basis=MetricBasis.NET,
                sample_size=sample_size,
                calculation_basis=(
                    "square root of mean squared close-to-close drawdown fractions; "
                    f"{metric_calculation_basis}"
                ),
                null_reason=equity_metric_null_reason,
            ),
        )
        values = _finalize_metric_values(
            values,
            evidence_references=(
                MetricEvidenceReference("rolling_window_intervals", observation_digest),
                MetricEvidenceReference("session_calendar", calendar_fingerprint),
            ),
            common_calculation_parameters={
                "window_sessions": window_sessions,
                "session_interval_convention": "actual_close_to_close_intervals",
                "external_cash_flow_policy": (
                    "subtract complete flows from net pnl; use explicit pre/post boundaries for flow-bearing return and risk metrics"
                ),
            },
            calculation_parameters_by_metric={
                "rolling_annualized_volatility": {
                    "periods_per_year": periods_per_year,
                    "minimum_risk_observations": minimum_risk_observations,
                },
                "rolling_sharpe_ratio": {
                    "periods_per_year": periods_per_year,
                    "risk_free_return_per_period": risk_free_return_per_period,
                    "minimum_risk_observations": minimum_risk_observations,
                },
                "rolling_sortino_ratio": {
                    "periods_per_year": periods_per_year,
                    "risk_free_return_per_period": risk_free_return_per_period,
                    "minimum_risk_observations": minimum_risk_observations,
                },
            },
        )
        points.append(
            RollingMetricPoint(
                portfolio_fingerprint=portfolio_fingerprint,
                run_attempt_id=run_attempt_id,
                calendar_fingerprint=calendar_fingerprint,
                window_sessions=window_sessions,
                observed_sessions=observed_sessions,
                window_start_session_label=start_label,
                window_end_session_label=endpoint.session_label,
                window_start_point=window_start_point,
                window_end_point=endpoint.end_point,
                coverage_complete=coverage_complete,
                observation_digest=observation_digest,
                metrics=values,
            )
        )
    return tuple(points)


@deterministic_decimal_math
def calculate_session_return_distribution_metrics(
    observations: Sequence[AccountEquityIntervalObservation],
    *,
    calendar: SessionCalendarSnapshot,
    start_session_label: date,
    end_session_label: date,
    quantile_probabilities: Sequence[Decimal] = DEFAULT_SESSION_RETURN_QUANTILE_PROBABILITIES,
    confidence_levels: Sequence[Decimal] = DEFAULT_SESSION_RETURN_CONFIDENCE_LEVELS,
    minimum_observations: int = 2,
) -> SessionReturnDistribution:
    """Summarize exact run-scoped close-to-close session returns without interpolation.

    The inclusive requested range must have one actual session-close interval per
    trading session, with each opening mark at the preceding actual session close.
    Incomplete coverage or external-flow evidence withholds every distribution
    value unless each flow has explicit pre/post boundary marks, in which case
    session returns use the same geometrically linked time-weighted convention.
    """

    if type(start_session_label) is not date or type(end_session_label) is not date:
        raise TypeError("session bounds must be dates, not datetimes")
    if start_session_label > end_session_label:
        raise ValueError("start_session_label must not follow end_session_label")
    if (
        not isinstance(minimum_observations, int)
        or isinstance(minimum_observations, bool)
        or minimum_observations < 2
    ):
        raise ValueError("minimum_observations must be an integer of at least two")

    raw_quantiles = _validate_decimal_series(quantile_probabilities, "quantile_probabilities")
    raw_confidence = _validate_decimal_series(confidence_levels, "confidence_levels")
    if not raw_quantiles or any(not Decimal(0) < value < Decimal(1) for value in raw_quantiles):
        raise ValueError("quantile_probabilities must be strictly between zero and one")
    if not raw_confidence or any(not Decimal(0) < value < Decimal(1) for value in raw_confidence):
        raise ValueError("confidence_levels must be strictly between zero and one")
    if len(set(raw_quantiles)) != len(raw_quantiles):
        raise ValueError("quantile_probabilities must not contain duplicates")
    if len(set(raw_confidence)) != len(raw_confidence):
        raise ValueError("confidence_levels must not contain duplicates")
    quantiles = tuple(sorted(raw_quantiles))
    confidence_levels_sorted = tuple(sorted(raw_confidence))

    intervals, session_by_label = _validated_equity_intervals(observations, calendar)
    if start_session_label not in session_by_label or end_session_label not in session_by_label:
        raise ValueError(
            "session bounds must be actual trading-session labels in the supplied calendar"
        )
    if any(
        item.session_label < start_session_label or item.session_label > end_session_label
        for item in intervals
    ):
        raise ValueError("account equity intervals must be confined to the requested session range")

    calendar_sessions = tuple(session_by_label[label] for label in sorted(session_by_label))
    calendar_session_index = {
        session.session_label: index for index, session in enumerate(calendar_sessions)
    }
    expected_labels = tuple(
        session.session_label
        for session in calendar_sessions
        if start_session_label <= session.session_label <= end_session_label
    )
    observed_labels = tuple(item.session_label for item in intervals)
    coverage_complete = observed_labels == expected_labels
    for item in intervals:
        session_index = calendar_session_index[item.session_label]
        preceding_session = calendar_sessions[session_index - 1] if session_index > 0 else None
        if preceding_session is None or item.start_point.event_time != preceding_session.close_time:
            coverage_complete = False

    flow_reports_complete = all(
        item.external_cash_flow_report_status is ExternalCashFlowReportStatus.COMPLETE
        for item in intervals
    )
    external_flows_occurred = (
        any(item.external_cash_flow_occurred is True for item in intervals)
        if flow_reports_complete
        else None
    )
    observation_digest = content_digest(intervals)
    observed_sessions = len(intervals)
    expected_sessions = len(expected_labels)

    null_reason = None
    weighted_results = None
    if not coverage_complete:
        null_reason = "requested session range is missing observations or preceding actual session-close marks"
    elif not flow_reports_complete:
        null_reason = "one or more external cash-flow reports are incomplete"
    elif external_flows_occurred:
        weighted_results = _time_weighted_interval_results(intervals)
        if weighted_results is None:
            null_reason = (
                "external cash-flow boundary valuations are required for every reported event"
            )
    elif observed_sessions < minimum_observations:
        null_reason = f"at least {minimum_observations} session-return observations are required"
    eligible = null_reason is None
    if eligible:
        if weighted_results is not None:
            returns = tuple(item[0] - Decimal(1) for item in weighted_results)
        else:
            returns = tuple(item.ending_equity / item.starting_equity - Decimal(1) for item in intervals)
    else:
        returns = ()
    returns_flow_adjusted = weighted_results is not None and external_flows_occurred is True
    sorted_returns = tuple(sorted(returns))
    return_basis_prefix = (
        "trading-session flow-adjusted time-weighted returns; "
        if returns_flow_adjusted
        else "trading-session close-to-close simple returns; "
    )
    basis = (
        f"{return_basis_prefix}"
        f"inclusive_range={start_session_label.isoformat()}..{end_session_label.isoformat()}; "
        f"expected_sessions={expected_sessions}; observed_sessions={observed_sessions}; "
        f"coverage_complete={str(coverage_complete).lower()}; "
        f"external_cash_flow_reports_complete={str(flow_reports_complete).lower()}; "
        f"external_flows_occurred={external_flows_occurred}; "
        f"calendar={calendar.fingerprint}; observations={observation_digest}"
    )
    metric_values: list[MetricValue] = []
    distribution_parameters: dict[str, dict[str, Any]] = {}
    for probability in quantiles:
        rank = _ceil_probability_count(observed_sessions, probability) if eligible else None
        value = sorted_returns[rank - 1] if rank is not None else None
        token = _decimal_token(probability)
        distribution_parameters[f"session_return_quantile:p={token}"] = {
            "quantile_probability": probability,
            "minimum_observations": minimum_observations,
            "rank_rule": "ceil(n * probability); one-based nearest-rank; no interpolation",
        }
        metric_values.append(
            _value(
                f"session_return_quantile:p={token}",
                value,
                unit="fraction",
                basis=MetricBasis.NET,
                sample_size=observed_sessions,
                calculation_basis=(
                    f"empirical nearest-rank session-return quantile p={probability}; "
                    f"one-based rank={rank}; no interpolation; {basis}"
                ),
                null_reason=null_reason,
            )
        )

    tail_counts: list[int | None] = []
    for confidence in confidence_levels_sorted:
        tail_count = (
            _ceil_probability_count(observed_sessions, confidence, complement=True)
            if eligible
            else None
        )
        tail_counts.append(tail_count)
        worst_returns = sorted_returns[:tail_count] if tail_count is not None else ()
        value_at_risk = max(Decimal(0), -worst_returns[-1]) if worst_returns else None
        expected_shortfall = (
            max(Decimal(0), -sum(worst_returns, Decimal(0)) / Decimal(tail_count))
            if tail_count is not None
            else None
        )
        token = _decimal_token(confidence)
        distribution_parameters[f"session_return_value_at_risk:c={token}"] = {
            "confidence_level": confidence,
            "minimum_observations": minimum_observations,
            "tail_rule": "ceil(n * (1 - confidence)); nearest-rank boundary; no interpolation",
        }
        distribution_parameters[f"session_return_expected_shortfall:c={token}"] = {
            "confidence_level": confidence,
            "minimum_observations": minimum_observations,
            "tail_rule": "ceil(n * (1 - confidence)); mean worst tail; no interpolation",
        }
        metric_values.extend(
            (
                _value(
                    f"session_return_value_at_risk:c={token}",
                    value_at_risk,
                    unit="fraction",
                    basis=MetricBasis.NET,
                    sample_size=observed_sessions,
                    calculation_basis=(
                        f"non-negative loss at the empirical lower-tail nearest-rank return boundary; "
                        f"confidence={confidence}; tail_observations={tail_count}; no interpolation; {basis}"
                    ),
                    null_reason=null_reason,
                ),
                _value(
                    f"session_return_expected_shortfall:c={token}",
                    expected_shortfall,
                    unit="fraction",
                    basis=MetricBasis.NET,
                    sample_size=observed_sessions,
                    calculation_basis=(
                        f"non-negative mean loss across the worst tail observations; "
                        f"confidence={confidence}; tail_observations={tail_count}; {basis}"
                    ),
                    null_reason=null_reason,
                ),
            )
        )

    structured_metrics = _finalize_metric_values(
        metric_values,
        evidence_references=(
            MetricEvidenceReference("session_equity_intervals", observation_digest),
            MetricEvidenceReference("session_calendar", calendar.fingerprint),
        ),
        common_calculation_parameters={
            "return_convention": (
                "geometrically_linked_pre_post_flow_session_returns"
                if returns_flow_adjusted
                else "simple_close_to_close_session_returns"
            ),
            "coverage_policy": "one interval per actual session with preceding actual close mark",
            "external_cash_flow_policy": (
                "require explicit pre/post boundaries for flow-bearing returns; suppress incomplete evidence"
            ),
        },
        calculation_parameters_by_metric=distribution_parameters,
    )
    return SessionReturnDistribution(
        portfolio_fingerprint=intervals[0].portfolio_fingerprint,
        run_attempt_id=intervals[0].run_attempt_id,
        calendar_fingerprint=calendar.fingerprint,
        start_session_label=start_session_label,
        end_session_label=end_session_label,
        opening_point=intervals[0].start_point,
        closing_point=intervals[-1].end_point,
        expected_sessions=expected_sessions,
        observed_sessions=observed_sessions,
        coverage_complete=coverage_complete,
        external_cash_flow_reports_complete=flow_reports_complete,
        external_flows_occurred=external_flows_occurred,
        minimum_observations=minimum_observations,
        quantile_probabilities=quantiles,
        confidence_levels=confidence_levels_sorted,
        effective_tail_observation_counts=tuple(tail_counts),
        observation_digest=observation_digest,
        metrics=structured_metrics,
        returns_flow_adjusted=returns_flow_adjusted,
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
    net_cost = -sum(cash_effects.values(), Decimal(0)) if cost_reporting_complete else None
    cost_bps = None if notional == 0 or net_cost is None else net_cost / notional * Decimal(10000)
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
                "one or more fill cost reports are incomplete" if net_cost is None else None
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
            component_effects[component_id] if component_cost_complete[component_id] else None
        )
        component_notional = component_notionals[component_id]
        component_bps = (
            None if component_cost is None else component_cost / component_notional * Decimal(10000)
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
    cost_definition_parameters = {
        "cost_model_digests": tuple(
            sorted({cost.cost_model_digest for fill in fill_values for cost in fill.costs})
        ),
        "slippage_benchmark_definition_digests": tuple(
            sorted(
                {
                    cost.benchmark_definition_digest
                    for fill in fill_values
                    for cost in fill.costs
                    if cost.benchmark_definition_digest is not None
                }
            )
        ),
        "cost_report_policy": "null_cost_totals_unless_all_fill_reports_complete",
    }
    cost_sensitive_parameters: dict[str, dict[str, Any]] = {
        "net_execution_cost": cost_definition_parameters,
        "execution_cost_basis_points": {
            **cost_definition_parameters,
            "basis_point_scale": Decimal(10000),
        },
        "component_execution_cost": cost_definition_parameters,
        "component_execution_cost_basis_points": {
            **cost_definition_parameters,
            "basis_point_scale": Decimal(10000),
        },
    }
    for kind in ExecutionCostKind:
        cost_sensitive_parameters[f"reported_{kind.value}_cash_effect"] = {
            **cost_definition_parameters,
            "execution_cost_kind": kind.value,
        }
    return _finalize_metric_values(
        metrics,
        evidence_references=(
            MetricEvidenceReference("fill_cost_observations", observation_digest),
        ),
        calculation_parameters_by_metric=cost_sensitive_parameters,
    )


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
                    None if portfolio_pnl.net_pnl == 0 else item.net_pnl / portfolio_pnl.net_pnl,
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
    component_parameters: dict[str, dict[str, Any]] = {}
    component_evidence: dict[str, tuple[MetricEvidenceReference, ...]] = {}
    for item in components:
        for metric_family in (
            "component_gross_pnl",
            "component_net_pnl",
            "component_net_pnl_contribution",
        ):
            metric_name = f"{metric_family}:{item.component_id}"
            component_parameters[metric_name] = {
                "component_id": item.component_id,
                "attribution_method_digest": item.attribution_method_digest,
            }
            component_evidence[metric_name] = (
                MetricEvidenceReference("component_engine_evidence", item.engine_evidence_digest),
            )
    attribution_input_digest = content_digest(
        {"portfolio_pnl": portfolio_pnl, "component_pnl": components}
    )
    return _finalize_metric_values(
        metrics,
        evidence_references=(
            MetricEvidenceReference("attribution_inputs", attribution_input_digest),
            MetricEvidenceReference(
                "portfolio_engine_evidence", portfolio_pnl.engine_evidence_digest
            ),
            MetricEvidenceReference("result_bundle", portfolio_pnl.result_bundle_digest),
        ),
        evidence_references_by_metric=component_evidence,
        calculation_parameters_by_metric={
            "portfolio_attributed_gross_pnl": {
                "reconciliation_policy": "exact_component_sum_matches_portfolio_gross_pnl",
            },
            "portfolio_attributed_net_pnl": {
                "reconciliation_policy": "exact_component_sum_matches_portfolio_net_pnl",
            },
            **component_parameters,
        },
    )
