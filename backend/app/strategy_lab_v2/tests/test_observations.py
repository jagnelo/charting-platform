from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from app.strategy_lab_v2.allocation import (
    ComponentPositionExposure,
    InstrumentRiskBinding,
    PortfolioExposureSnapshot,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    MetricBasis,
    ProductClass,
    ProductRiskModel,
    RiskExposureMeasure,
)
from app.strategy_lab_v2.metrics import (
    calculate_calendar_period_metrics,
    calculate_component_attribution_metrics,
    calculate_execution_cost_metrics,
    calculate_exposure_utilization_metrics,
)
from app.strategy_lab_v2.observations import (
    AccountEquityIntervalObservation,
    ComponentPnlObservation,
    CostReportStatus,
    ExecutionCostComponent,
    ExecutionCostKind,
    FillCostObservation,
    ObservationPoint,
    PortfolioPnlObservation,
)
from app.strategy_lab_v2.rebalance import (
    CalendarDay,
    CalendarDayStatus,
    RebalanceCadence,
    SessionCalendarSnapshot,
    SessionSegment,
    TradingSession,
)

PORTFOLIO = content_digest("observation-test-portfolio")
EVIDENCE = content_digest("observation-test-evidence")
METHOD = content_digest("component-attribution-method-v1")
RESULT_BUNDLE = content_digest("engine-result-evidence-bundle-v1")
MODEL = content_digest("engine-cost-model-v1")
BENCHMARK = content_digest("slippage-benchmark-v1")
START = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)


def _january_calendar() -> SessionCalendarSnapshot:
    start = date(2023, 12, 1)
    end = date(2024, 1, 31)
    trading_dates = (
        date(2023, 12, 29),
        date(2024, 1, 2),
        date(2024, 1, 3),
        date(2024, 1, 31),
    )
    sessions = {
        label: TradingSession(
            f"XNYS:{label.isoformat()}",
            label,
            (
                SessionSegment(
                    datetime(label.year, label.month, label.day, 14, 30, tzinfo=UTC),
                    datetime(label.year, label.month, label.day, 21, 0, tzinfo=UTC),
                ),
            ),
        )
        for label in trading_dates
    }
    calendar_days: list[CalendarDay] = []
    current = start
    while current <= end:
        calendar_days.append(
            CalendarDay(
                current,
                CalendarDayStatus.TRADING if current in sessions else CalendarDayStatus.CLOSED,
                sessions.get(current),
            )
        )
        current += timedelta(days=1)
    days = tuple(calendar_days)
    return SessionCalendarSnapshot(
        calendar_id="XNYS",
        definition_version="XNYS-reg-hours-v1",
        timezone_name="America/New_York",
        timezone_database_version="2024a-test-fixture",
        coverage_start=start,
        coverage_end=end,
        days=days,
        source_evidence_digest=content_digest("january-equity-calendar-source-v1"),
    )


def _equity_interval(
    calendar: SessionCalendarSnapshot,
    label: date,
    start_point: ObservationPoint,
    end_point: ObservationPoint,
    starting_equity: str,
    ending_equity: str,
    *,
    flow: str = "0",
    attempt_id: str = "attempt-1",
) -> AccountEquityIntervalObservation:
    return AccountEquityIntervalObservation(
        portfolio_fingerprint=PORTFOLIO,
        run_attempt_id=attempt_id,
        calendar_fingerprint=calendar.fingerprint,
        session_label=label,
        start_point=start_point,
        end_point=end_point,
        starting_equity=Decimal(starting_equity),
        ending_equity=Decimal(ending_equity),
        external_cash_flow=Decimal(flow),
        base_currency="USD",
        engine_evidence_digest=EVIDENCE,
    )


def _snapshot(
    sequence: int,
    *,
    equity: str,
    cash: str,
    positions: tuple[tuple[str, str, str], ...],
    risk_model: ProductRiskModel = CASH_EQUITY_NOTIONAL_RISK_MODEL,
    run_attempt_id: str = "attempt-1",
) -> PortfolioExposureSnapshot:
    return PortfolioExposureSnapshot(
        portfolio_fingerprint=PORTFOLIO,
        run_attempt_id=run_attempt_id,
        event_time=START + timedelta(minutes=sequence),
        event_sequence=sequence,
        account_equity=Decimal(equity),
        account_cash_balance=Decimal(cash),
        base_currency="USD",
        valuation_evidence_digest=EVIDENCE,
        positions=tuple(
            ComponentPositionExposure(component, instrument, Decimal(amount))
            for component, instrument, amount in positions
        ),
        instrument_risk_models=tuple(
            InstrumentRiskBinding(instrument, risk_model)
            for instrument in sorted({instrument for _, instrument, _ in positions})
        ),
    )


def _cost(
    cost_id: str,
    kind: ExecutionCostKind,
    base_effect: str,
    *,
    native_currency: str = "USD",
    native_effect: str | None = None,
    fx_evidence: str | None = None,
    benchmark: str | None = None,
) -> ExecutionCostComponent:
    return ExecutionCostComponent(
        cost_component_id=cost_id,
        kind=kind,
        native_currency=native_currency,
        native_cash_effect=Decimal(native_effect or base_effect),
        base_currency="USD",
        base_cash_effect=Decimal(base_effect),
        cost_model_digest=MODEL,
        evidence_digest=EVIDENCE,
        fx_conversion_evidence_digest=fx_evidence,
        benchmark_definition_digest=benchmark,
    )


def _fill(
    fill_id: str,
    component_id: str,
    notional: str,
    *,
    sequence: int,
    costs: tuple[ExecutionCostComponent, ...] = (),
    cost_report_status: CostReportStatus = CostReportStatus.COMPLETE,
    run_attempt_id: str = "attempt-1",
) -> FillCostObservation:
    return FillCostObservation(
        portfolio_fingerprint=PORTFOLIO,
        run_attempt_id=run_attempt_id,
        point=ObservationPoint(START + timedelta(minutes=sequence), sequence),
        fill_id=fill_id,
        component_id=component_id,
        instrument_id="US.AAPL",
        traded_base_notional=Decimal(notional),
        base_currency="USD",
        engine_evidence_digest=EVIDENCE,
        cost_report_status=cost_report_status,
        costs=costs,
    )


def _pnl_component(
    component_id: str,
    gross: str,
    costs: str,
    rebates: str,
    net: str,
) -> ComponentPnlObservation:
    return ComponentPnlObservation(
        portfolio_fingerprint=PORTFOLIO,
        run_attempt_id="attempt-1",
        point=ObservationPoint(START + timedelta(days=5), 100),
        component_id=component_id,
        gross_pnl=Decimal(gross),
        cost_deductions=Decimal(costs),
        rebates=Decimal(rebates),
        net_pnl=Decimal(net),
        base_currency="USD",
        attribution_method_digest=METHOD,
        result_bundle_digest=RESULT_BUNDLE,
        engine_evidence_digest=EVIDENCE,
    )


def _metric_map(values):
    return {item.name: item for item in values}


def test_observation_points_normalize_offsets_and_preserve_sequence_order() -> None:
    utc_point = ObservationPoint(START, 10)
    offset_point = ObservationPoint(
        datetime(2024, 1, 2, 16, 0, tzinfo=timezone(timedelta(hours=1))), 10
    )

    assert offset_point == utc_point
    assert ObservationPoint(START, 11) > utc_point
    with pytest.raises(ValueError, match="timezone-aware"):
        ObservationPoint(datetime(2024, 1, 2), 1)


def test_exposure_metrics_are_ordered_event_weighted_and_not_margin_utilization() -> None:
    marks = (
        _snapshot(
            1,
            equity="100000",
            cash="60000",
            positions=(
                ("alpha", "US.AAPL", "40000"),
                ("beta", "US.MSFT", "-10000"),
            ),
        ),
        _snapshot(
            2,
            equity="120000",
            cash="60000",
            positions=(("alpha", "US.AAPL", "80000"),),
        ),
    )

    metrics = _metric_map(calculate_exposure_utilization_metrics(marks))
    with localcontext() as decimal_context:
        decimal_context.prec = 34
        average_gross = (Decimal("0.5") + Decimal(2) / Decimal(3)) / Decimal(2)
        average_net = (Decimal("0.3") + Decimal(2) / Decimal(3)) / Decimal(2)
        maximum_gross = Decimal(2) / Decimal(3)

    assert metrics["average_gross_notional_to_equity"].value == average_gross
    assert metrics["maximum_gross_notional_to_equity"].value == maximum_gross
    assert metrics["average_net_notional_to_equity"].value == average_net
    assert metrics["maximum_absolute_net_notional_to_equity"].value == maximum_gross
    assert metrics["average_cash_balance_to_equity"].value == Decimal("0.55")
    assert "not margin usage" in metrics["maximum_gross_notional_to_equity"].calculation_basis
    assert content_digest(marks) in metrics["average_gross_notional_to_equity"].calculation_basis
    assert metrics["average_gross_notional_to_equity"].basis is MetricBasis.GROSS
    permuted = _snapshot(
        1,
        equity="100000",
        cash="60000",
        positions=(
            ("beta", "US.MSFT", "-10000"),
            ("alpha", "US.AAPL", "40000"),
        ),
    )
    assert permuted.positions == marks[0].positions
    assert permuted.fingerprint == marks[0].fingerprint
    mixed_attempt = replace(marks[1], run_attempt_id="attempt-2")
    with pytest.raises(ValueError, match="same run attempt"):
        calculate_exposure_utilization_metrics((marks[0], mixed_attempt))


def test_exposure_metrics_reject_reordered_and_unsupported_product_marks() -> None:
    first = _snapshot(
        1,
        equity="100000",
        cash="50000",
        positions=(("alpha", "US.AAPL", "50000"),),
    )
    second = _snapshot(
        2,
        equity="100000",
        cash="50000",
        positions=(("alpha", "US.AAPL", "50000"),),
    )
    with pytest.raises(ValueError, match="strictly ordered"):
        calculate_exposure_utilization_metrics((second, first))

    option_model = ProductRiskModel(
        ProductClass.OPTION,
        RiskExposureMeasure.SIGNED_BASE_NOTIONAL,
        content_digest("unsupported-option-model"),
    )
    unsupported = replace(
        first,
        instrument_risk_models=(InstrumentRiskBinding("US.AAPL", option_model),),
    )
    with pytest.raises(ValueError, match="unsupported exposure risk model"):
        calculate_exposure_utilization_metrics((unsupported,))


def test_calendar_period_metrics_reconcile_complete_period_pnl_and_return() -> None:
    calendar = _january_calendar()
    start = ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1)
    first_close = ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2)
    last_close = ObservationPoint(datetime(2024, 1, 31, 21, 0, tzinfo=UTC), 3)
    intervals = (
        _equity_interval(
            calendar,
            date(2024, 1, 2),
            start,
            first_close,
            "100000",
            "101000",
        ),
        _equity_interval(
            calendar,
            date(2024, 1, 31),
            first_close,
            last_close,
            "101000",
            "102000",
        ),
    )

    metrics = _metric_map(
        calculate_calendar_period_metrics(
            intervals,
            calendar=calendar,
            cadence=RebalanceCadence.MONTHLY,
        )
    )

    assert metrics["calendar_period_net_pnl:monthly:month:2024-01"].value == Decimal(2000)
    assert metrics["calendar_period_return:monthly:month:2024-01"].value == Decimal("0.02")
    assert metrics["calendar_period_complete:monthly:month:2024-01"].value == Decimal(1)
    assert metrics["calendar_period_return:monthly:month:2024-01"].unit == "fraction"
    assert (
        calendar.fingerprint
        in metrics["calendar_period_net_pnl:monthly:month:2024-01"].calculation_basis
    )
    assert all(item.definition_version == "strategy-lab.metrics.v4" for item in metrics.values())


def test_calendar_period_partial_and_external_flow_returns() -> None:
    calendar = _january_calendar()
    first_close = ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2)
    last_close = ObservationPoint(datetime(2024, 1, 31, 21, 0, tzinfo=UTC), 3)
    partial = _equity_interval(
        calendar,
        date(2024, 1, 31),
        first_close,
        last_close,
        "101000",
        "102000",
    )
    partial_metrics = _metric_map(
        calculate_calendar_period_metrics(
            (partial,), calendar=calendar, cadence=RebalanceCadence.MONTHLY
        )
    )
    assert partial_metrics["calendar_period_complete:monthly:month:2024-01"].value == Decimal(0)
    assert partial_metrics["calendar_period_return:monthly:month:2024-01"].value is None
    assert partial_metrics["calendar_period_return:monthly:month:2024-01"].null_reason == (
        "calendar period coverage is incomplete"
    )

    flow_intervals = (
        _equity_interval(
            calendar,
            date(2024, 1, 2),
            ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
            first_close,
            "100000",
            "106000",
            flow="5000",
        ),
        _equity_interval(
            calendar,
            date(2024, 1, 31),
            first_close,
            last_close,
            "106000",
            "107000",
        ),
    )
    flow_metrics = _metric_map(
        calculate_calendar_period_metrics(
            flow_intervals,
            calendar=calendar,
            cadence=RebalanceCadence.MONTHLY,
        )
    )
    assert flow_metrics["calendar_period_net_pnl:monthly:month:2024-01"].value == Decimal(2000)
    assert flow_metrics["calendar_period_return:monthly:month:2024-01"].value is None
    assert flow_metrics["calendar_period_return:monthly:month:2024-01"].null_reason == (
        "period contains external cash flows; time-weighted return is not implemented"
    )


def test_calendar_period_metrics_reject_mixed_runs_unmatched_marks_and_wrong_calendar() -> None:
    calendar = _january_calendar()
    start = ObservationPoint(datetime(2024, 1, 1, 20, 0, tzinfo=UTC), 1)
    first_close = ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2)
    last_close = ObservationPoint(datetime(2024, 1, 31, 21, 0, tzinfo=UTC), 3)
    first = _equity_interval(
        calendar, date(2024, 1, 2), start, first_close, "100000", "101000"
    )
    second = _equity_interval(
        calendar, date(2024, 1, 31), first_close, last_close, "101000", "102000"
    )

    with pytest.raises(ValueError, match="same run attempt"):
        calculate_calendar_period_metrics(
            (first, replace(second, run_attempt_id="attempt-2")),
            calendar=calendar,
            cadence=RebalanceCadence.MONTHLY,
        )
    with pytest.raises(ValueError, match="contiguous mark chain"):
        calculate_calendar_period_metrics(
            (
                first,
                replace(
                    second,
                    start_point=ObservationPoint(first_close.event_time, 99),
                ),
            ),
            calendar=calendar,
            cadence=RebalanceCadence.MONTHLY,
        )
    with pytest.raises(ValueError, match="official session close"):
        calculate_calendar_period_metrics(
            (replace(first, end_point=ObservationPoint(datetime(2024, 1, 2, 20, 0, tzinfo=UTC), 2)),),
            calendar=calendar,
            cadence=RebalanceCadence.MONTHLY,
        )
    with pytest.raises(ValueError, match="bind the supplied calendar version"):
        calculate_calendar_period_metrics(
            (replace(first, calendar_fingerprint=content_digest("other-calendar")),),
            calendar=calendar,
            cadence=RebalanceCadence.MONTHLY,
        )


def test_execution_cost_metrics_reconcile_fill_cash_effects_and_component_costs() -> None:
    fills = (
        _fill(
            "fill-1",
            "alpha",
            "100000",
            sequence=1,
            costs=(
                _cost("commission", ExecutionCostKind.COMMISSION, "-10"),
                _cost("exchange", ExecutionCostKind.EXCHANGE_FEE, "-2"),
                _cost(
                    "slippage",
                    ExecutionCostKind.SLIPPAGE,
                    "-3",
                    benchmark=BENCHMARK,
                ),
            ),
        ),
        _fill(
            "fill-2",
            "beta",
            "50000",
            sequence=2,
            costs=(_cost("rebate", ExecutionCostKind.REBATE, "1"),),
        ),
    )

    metrics = _metric_map(calculate_execution_cost_metrics(fills, base_currency="usd"))
    with localcontext() as decimal_context:
        decimal_context.prec = 34
        expected_bps = Decimal(14) / Decimal(150000) * Decimal(10000)

    assert metrics["fill_count"].value == Decimal(2)
    assert metrics["traded_base_notional"].value == Decimal(150000)
    assert metrics["net_execution_cost"].value == Decimal(14)
    assert metrics["execution_cost_basis_points"].value == expected_bps
    assert metrics["reported_commission_cash_effect"].value == Decimal(-10)
    assert metrics["reported_rebate_cash_effect"].value == Decimal(1)
    assert metrics["component_execution_cost:alpha"].value == Decimal(15)
    assert metrics["component_execution_cost_basis_points:beta"].value == Decimal("-0.2")
    assert metrics["net_execution_cost"].unit == "currency:USD"
    assert content_digest(fills) in metrics["net_execution_cost"].calculation_basis
    assert calculate_execution_cost_metrics(
        tuple(reversed(fills)), base_currency="USD"
    ) == calculate_execution_cost_metrics(fills, base_currency="USD")

    mixed_attempt = replace(fills[1], run_attempt_id="attempt-2")
    with pytest.raises(ValueError, match="same run attempt"):
        calculate_execution_cost_metrics((fills[0], mixed_attempt), base_currency="USD")


def test_execution_cost_metrics_require_currency_evidence_and_named_slippage_benchmark() -> None:
    with pytest.raises(ValueError, match="benchmark_definition_digest"):
        _cost("slippage", ExecutionCostKind.SLIPPAGE, "-1")
    with pytest.raises(ValueError, match="FX conversion evidence"):
        _cost(
            "foreign-commission",
            ExecutionCostKind.COMMISSION,
            "-1",
            native_currency="EUR",
            native_effect="-1",
        )
    with pytest.raises(ValueError, match="preserve zero versus non-zero"):
        _cost(
            "rounded-zero-conversion",
            ExecutionCostKind.COMMISSION,
            "-1.1",
            native_currency="EUR",
            native_effect="0",
            fx_evidence=content_digest("zero-conversion-evidence"),
        )
    with pytest.raises(ValueError, match="rebate cash effects"):
        _cost("bad-rebate", ExecutionCostKind.REBATE, "-1")

    foreign_cost = _cost(
        "foreign-commission",
        ExecutionCostKind.COMMISSION,
        "-1.1",
        native_currency="EUR",
        native_effect="-1",
        fx_evidence=content_digest("eur-usd-cost-conversion"),
    )
    metrics = _metric_map(
        calculate_execution_cost_metrics(
            (_fill("foreign-fill", "alpha", "1000", sequence=1, costs=(foreign_cost,)),),
            base_currency="USD",
        )
    )
    assert metrics["net_execution_cost"].value == Decimal("1.1")
    with pytest.raises(ValueError, match="requested account base currency"):
        calculate_execution_cost_metrics(
            (_fill("usd-fill", "alpha", "1000", sequence=1),),
            base_currency="EUR",
        )


def test_empty_fill_sample_has_explicit_currency_and_undefined_cost_bps() -> None:
    metrics = _metric_map(calculate_execution_cost_metrics((), base_currency="eur"))

    assert metrics["traded_base_notional"].unit == "currency:EUR"
    assert metrics["net_execution_cost"].value == Decimal(0)
    assert metrics["execution_cost_basis_points"].value is None
    assert metrics["execution_cost_basis_points"].null_reason == "no traded fill notional"


def test_incomplete_fill_cost_reports_never_appear_as_zero_total_cost() -> None:
    unavailable = _fill(
        "fill-costs-unavailable",
        "alpha",
        "10000",
        sequence=1,
        cost_report_status=CostReportStatus.UNAVAILABLE,
    )
    metrics = _metric_map(
        calculate_execution_cost_metrics((unavailable,), base_currency="USD")
    )

    assert metrics["complete_cost_report_fill_count"].value == Decimal(0)
    assert metrics["unavailable_cost_report_fill_count"].value == Decimal(1)
    assert metrics["reported_commission_cash_effect"].value == Decimal(0)
    assert metrics["net_execution_cost"].value is None
    assert metrics["net_execution_cost"].null_reason == (
        "one or more fill cost reports are incomplete"
    )
    assert metrics["execution_cost_basis_points"].value is None
    assert metrics["component_execution_cost:alpha"].value is None

    partial = _fill(
        "fill-costs-partial",
        "beta",
        "20000",
        sequence=2,
        costs=(_cost("known-commission", ExecutionCostKind.COMMISSION, "-2"),),
        cost_report_status=CostReportStatus.PARTIAL,
    )
    partial_metrics = _metric_map(
        calculate_execution_cost_metrics((partial,), base_currency="USD")
    )
    assert partial_metrics["reported_commission_cash_effect"].value == Decimal(-2)
    assert partial_metrics["net_execution_cost"].value is None
    assert partial_metrics["partial_cost_report_fill_count"].value == Decimal(1)

    explicit_zero = _fill("zero-cost", "alpha", "10000", sequence=3)
    complete_metrics = _metric_map(
        calculate_execution_cost_metrics((explicit_zero,), base_currency="USD")
    )
    assert complete_metrics["net_execution_cost"].value == Decimal(0)
    assert complete_metrics["execution_cost_basis_points"].value == Decimal(0)


def test_component_attribution_reconciles_account_pnl_and_records_unallocated_residual() -> None:
    portfolio_pnl = PortfolioPnlObservation(
        portfolio_fingerprint=PORTFOLIO,
        run_attempt_id="attempt-1",
        point=ObservationPoint(START + timedelta(days=5), 100),
        gross_pnl=Decimal("100"),
        net_pnl=Decimal("80"),
        base_currency="USD",
        component_ids=("alpha", "beta"),
        result_bundle_digest=RESULT_BUNDLE,
        engine_evidence_digest=EVIDENCE,
    )
    components = (
        _pnl_component("alpha", "60", "10", "0", "50"),
        _pnl_component("beta", "45", "15", "0", "30"),
        _pnl_component("__unallocated__", "-5", "0", "5", "0"),
    )

    metrics = _metric_map(calculate_component_attribution_metrics(portfolio_pnl, components))

    assert metrics["portfolio_attributed_gross_pnl"].value == Decimal(100)
    assert metrics["portfolio_attributed_net_pnl"].value == Decimal(80)
    assert metrics["component_net_pnl:alpha"].value == Decimal(50)
    assert metrics["component_net_pnl:__unallocated__"].value == Decimal(0)
    assert metrics["component_net_pnl_contribution:alpha"].value == Decimal("0.625")
    assert metrics["component_net_pnl_contribution:beta"].value == Decimal("0.375")
    assert metrics["component_net_pnl_contribution:__unallocated__"].value == Decimal(0)
    assert METHOD in metrics["component_net_pnl:alpha"].calculation_basis
    assert RESULT_BUNDLE in metrics["portfolio_attributed_net_pnl"].calculation_basis
    assert calculate_component_attribution_metrics(
        portfolio_pnl, tuple(reversed(components))
    ) == calculate_component_attribution_metrics(portfolio_pnl, components)


def test_component_attribution_fails_closed_on_unreconciled_or_misaligned_inputs() -> None:
    portfolio_pnl = PortfolioPnlObservation(
        PORTFOLIO,
        "attempt-1",
        ObservationPoint(START + timedelta(days=5), 100),
        Decimal(10),
        Decimal(8),
        "USD",
        ("alpha",),
        RESULT_BUNDLE,
        EVIDENCE,
    )
    component = _pnl_component("alpha", "10", "1", "0", "9")
    with pytest.raises(ValueError, match="does not reconcile to portfolio net P&L"):
        calculate_component_attribution_metrics(portfolio_pnl, (component,))

    duplicate = replace(component, component_id="alpha")
    with pytest.raises(ValueError, match="unique per component"):
        calculate_component_attribution_metrics(portfolio_pnl, (component, duplicate))

    with pytest.raises(ValueError, match="net_pnl must equal"):
        replace(component, net_pnl=Decimal("8"))

    mismatched_bundle = replace(
        component,
        result_bundle_digest=content_digest("another-result-bundle"),
    )
    with pytest.raises(ValueError, match="result evidence bundle"):
        calculate_component_attribution_metrics(portfolio_pnl, (mismatched_bundle,))

    mismatched_attempt = replace(component, run_attempt_id="attempt-2")
    with pytest.raises(ValueError, match="same run attempt"):
        calculate_component_attribution_metrics(portfolio_pnl, (mismatched_attempt,))
