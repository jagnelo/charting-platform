from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, localcontext
from typing import TypedDict

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
    MetricEvidenceReference,
    ProductClass,
    ProductRiskModel,
    RiskExposureMeasure,
    RollingMetricPoint,
    SessionReturnDistribution,
)
from app.strategy_lab_v2.metrics import (
    calculate_calendar_period_metrics,
    calculate_capital_margin_utilization_metrics,
    calculate_component_attribution_metrics,
    calculate_execution_cost_metrics,
    calculate_exposure_utilization_metrics,
    calculate_financing_cost_metrics,
    calculate_rolling_equity_metrics,
    calculate_session_return_distribution_metrics,
    calculate_time_weighted_return_metrics,
)
from app.strategy_lab_v2.observations import (
    AccountCapitalMarginObservation,
    AccountEquityIntervalObservation,
    ComponentPnlObservation,
    CostReportStatus,
    ExecutionCostComponent,
    ExecutionCostKind,
    ExternalCashFlowBoundaryObservation,
    ExternalCashFlowReportStatus,
    FillCostObservation,
    FinancingCostObservation,
    FinancingCostReport,
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


class _SessionDistributionArgs(TypedDict):
    calendar: SessionCalendarSnapshot
    start_session_label: date
    end_session_label: date


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
    flow: str | None = "0",
    flow_status: ExternalCashFlowReportStatus = ExternalCashFlowReportStatus.COMPLETE,
    flow_occurred: bool | None = None,
    attempt_id: str = "attempt-1",
) -> AccountEquityIntervalObservation:
    flow_amount = None if flow is None else Decimal(flow)
    if flow_occurred is None:
        if flow_status is ExternalCashFlowReportStatus.COMPLETE:
            flow_occurred = flow_amount != 0
        elif flow_status is ExternalCashFlowReportStatus.PARTIAL and flow_amount not in (
            None,
            Decimal(0),
        ):
            flow_occurred = True
    return AccountEquityIntervalObservation(
        portfolio_fingerprint=PORTFOLIO,
        run_attempt_id=attempt_id,
        calendar_fingerprint=calendar.fingerprint,
        session_label=label,
        start_point=start_point,
        end_point=end_point,
        starting_equity=Decimal(starting_equity),
        ending_equity=Decimal(ending_equity),
        external_cash_flow=flow_amount,
        external_cash_flow_occurred=flow_occurred,
        external_cash_flow_report_status=flow_status,
        base_currency="USD",
        engine_evidence_digest=EVIDENCE,
    )


def _two_session_equity_intervals(
    calendar: SessionCalendarSnapshot,
) -> tuple[AccountEquityIntervalObservation, ...]:
    first_close = ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2)
    second_close = ObservationPoint(datetime(2024, 1, 3, 21, 0, tzinfo=UTC), 3)
    return (
        _equity_interval(
            calendar,
            date(2024, 1, 2),
            ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
            first_close,
            "100000",
            "110000",
        ),
        _equity_interval(
            calendar,
            date(2024, 1, 3),
            first_close,
            second_close,
            "110000",
            "88000",
        ),
    )


def test_account_equity_interval_requires_explicit_cash_flow_evidence_status() -> None:
    calendar = _january_calendar()
    interval = _equity_interval(
        calendar,
        date(2024, 1, 2),
        ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
        ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2),
        "100000",
        "101000",
    )

    with pytest.raises(ValueError, match="complete external cash-flow reports"):
        replace(interval, external_cash_flow=None)
    with pytest.raises(ValueError, match="must state whether flows occurred"):
        replace(interval, external_cash_flow_occurred=None)
    with pytest.raises(ValueError, match="requires flow-occurrence evidence"):
        replace(
            interval,
            external_cash_flow=Decimal("100"),
            external_cash_flow_occurred=False,
        )
    with pytest.raises(ValueError, match="partial external cash-flow reports"):
        replace(
            interval,
            external_cash_flow_report_status=ExternalCashFlowReportStatus.PARTIAL,
            external_cash_flow_occurred=False,
        )
    with pytest.raises(ValueError, match="unavailable external cash-flow reports"):
        replace(
            interval,
            external_cash_flow_report_status=ExternalCashFlowReportStatus.UNAVAILABLE,
        )

    partial = replace(
        interval,
        external_cash_flow=Decimal("100"),
        external_cash_flow_occurred=True,
        external_cash_flow_report_status=ExternalCashFlowReportStatus.PARTIAL,
    )
    partial_unknown = replace(
        interval,
        external_cash_flow=None,
        external_cash_flow_occurred=None,
        external_cash_flow_report_status=ExternalCashFlowReportStatus.PARTIAL,
    )
    net_zero_offsetting = replace(
        interval,
        external_cash_flow=Decimal(0),
        external_cash_flow_occurred=True,
    )
    unavailable = replace(
        interval,
        external_cash_flow=None,
        external_cash_flow_occurred=None,
        external_cash_flow_report_status=ExternalCashFlowReportStatus.UNAVAILABLE,
    )
    assert partial.external_cash_flow_report_status is ExternalCashFlowReportStatus.PARTIAL
    assert partial_unknown.external_cash_flow_occurred is None
    assert interval.external_cash_flow_occurred is False
    assert net_zero_offsetting.external_cash_flow == 0
    assert net_zero_offsetting.external_cash_flow_occurred is True
    assert unavailable.external_cash_flow is None


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


def _capital_margin(
    sequence: int,
    *,
    equity: str,
    initial_requirement: str,
    maintenance_requirement: str,
    initial_capacity: str,
    maintenance_capacity: str,
    run_attempt_id: str = "attempt-1",
    base_currency: str = "USD",
) -> AccountCapitalMarginObservation:
    return AccountCapitalMarginObservation(
        portfolio_fingerprint=PORTFOLIO,
        run_attempt_id=run_attempt_id,
        point=ObservationPoint(START + timedelta(minutes=sequence), sequence),
        account_equity=Decimal(equity),
        initial_margin_requirement=Decimal(initial_requirement),
        maintenance_margin_requirement=Decimal(maintenance_requirement),
        initial_margin_capacity=Decimal(initial_capacity),
        maintenance_margin_capacity=Decimal(maintenance_capacity),
        base_currency=base_currency,
        valuation_evidence_digest=EVIDENCE,
    )


def _financing_observation(
    sequence: int,
    *,
    cash_effect: str,
    event_id: str,
    attempt_id: str = "attempt-1",
) -> FinancingCostObservation:
    return FinancingCostObservation(
        portfolio_fingerprint=PORTFOLIO,
        run_attempt_id=attempt_id,
        point=ObservationPoint(START + timedelta(minutes=sequence), sequence),
        financing_event_id=event_id,
        base_cash_effect=Decimal(cash_effect),
        base_currency="USD",
        financing_model_digest=MODEL,
        engine_evidence_digest=EVIDENCE,
    )


def _financing_report(
    start_sequence: int,
    end_sequence: int,
    *,
    observations: tuple[FinancingCostObservation, ...] = (),
    status: CostReportStatus = CostReportStatus.COMPLETE,
    attempt_id: str = "attempt-1",
) -> FinancingCostReport:
    return FinancingCostReport(
        portfolio_fingerprint=PORTFOLIO,
        run_attempt_id=attempt_id,
        start_point=ObservationPoint(START + timedelta(minutes=start_sequence), start_sequence),
        end_point=ObservationPoint(START + timedelta(minutes=end_sequence), end_sequence),
        base_currency="USD",
        report_status=status,
        engine_evidence_digest=EVIDENCE,
        observations=observations,
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
    assert MetricEvidenceReference("exposure_observations", content_digest(marks)) in (
        metrics["average_gross_notional_to_equity"].evidence_references
    )
    risk_model_parameters = metrics[
        "average_gross_notional_to_equity"
    ].calculation_definition.parameters["risk_model"]
    assert risk_model_parameters["product_class"] == (
        CASH_EQUITY_NOTIONAL_RISK_MODEL.product_class.value
    )
    assert risk_model_parameters["exposure_measure"] == (
        CASH_EQUITY_NOTIONAL_RISK_MODEL.exposure_measure.value
    )
    assert risk_model_parameters["definition_digest"] == (
        CASH_EQUITY_NOTIONAL_RISK_MODEL.definition_digest
    )
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


def test_capital_margin_metrics_use_authoritative_requirements_and_capacities() -> None:
    marks = (
        _capital_margin(
            1,
            equity="100000",
            initial_requirement="20000",
            maintenance_requirement="10000",
            initial_capacity="50000",
            maintenance_capacity="40000",
        ),
        _capital_margin(
            2,
            equity="110000",
            initial_requirement="30000",
            maintenance_requirement="20000",
            initial_capacity="60000",
            maintenance_capacity="40000",
        ),
    )

    metrics = _metric_map(calculate_capital_margin_utilization_metrics(marks))
    assert metrics["average_initial_margin_utilization"].value == Decimal("0.45")
    assert metrics["maximum_initial_margin_utilization"].value == Decimal("0.5")
    assert metrics["average_maintenance_margin_utilization"].value == Decimal("0.375")
    assert metrics["maximum_maintenance_margin_utilization"].value == Decimal("0.5")
    with localcontext() as decimal_context:
        decimal_context.prec = 34
        expected_initial_to_equity = (Decimal("0.2") + Decimal(3) / Decimal(11)) / Decimal(2)
        expected_maintenance_to_equity = (Decimal("0.1") + Decimal(2) / Decimal(11)) / Decimal(2)
        expected_max_initial_to_equity = Decimal(3) / Decimal(11)
        expected_max_maintenance_to_equity = Decimal(2) / Decimal(11)
    assert metrics["average_initial_margin_requirement_to_equity"].value == expected_initial_to_equity
    assert metrics["maximum_initial_margin_requirement_to_equity"].value == expected_max_initial_to_equity
    assert metrics["average_maintenance_margin_requirement_to_equity"].value == expected_maintenance_to_equity
    assert metrics["maximum_maintenance_margin_requirement_to_equity"].value == expected_max_maintenance_to_equity
    assert metrics["average_initial_margin_utilization"].basis is MetricBasis.NET
    assert metrics["average_initial_margin_utilization"].sample_size == 2
    assert "notional_inference" in metrics[
        "average_initial_margin_utilization"
    ].calculation_definition.parameters
    assert metrics["average_initial_margin_utilization"].evidence_references == (
        MetricEvidenceReference("capital_margin_observations", content_digest(marks)),
    )


def test_capital_margin_metrics_reject_mixed_scope_or_unordered_marks() -> None:
    first = _capital_margin(
        1,
        equity="100000",
        initial_requirement="20000",
        maintenance_requirement="10000",
        initial_capacity="50000",
        maintenance_capacity="40000",
    )
    second = _capital_margin(
        2,
        equity="100000",
        initial_requirement="20000",
        maintenance_requirement="10000",
        initial_capacity="50000",
        maintenance_capacity="40000",
    )
    with pytest.raises(ValueError, match="same run attempt"):
        calculate_capital_margin_utilization_metrics((first, replace(second, run_attempt_id="attempt-2")))
    with pytest.raises(ValueError, match="strictly ordered"):
        calculate_capital_margin_utilization_metrics((second, first))
    with pytest.raises(ValueError, match="margin capacities must be positive"):
        replace(first, initial_margin_capacity=Decimal(0))


def test_financing_metrics_separate_complete_costs_from_reported_cash_effects() -> None:
    first = _financing_observation(1, cash_effect="-25", event_id="funding-1")
    second = _financing_observation(2, cash_effect="5", event_id="rebate-1")
    reports = (
        _financing_report(0, 1, observations=(first,)),
        _financing_report(1, 2, observations=(second,)),
    )

    metrics = _metric_map(calculate_financing_cost_metrics(reports))
    assert metrics["financing_event_count"].value == Decimal(2)
    assert metrics["complete_financing_report_count"].value == Decimal(2)
    assert metrics["partial_financing_report_count"].value == Decimal(0)
    assert metrics["unavailable_financing_report_count"].value == Decimal(0)
    assert metrics["reported_financing_cash_effect"].value == Decimal(-20)
    assert metrics["gross_financing_cost"].value == Decimal(25)
    assert metrics["reported_financing_credit"].value == Decimal(5)
    assert metrics["net_financing_cost"].value == Decimal(20)
    assert metrics["net_financing_cost"].unit == "currency:USD"
    assert metrics["net_financing_cost"].calculation_definition.parameters["financing_scope"] == (
        "outside_fill_reports"
    )
    assert metrics["net_financing_cost"].evidence_references == (
        MetricEvidenceReference("financing_cost_reports", content_digest(reports)),
    )


def test_financing_metrics_withhold_net_cost_for_incomplete_reports() -> None:
    observation = _financing_observation(1, cash_effect="-25", event_id="funding-1")
    partial = _financing_report(
        0,
        1,
        observations=(observation,),
        status=CostReportStatus.PARTIAL,
    )
    metrics = _metric_map(calculate_financing_cost_metrics((partial,)))
    assert metrics["reported_financing_cash_effect"].value == Decimal(-25)
    assert metrics["gross_financing_cost"].value is None
    assert metrics["reported_financing_credit"].value == Decimal(0)
    assert metrics["net_financing_cost"].value is None
    assert metrics["net_financing_cost"].null_reason == (
        "one or more financing reports are incomplete"
    )

    unavailable = _financing_report(1, 2, status=CostReportStatus.UNAVAILABLE)
    unavailable_metrics = _metric_map(calculate_financing_cost_metrics((unavailable,)))
    assert unavailable_metrics["financing_event_count"].value == Decimal(0)
    assert unavailable_metrics["net_financing_cost"].value is None


def test_financing_reports_reject_scope_overlap_and_out_of_range_events() -> None:
    first = _financing_observation(1, cash_effect="-25", event_id="funding-1")
    second = _financing_observation(2, cash_effect="-10", event_id="funding-2")
    with pytest.raises(ValueError, match="report's run attempt"):
        calculate_financing_cost_metrics(
            (_financing_report(0, 1, observations=(first,)),
             _financing_report(1, 2, observations=(second,), attempt_id="attempt-2"))
        )
    with pytest.raises(ValueError, match="must not overlap"):
        calculate_financing_cost_metrics(
            (_financing_report(0, 2, observations=(first,)),
             _financing_report(1, 3, observations=(second,)))
        )
    with pytest.raises(ValueError, match="within the report interval"):
        _financing_report(0, 1, observations=(second,))


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
    period_metric = metrics["calendar_period_net_pnl:monthly:month:2024-01"]
    assert period_metric.calculation_definition.parameters["calendar_cadence"] == "monthly"
    assert (
        MetricEvidenceReference("session_calendar", calendar.fingerprint)
        in period_metric.evidence_references
    )
    assert all(item.definition_version == "strategy-lab.metrics.v6" for item in metrics.values())


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
        "external cash-flow boundary valuations are required for every reported event"
    )

    net_zero_flow_intervals = (
        replace(
            flow_intervals[0],
            external_cash_flow=Decimal(0),
            external_cash_flow_occurred=True,
        ),
        flow_intervals[1],
    )
    net_zero_flow_metrics = _metric_map(
        calculate_calendar_period_metrics(
            net_zero_flow_intervals,
            calendar=calendar,
            cadence=RebalanceCadence.MONTHLY,
        )
    )
    assert net_zero_flow_metrics["calendar_period_net_pnl:monthly:month:2024-01"].value == (
        Decimal(7000)
    )
    assert net_zero_flow_metrics["calendar_period_return:monthly:month:2024-01"].value is None
    assert net_zero_flow_metrics["calendar_period_return:monthly:month:2024-01"].null_reason == (
        "external cash-flow boundary valuations are required for every reported event"
    )

    incomplete_flow_intervals = (
        replace(
            flow_intervals[0],
            external_cash_flow_report_status=ExternalCashFlowReportStatus.PARTIAL,
        ),
        flow_intervals[1],
    )
    incomplete_flow_metrics = _metric_map(
        calculate_calendar_period_metrics(
            incomplete_flow_intervals,
            calendar=calendar,
            cadence=RebalanceCadence.MONTHLY,
        )
    )
    net_pnl_metric = incomplete_flow_metrics["calendar_period_net_pnl:monthly:month:2024-01"]
    return_metric = incomplete_flow_metrics["calendar_period_return:monthly:month:2024-01"]
    assert net_pnl_metric.value is None
    assert net_pnl_metric.null_reason == "one or more external cash-flow reports are incomplete"
    assert return_metric.value is None
    assert return_metric.null_reason == "one or more external cash-flow reports are incomplete"

    unavailable_flow_intervals = (
        replace(
            flow_intervals[0],
            external_cash_flow=None,
            external_cash_flow_occurred=None,
            external_cash_flow_report_status=ExternalCashFlowReportStatus.UNAVAILABLE,
        ),
        flow_intervals[1],
    )
    unavailable_flow_metrics = _metric_map(
        calculate_calendar_period_metrics(
            unavailable_flow_intervals,
            calendar=calendar,
            cadence=RebalanceCadence.MONTHLY,
        )
    )
    assert (
        unavailable_flow_metrics["calendar_period_net_pnl:monthly:month:2024-01"].null_reason
        == "one or more external cash-flow reports are incomplete"
    )
    assert (
        unavailable_flow_metrics["calendar_period_return:monthly:month:2024-01"].null_reason
        == "one or more external cash-flow reports are incomplete"
    )

    boundary_flow_intervals = (
        replace(
            flow_intervals[0],
            ending_equity=Decimal("110000"),
            external_cash_flow_boundaries=(
                ExternalCashFlowBoundaryObservation(
                    point=ObservationPoint(datetime(2024, 1, 2, 17, 0, tzinfo=UTC), 4),
                    pre_flow_equity=Decimal("105000"),
                    post_flow_equity=Decimal("110000"),
                    external_cash_flow=Decimal("5000"),
                    engine_evidence_digest=EVIDENCE,
                ),
            ),
        ),
        replace(flow_intervals[1], starting_equity=Decimal("110000"), ending_equity=Decimal("111000")),
    )
    boundary_flow_metrics = _metric_map(
        calculate_calendar_period_metrics(
            boundary_flow_intervals,
            calendar=calendar,
            cadence=RebalanceCadence.MONTHLY,
        )
    )
    assert boundary_flow_metrics["calendar_period_net_pnl:monthly:month:2024-01"].value == (
        Decimal("6000")
    )
    with localcontext() as decimal_context:
        decimal_context.prec = 34
        expected_time_weighted_return = (
            Decimal("105000") / Decimal("100000") * Decimal("111000") / Decimal("110000")
            - Decimal(1)
        )
    actual_time_weighted_return = boundary_flow_metrics[
        "calendar_period_return:monthly:month:2024-01"
    ].value
    assert actual_time_weighted_return is not None
    assert abs(actual_time_weighted_return - expected_time_weighted_return) <= Decimal("1e-33")


def test_time_weighted_returns_exclude_explicit_cash_flow_jumps_and_annualize_elapsed_time() -> (
    None
):
    calendar = _january_calendar()
    interval = _equity_interval(
        calendar,
        date(2024, 1, 2),
        ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
        ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 3),
        "100000",
        "121000",
        flow="5000",
    )
    interval = replace(
        interval,
        external_cash_flow_boundaries=(
            ExternalCashFlowBoundaryObservation(
                point=ObservationPoint(datetime(2024, 1, 2, 17, 0, tzinfo=UTC), 2),
                pre_flow_equity=Decimal("105000"),
                post_flow_equity=Decimal("110000"),
                external_cash_flow=Decimal("5000"),
                engine_evidence_digest=EVIDENCE,
            ),
        ),
    )

    metrics = {
        item.name: item
        for item in calculate_time_weighted_return_metrics(
            (interval,), calendar=calendar, annualization_days=Decimal("365")
        )
    }
    assert metrics["time_weighted_return"].value == Decimal("0.155")
    assert metrics["time_weighted_annualized_return"].value is not None
    assert metrics["time_weighted_annualized_return"].annualization_basis == (
        "elapsed UTC duration; 365 days per year"
    )
    calculation_definition = metrics["time_weighted_return"].calculation_definition
    assert calculation_definition is not None
    assert calculation_definition.parameters["external_cash_flow_policy"] == (
        "requires_complete_reports_and_explicit_pre_post_boundaries"
    )


def test_time_weighted_returns_require_complete_boundary_evidence_and_reconcile_amounts() -> None:
    calendar = _january_calendar()
    interval = _equity_interval(
        calendar,
        date(2024, 1, 2),
        ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
        ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 3),
        "100000",
        "110000",
        flow="5000",
    )
    metrics = calculate_time_weighted_return_metrics((interval,), calendar=calendar)
    assert all(item.value is None for item in metrics)
    assert all(
        item.null_reason
        == "external cash-flow boundary valuations are required for every reported event"
        for item in metrics
    )

    with pytest.raises(ValueError, match="reconcile the interval flow amount"):
        replace(
            interval,
            external_cash_flow_boundaries=(
                ExternalCashFlowBoundaryObservation(
                    point=ObservationPoint(datetime(2024, 1, 2, 17, 0, tzinfo=UTC), 2),
                    pre_flow_equity=Decimal("100000"),
                    post_flow_equity=Decimal("101000"),
                    external_cash_flow=Decimal("1000"),
                    engine_evidence_digest=EVIDENCE,
                ),
            ),
        )


def test_time_weighted_returns_withhold_incomplete_flow_reports() -> None:
    calendar = _january_calendar()
    interval = _equity_interval(
        calendar,
        date(2024, 1, 2),
        ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
        ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 3),
        "100000",
        "110000",
        flow=None,
        flow_status=ExternalCashFlowReportStatus.PARTIAL,
    )
    metrics = calculate_time_weighted_return_metrics((interval,), calendar=calendar)
    assert all(item.value is None for item in metrics)
    assert all(
        item.null_reason == "one or more external cash-flow reports are incomplete"
        for item in metrics
    )


def test_rolling_equity_metrics_emit_reproducible_complete_session_windows() -> None:
    calendar = _january_calendar()
    first_close = ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2)
    second_close = ObservationPoint(datetime(2024, 1, 3, 21, 0, tzinfo=UTC), 3)
    intervals = (
        _equity_interval(
            calendar,
            date(2024, 1, 2),
            ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
            first_close,
            "100000",
            "101000",
        ),
        _equity_interval(
            calendar,
            date(2024, 1, 3),
            first_close,
            second_close,
            "101000",
            "99990",
        ),
    )

    points = calculate_rolling_equity_metrics(
        intervals,
        calendar=calendar,
        window_sessions=2,
        periods_per_year=252,
        risk_free_return_per_period=Decimal(0),
    )

    assert all(isinstance(point, RollingMetricPoint) for point in points)
    first_point, complete_point = points
    assert not first_point.coverage_complete
    assert first_point.observed_sessions == 1
    assert _metric_map(first_point.metrics)["rolling_return"].value is None
    assert complete_point.coverage_complete
    assert complete_point.observed_sessions == 2
    assert complete_point.window_start_session_label == date(2024, 1, 2)
    assert complete_point.window_start_point == intervals[0].start_point
    assert complete_point.window_end_point == second_close
    assert complete_point.observation_digest == content_digest(intervals)
    assert (
        complete_point.fingerprint
        == calculate_rolling_equity_metrics(
            intervals,
            calendar=calendar,
            window_sessions=2,
            periods_per_year=252,
            risk_free_return_per_period=Decimal(0),
        )[-1].fingerprint
    )
    with pytest.raises(ValueError, match="start label must not follow"):
        replace(
            complete_point,
            window_start_session_label=date(2024, 1, 4),
        )
    with pytest.raises(ValueError, match="sample sizes must match"):
        replace(
            complete_point,
            metrics=(replace(complete_point.metrics[0], sample_size=1),)
            + complete_point.metrics[1:],
        )

    metrics = _metric_map(complete_point.metrics)
    assert metrics["rolling_net_pnl"].value == Decimal(-10)
    assert metrics["rolling_return"].value == Decimal("-0.0001")
    assert Decimal("0.22") < metrics["rolling_annualized_volatility"].value < Decimal("0.23")
    assert metrics["rolling_annualized_volatility"].annualization_basis == (
        "sample session-return convention: 252 sessions per year"
    )
    assert metrics["rolling_sharpe_ratio"].value == Decimal(0)
    assert metrics["rolling_sortino_ratio"].value == Decimal(0)
    assert metrics["rolling_maximum_drawdown"].value == Decimal("-0.01")
    assert metrics["rolling_maximum_drawdown_duration"].value == Decimal(1)
    assert Decimal("0.007") < metrics["rolling_ulcer_index"].value < Decimal("0.008")
    assert (
        MetricEvidenceReference("rolling_window_intervals", complete_point.observation_digest)
        in metrics["rolling_net_pnl"].evidence_references
    )
    assert metrics["rolling_sharpe_ratio"].calculation_definition.parameters[
        "risk_free_return_per_period"
    ] == Decimal(0)
    assert all(item.definition_version == "strategy-lab.metrics.v6" for item in metrics.values())

    risk_free_target = Decimal("0.001")
    targeted_metrics = _metric_map(
        calculate_rolling_equity_metrics(
            intervals,
            calendar=calendar,
            window_sessions=2,
            periods_per_year=252,
            risk_free_return_per_period=risk_free_target,
        )[-1].metrics
    )
    with localcontext() as context:
        context.prec = 34
        expected_sharpe = -risk_free_target / Decimal("0.0002").sqrt() * Decimal(252).sqrt()
        expected_sortino = -risk_free_target / Decimal("0.0000605").sqrt() * Decimal(252).sqrt()
    assert targeted_metrics["rolling_sharpe_ratio"].value == expected_sharpe
    assert targeted_metrics["rolling_sortino_ratio"].value == expected_sortino


def test_rolling_equity_metrics_fail_closed_for_missing_sessions_and_marks() -> None:
    calendar = _january_calendar()
    second_close = ObservationPoint(datetime(2024, 1, 3, 21, 0, tzinfo=UTC), 3)
    only_second = _equity_interval(
        calendar,
        date(2024, 1, 3),
        ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2),
        second_close,
        "101000",
        "102000",
    )
    missing = calculate_rolling_equity_metrics(
        (only_second,),
        calendar=calendar,
        window_sessions=2,
        periods_per_year=252,
        risk_free_return_per_period=Decimal(0),
    )[0]
    missing_metrics = _metric_map(missing.metrics)
    assert not missing.coverage_complete
    assert missing.observed_sessions == 1
    assert missing_metrics["rolling_return"].value is None
    assert missing_metrics["rolling_return"].null_reason == (
        "one or more expected session-close observations are missing"
    )

    first_close = ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2)
    wrong_open = _equity_interval(
        calendar,
        date(2024, 1, 2),
        ObservationPoint(datetime(2023, 12, 29, 20, 0, tzinfo=UTC), 1),
        first_close,
        "100000",
        "101000",
    )
    second = replace(only_second, start_point=first_close, starting_equity=Decimal("101000"))
    mismatched = calculate_rolling_equity_metrics(
        (wrong_open, second),
        calendar=calendar,
        window_sessions=2,
        periods_per_year=252,
        risk_free_return_per_period=Decimal(0),
    )[-1]
    assert not mismatched.coverage_complete
    assert _metric_map(mismatched.metrics)["rolling_return"].null_reason == (
        "rolling window opening mark does not match the preceding session close"
    )


def test_rolling_equity_metrics_separate_cash_flow_pnl_and_unavailable_risk() -> None:
    calendar = _january_calendar()
    first_close = ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2)
    second_close = ObservationPoint(datetime(2024, 1, 3, 21, 0, tzinfo=UTC), 3)
    first = _equity_interval(
        calendar,
        date(2024, 1, 2),
        ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
        first_close,
        "100000",
        "106000",
        flow="5000",
    )
    second = _equity_interval(
        calendar,
        date(2024, 1, 3),
        first_close,
        second_close,
        "106000",
        "107000",
    )
    point = calculate_rolling_equity_metrics(
        (first, second),
        calendar=calendar,
        window_sessions=2,
        periods_per_year=252,
        risk_free_return_per_period=Decimal(0),
    )[-1]
    metrics = _metric_map(point.metrics)
    assert point.coverage_complete
    assert metrics["rolling_net_pnl"].value == Decimal(2000)
    assert metrics["rolling_return"].value is None
    assert metrics["rolling_return"].null_reason == (
        "external cash-flow boundary valuations are required for every reported event"
    )
    assert metrics["rolling_annualized_volatility"].value is None
    assert metrics["rolling_maximum_drawdown"].value is None

    net_zero_first = replace(
        first,
        external_cash_flow=Decimal(0),
        external_cash_flow_occurred=True,
    )
    net_zero_metrics = _metric_map(
        calculate_rolling_equity_metrics(
            (net_zero_first, second),
            calendar=calendar,
            window_sessions=2,
            periods_per_year=252,
            risk_free_return_per_period=Decimal(0),
        )[-1].metrics
    )
    assert net_zero_metrics["rolling_net_pnl"].value == Decimal(7000)
    assert net_zero_metrics["rolling_return"].value is None
    assert net_zero_metrics["rolling_return"].null_reason == (
        "external cash-flow boundary valuations are required for every reported event"
    )

    withdrawal_first = _equity_interval(
        calendar,
        date(2024, 1, 2),
        ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
        first_close,
        "100000",
        "96000",
        flow="-5000",
    )
    withdrawal_second = _equity_interval(
        calendar,
        date(2024, 1, 3),
        first_close,
        second_close,
        "96000",
        "97000",
    )
    withdrawal_metrics = _metric_map(
        calculate_rolling_equity_metrics(
            (withdrawal_first, withdrawal_second),
            calendar=calendar,
            window_sessions=2,
            periods_per_year=252,
            risk_free_return_per_period=Decimal(0),
        )[-1].metrics
    )
    assert withdrawal_metrics["rolling_net_pnl"].value == Decimal(2000)

    boundary_first = replace(
        first,
        ending_equity=Decimal("110000"),
        external_cash_flow_boundaries=(
            ExternalCashFlowBoundaryObservation(
                point=ObservationPoint(datetime(2024, 1, 2, 17, 0, tzinfo=UTC), 4),
                pre_flow_equity=Decimal("105000"),
                post_flow_equity=Decimal("110000"),
                external_cash_flow=Decimal("5000"),
                engine_evidence_digest=EVIDENCE,
            ),
        ),
    )
    boundary_second = replace(second, starting_equity=Decimal("110000"), ending_equity=Decimal("111000"))
    boundary_point = calculate_rolling_equity_metrics(
        (boundary_first, boundary_second),
        calendar=calendar,
        window_sessions=2,
        periods_per_year=252,
        risk_free_return_per_period=Decimal(0),
    )[-1]
    boundary_metrics = _metric_map(boundary_point.metrics)
    with localcontext() as decimal_context:
        decimal_context.prec = 34
        expected_boundary_return = (
            Decimal("105000") / Decimal("100000") * Decimal("111000") / Decimal("110000")
            - Decimal(1)
        )
    assert boundary_metrics["rolling_return"].value is not None
    assert abs(boundary_metrics["rolling_return"].value - expected_boundary_return) <= Decimal("1e-33")
    assert boundary_metrics["rolling_maximum_drawdown"].value == Decimal(0)
    assert "geometrically linked pre/post-flow" in boundary_metrics[
        "rolling_return"
    ].calculation_basis

    partial_flow = replace(
        first,
        external_cash_flow=Decimal("5000"),
        external_cash_flow_report_status=ExternalCashFlowReportStatus.PARTIAL,
    )
    incomplete_flow = calculate_rolling_equity_metrics(
        (partial_flow, second),
        calendar=calendar,
        window_sessions=2,
        periods_per_year=252,
        risk_free_return_per_period=Decimal(0),
    )[-1]
    incomplete_metrics = _metric_map(incomplete_flow.metrics)
    assert incomplete_flow.coverage_complete
    assert incomplete_metrics["rolling_net_pnl"].value is None
    assert incomplete_metrics["rolling_net_pnl"].null_reason == (
        "one or more external cash-flow reports are incomplete"
    )
    assert incomplete_metrics["rolling_return"].null_reason == (
        "one or more external cash-flow reports are incomplete"
    )

    unavailable_first = replace(
        first,
        external_cash_flow=None,
        external_cash_flow_occurred=None,
        external_cash_flow_report_status=ExternalCashFlowReportStatus.UNAVAILABLE,
    )
    unavailable_flow = calculate_rolling_equity_metrics(
        (unavailable_first, second),
        calendar=calendar,
        window_sessions=2,
        periods_per_year=252,
        risk_free_return_per_period=Decimal(0),
    )[-1]
    unavailable_metrics = _metric_map(unavailable_flow.metrics)
    assert unavailable_metrics["rolling_net_pnl"].value is None
    assert unavailable_metrics["rolling_return"].null_reason == (
        "one or more external cash-flow reports are incomplete"
    )
    assert unavailable_metrics["rolling_annualized_volatility"].null_reason == (
        "one or more external cash-flow reports are incomplete"
    )


def test_rolling_equity_metrics_apply_minimum_sample_and_zero_risk_rules() -> None:
    calendar = _january_calendar()
    first_close = ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2)
    single_interval = _equity_interval(
        calendar,
        date(2024, 1, 2),
        ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
        first_close,
        "100000",
        "101000",
    )
    one_session = calculate_rolling_equity_metrics(
        (single_interval,),
        calendar=calendar,
        window_sessions=1,
        periods_per_year=252,
        risk_free_return_per_period=Decimal(0),
    )[0]
    one_session_metrics = _metric_map(one_session.metrics)
    assert one_session.coverage_complete
    assert one_session_metrics["rolling_return"].value == Decimal("0.01")
    assert one_session_metrics["rolling_annualized_volatility"].null_reason == (
        "at least 2 return observations are required"
    )

    second_close = ObservationPoint(datetime(2024, 1, 3, 21, 0, tzinfo=UTC), 3)
    next_interval = _equity_interval(
        calendar,
        date(2024, 1, 3),
        first_close,
        second_close,
        "101000",
        "102010",
    )
    zero_risk = calculate_rolling_equity_metrics(
        (single_interval, next_interval),
        calendar=calendar,
        window_sessions=2,
        periods_per_year=252,
        risk_free_return_per_period=Decimal("0.01"),
    )[-1]
    zero_risk_metrics = _metric_map(zero_risk.metrics)
    assert zero_risk_metrics["rolling_annualized_volatility"].value == Decimal(0)
    assert zero_risk_metrics["rolling_sharpe_ratio"].null_reason == (
        "return observations have zero sample variance"
    )
    assert zero_risk_metrics["rolling_sortino_ratio"].null_reason == (
        "no downside deviation below the periodic risk-free target"
    )

    with pytest.raises(ValueError, match="window_sessions"):
        calculate_rolling_equity_metrics(
            (single_interval,),
            calendar=calendar,
            window_sessions=True,
            periods_per_year=252,
            risk_free_return_per_period=Decimal(0),
        )
    with pytest.raises(ValueError, match="periods_per_year"):
        calculate_rolling_equity_metrics(
            (single_interval,),
            calendar=calendar,
            window_sessions=1,
            periods_per_year=0,
            risk_free_return_per_period=Decimal(0),
        )
    with pytest.raises(ValueError, match="risk_free_return_per_period"):
        calculate_rolling_equity_metrics(
            (single_interval,),
            calendar=calendar,
            window_sessions=1,
            periods_per_year=252,
            risk_free_return_per_period=Decimal(-1),
        )
    with pytest.raises(ValueError, match="minimum_risk_observations"):
        calculate_rolling_equity_metrics(
            (single_interval,),
            calendar=calendar,
            window_sessions=1,
            periods_per_year=252,
            risk_free_return_per_period=Decimal(0),
            minimum_risk_observations=1,
        )


def test_session_return_distribution_metrics_use_pinned_nearest_rank_estimators() -> None:
    calendar = _january_calendar()
    intervals = _two_session_equity_intervals(calendar)
    distribution = calculate_session_return_distribution_metrics(
        intervals,
        calendar=calendar,
        start_session_label=date(2024, 1, 2),
        end_session_label=date(2024, 1, 3),
        quantile_probabilities=(Decimal("0.75"), Decimal("0.25")),
        confidence_levels=(Decimal("0.50"), Decimal("0.25")),
    )

    assert isinstance(distribution, SessionReturnDistribution)
    assert distribution.coverage_complete
    assert distribution.expected_sessions == distribution.observed_sessions == 2
    assert distribution.external_cash_flow_reports_complete
    assert distribution.external_flows_occurred is False
    assert distribution.quantile_probabilities == (Decimal("0.25"), Decimal("0.75"))
    assert distribution.confidence_levels == (Decimal("0.25"), Decimal("0.50"))
    assert distribution.effective_tail_observation_counts == (2, 1)
    assert distribution.observation_digest == content_digest(intervals)

    metrics = _metric_map(distribution.metrics)
    assert metrics["session_return_quantile:p=0.25"].value == Decimal("-0.2")
    assert metrics["session_return_quantile:p=0.75"].value == Decimal("0.1")
    assert metrics["session_return_value_at_risk:c=0.25"].value == Decimal(0)
    assert metrics["session_return_expected_shortfall:c=0.25"].value == Decimal("0.05")
    assert metrics["session_return_value_at_risk:c=0.5"].value == Decimal("0.2")
    assert metrics["session_return_expected_shortfall:c=0.5"].value == Decimal("0.2")
    assert all(item.sample_size == 2 for item in metrics.values())
    assert all(item.basis is MetricBasis.NET for item in metrics.values())
    assert all(item.definition_version == "strategy-lab.metrics.v6" for item in metrics.values())
    assert (
        "one-based rank=1; no interpolation"
        in metrics["session_return_quantile:p=0.25"].calculation_basis
    )
    assert (
        MetricEvidenceReference("session_equity_intervals", distribution.observation_digest)
        in metrics["session_return_quantile:p=0.25"].evidence_references
    )
    assert metrics["session_return_quantile:p=0.25"].calculation_definition.parameters[
        "quantile_probability"
    ] == Decimal("0.25")

    canonical_order = calculate_session_return_distribution_metrics(
        intervals,
        calendar=calendar,
        start_session_label=date(2024, 1, 2),
        end_session_label=date(2024, 1, 3),
        quantile_probabilities=(Decimal("0.25"), Decimal("0.75")),
        confidence_levels=(Decimal("0.25"), Decimal("0.50")),
    )
    with localcontext() as decimal_context:
        decimal_context.prec = 7
        low_precision_result = calculate_session_return_distribution_metrics(
            intervals,
            calendar=calendar,
            start_session_label=date(2024, 1, 2),
            end_session_label=date(2024, 1, 3),
            quantile_probabilities=(Decimal("0.75"), Decimal("0.25")),
            confidence_levels=(Decimal("0.50"), Decimal("0.25")),
        )
    assert distribution.fingerprint == canonical_order.fingerprint
    assert distribution.fingerprint == low_precision_result.fingerprint

    tied = (
        replace(
            intervals[0],
            ending_equity=Decimal("105000"),
        ),
        replace(
            intervals[1],
            starting_equity=Decimal("105000"),
            ending_equity=Decimal("110250"),
        ),
    )
    tied_metrics = _metric_map(
        calculate_session_return_distribution_metrics(
            tied,
            calendar=calendar,
            start_session_label=date(2024, 1, 2),
            end_session_label=date(2024, 1, 3),
        ).metrics
    )
    assert tied_metrics["session_return_quantile:p=0.25"].value == Decimal("0.05")
    assert tied_metrics["session_return_quantile:p=0.75"].value == Decimal("0.05")
    assert tied_metrics["session_return_value_at_risk:c=0.95"].value == Decimal(0)
    assert tied_metrics["session_return_expected_shortfall:c=0.95"].value == Decimal(0)

    precision_boundary_intervals = (
        _equity_interval(
            calendar,
            date(2024, 1, 2),
            ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
            ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2),
            "100",
            "60",
        ),
        _equity_interval(
            calendar,
            date(2024, 1, 3),
            ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2),
            ObservationPoint(datetime(2024, 1, 3, 21, 0, tzinfo=UTC), 3),
            "60",
            "72",
        ),
        _equity_interval(
            calendar,
            date(2024, 1, 31),
            ObservationPoint(datetime(2024, 1, 3, 21, 0, tzinfo=UTC), 3),
            ObservationPoint(datetime(2024, 1, 31, 21, 0, tzinfo=UTC), 4),
            "72",
            "93.6",
        ),
    )
    precise_quantile = Decimal("0.3333333333333333333333333333333334")
    precise_confidence = Decimal("0.6666666666666666666666666666666666")
    precision_boundary = calculate_session_return_distribution_metrics(
        precision_boundary_intervals,
        calendar=calendar,
        start_session_label=date(2024, 1, 2),
        end_session_label=date(2024, 1, 31),
        quantile_probabilities=(precise_quantile,),
        confidence_levels=(precise_confidence,),
    )
    precision_metrics = _metric_map(precision_boundary.metrics)
    assert precision_metrics[
        "session_return_quantile:p=0.3333333333333333333333333333333334"
    ].value == Decimal("0.2")
    assert precision_boundary.effective_tail_observation_counts == (2,)
    assert precision_metrics[
        "session_return_expected_shortfall:c=0.6666666666666666666666666666666666"
    ].value == Decimal("0.1")

    with pytest.raises(ValueError, match="complete distributions require"):
        replace(distribution, observed_sessions=1)
    with pytest.raises(ValueError, match="tail observation counts must align"):
        replace(distribution, effective_tail_observation_counts=(1,))
    with pytest.raises(ValueError, match="observed sample count"):
        replace(
            distribution,
            metrics=(replace(distribution.metrics[0], sample_size=1),) + distribution.metrics[1:],
        )


def test_session_return_distribution_metrics_fail_closed_on_coverage_and_flow_evidence() -> None:
    calendar = _january_calendar()
    intervals = _two_session_equity_intervals(calendar)
    common: _SessionDistributionArgs = {
        "calendar": calendar,
        "start_session_label": date(2024, 1, 2),
        "end_session_label": date(2024, 1, 3),
    }

    missing_start = calculate_session_return_distribution_metrics((intervals[1],), **common)
    assert not missing_start.coverage_complete
    assert missing_start.expected_sessions == 2
    assert missing_start.observed_sessions == 1
    assert all(item.value is None for item in missing_start.metrics)
    assert all(
        item.null_reason
        == "requested session range is missing observations or preceding actual session-close marks"
        for item in missing_start.metrics
    )

    wrong_open = replace(
        intervals[0],
        start_point=ObservationPoint(datetime(2023, 12, 29, 20, 0, tzinfo=UTC), 1),
    )
    wrong_open_result = calculate_session_return_distribution_metrics(
        (wrong_open, intervals[1]), **common
    )
    assert not wrong_open_result.coverage_complete
    assert all(item.value is None for item in wrong_open_result.metrics)

    multi_session_gap = replace(
        intervals[1],
        session_label=date(2024, 1, 31),
        end_point=ObservationPoint(datetime(2024, 1, 31, 21, 0, tzinfo=UTC), 4),
    )
    gap_result = calculate_session_return_distribution_metrics(
        (intervals[0], multi_session_gap),
        calendar=calendar,
        start_session_label=date(2024, 1, 2),
        end_session_label=date(2024, 1, 31),
    )
    assert not gap_result.coverage_complete
    assert gap_result.expected_sessions == 3
    assert gap_result.observed_sessions == 2
    assert all(item.value is None for item in gap_result.metrics)

    nontrading_end: _SessionDistributionArgs = {
        **common,
        "end_session_label": date(2024, 1, 4),
    }
    with pytest.raises(ValueError, match="actual trading-session labels"):
        calculate_session_return_distribution_metrics(intervals, **nontrading_end)
    with pytest.raises(ValueError, match="same run attempt"):
        calculate_session_return_distribution_metrics(
            (intervals[0], replace(intervals[1], run_attempt_id="attempt-2")), **common
        )
    with pytest.raises(ValueError, match="bind the supplied calendar version"):
        calculate_session_return_distribution_metrics(
            (replace(intervals[0], calendar_fingerprint=content_digest("other-calendar")),),
            **common,
        )

    net_zero_flow = replace(
        intervals[0],
        external_cash_flow=Decimal(0),
        external_cash_flow_occurred=True,
    )
    flow_result = calculate_session_return_distribution_metrics(
        (net_zero_flow, intervals[1]), **common
    )
    assert flow_result.external_cash_flow_reports_complete
    assert flow_result.external_flows_occurred is True
    assert flow_result.observed_sessions == 2
    assert all(item.value is None for item in flow_result.metrics)
    assert all(
        item.null_reason == "external cash-flow boundary valuations are required for every reported event"
        for item in flow_result.metrics
    )

    boundary_flow = replace(
        intervals[0],
        ending_equity=Decimal("110000"),
        external_cash_flow=Decimal("5000"),
        external_cash_flow_occurred=True,
        external_cash_flow_boundaries=(
            ExternalCashFlowBoundaryObservation(
                point=ObservationPoint(datetime(2024, 1, 2, 17, 0, tzinfo=UTC), 4),
                pre_flow_equity=Decimal("105000"),
                post_flow_equity=Decimal("110000"),
                external_cash_flow=Decimal("5000"),
                engine_evidence_digest=EVIDENCE,
            ),
        ),
    )
    boundary_distribution = calculate_session_return_distribution_metrics(
        (boundary_flow, replace(intervals[1], starting_equity=Decimal("110000"))), **common
    )
    assert boundary_distribution.returns_flow_adjusted
    assert all(item.value is not None for item in boundary_distribution.metrics)

    partial_flow = replace(
        intervals[0],
        external_cash_flow=Decimal("100"),
        external_cash_flow_occurred=True,
        external_cash_flow_report_status=ExternalCashFlowReportStatus.PARTIAL,
    )
    partial_result = calculate_session_return_distribution_metrics(
        (partial_flow, intervals[1]), **common
    )
    assert not partial_result.external_cash_flow_reports_complete
    assert partial_result.external_flows_occurred is None
    assert partial_result.observed_sessions == 2
    assert all(
        item.null_reason == "one or more external cash-flow reports are incomplete"
        for item in partial_result.metrics
    )

    unavailable_flow = replace(
        intervals[0],
        external_cash_flow=None,
        external_cash_flow_occurred=None,
        external_cash_flow_report_status=ExternalCashFlowReportStatus.UNAVAILABLE,
    )
    unavailable_result = calculate_session_return_distribution_metrics(
        (unavailable_flow, intervals[1]), **common
    )
    assert all(item.value is None for item in unavailable_result.metrics)
    assert all(
        item.null_reason == "one or more external cash-flow reports are incomplete"
        for item in unavailable_result.metrics
    )


def test_session_return_distribution_metrics_validate_parameters_minimum_sample_and_early_close() -> (
    None
):
    calendar = _january_calendar()
    single_interval = _equity_interval(
        calendar,
        date(2024, 1, 2),
        ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
        ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2),
        "100000",
        "101000",
    )
    insufficient = calculate_session_return_distribution_metrics(
        (single_interval,),
        calendar=calendar,
        start_session_label=date(2024, 1, 2),
        end_session_label=date(2024, 1, 2),
    )
    assert insufficient.coverage_complete
    assert insufficient.expected_sessions == insufficient.observed_sessions == 1
    assert insufficient.effective_tail_observation_counts == (None,)
    assert all(item.value is None for item in insufficient.metrics)
    assert all(
        item.null_reason == "at least 2 session-return observations are required"
        for item in insufficient.metrics
    )

    with pytest.raises(ValueError, match="strictly between zero and one"):
        calculate_session_return_distribution_metrics(
            (single_interval,),
            calendar=calendar,
            start_session_label=date(2024, 1, 2),
            end_session_label=date(2024, 1, 2),
            quantile_probabilities=(Decimal(0),),
        )
    with pytest.raises(ValueError, match="strictly between zero and one"):
        calculate_session_return_distribution_metrics(
            (single_interval,),
            calendar=calendar,
            start_session_label=date(2024, 1, 2),
            end_session_label=date(2024, 1, 2),
            confidence_levels=(Decimal(1),),
        )
    with pytest.raises(ValueError, match="must not contain duplicates"):
        calculate_session_return_distribution_metrics(
            (single_interval,),
            calendar=calendar,
            start_session_label=date(2024, 1, 2),
            end_session_label=date(2024, 1, 2),
            quantile_probabilities=(Decimal("0.5"), Decimal("0.50")),
        )
    with pytest.raises(ValueError, match="minimum_observations"):
        calculate_session_return_distribution_metrics(
            (single_interval,),
            calendar=calendar,
            start_session_label=date(2024, 1, 2),
            end_session_label=date(2024, 1, 2),
            minimum_observations=True,
        )
    with pytest.raises(ValueError, match="start_session_label must not follow"):
        calculate_session_return_distribution_metrics(
            (single_interval,),
            calendar=calendar,
            start_session_label=date(2024, 1, 3),
            end_session_label=date(2024, 1, 2),
        )

    early_close_time = datetime(2024, 1, 2, 18, 0, tzinfo=UTC)
    early_session = TradingSession(
        "XNYS:2024-01-02:early-close",
        date(2024, 1, 2),
        (
            SessionSegment(
                datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
                early_close_time,
            ),
        ),
    )
    early_calendar = replace(
        calendar,
        days=tuple(
            replace(day, session=early_session) if day.label == date(2024, 1, 2) else day
            for day in calendar.days
        ),
        source_evidence_digest=content_digest("january-early-close-calendar-source-v1"),
    )
    first_early_close = ObservationPoint(early_close_time, 2)
    second_close = ObservationPoint(datetime(2024, 1, 3, 21, 0, tzinfo=UTC), 3)
    early_intervals = (
        _equity_interval(
            early_calendar,
            date(2024, 1, 2),
            ObservationPoint(datetime(2023, 12, 29, 21, 0, tzinfo=UTC), 1),
            first_early_close,
            "100000",
            "105000",
        ),
        _equity_interval(
            early_calendar,
            date(2024, 1, 3),
            first_early_close,
            second_close,
            "105000",
            "110250",
        ),
    )
    early_result = calculate_session_return_distribution_metrics(
        early_intervals,
        calendar=early_calendar,
        start_session_label=date(2024, 1, 2),
        end_session_label=date(2024, 1, 3),
    )
    assert early_result.coverage_complete
    assert early_result.metrics[0].value is not None
    early_close_by_label = {
        day.label: day.session.close_time for day in early_calendar.days if day.session is not None
    }
    assert all(
        item.end_point.event_time == early_close_by_label[item.session_label]
        for item in early_intervals
    )


def test_calendar_period_metrics_reject_mixed_runs_unmatched_marks_and_wrong_calendar() -> None:
    calendar = _january_calendar()
    start = ObservationPoint(datetime(2024, 1, 1, 20, 0, tzinfo=UTC), 1)
    first_close = ObservationPoint(datetime(2024, 1, 2, 21, 0, tzinfo=UTC), 2)
    last_close = ObservationPoint(datetime(2024, 1, 31, 21, 0, tzinfo=UTC), 3)
    first = _equity_interval(calendar, date(2024, 1, 2), start, first_close, "100000", "101000")
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
            (
                replace(
                    first, end_point=ObservationPoint(datetime(2024, 1, 2, 20, 0, tzinfo=UTC), 2)
                ),
            ),
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
    assert (
        MetricEvidenceReference("fill_cost_observations", content_digest(fills))
        in metrics["net_execution_cost"].evidence_references
    )
    assert metrics["net_execution_cost"].calculation_definition.parameters[
        "cost_model_digests"
    ] == (MODEL,)
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
    metrics = _metric_map(calculate_execution_cost_metrics((unavailable,), base_currency="USD"))

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
    partial_metrics = _metric_map(calculate_execution_cost_metrics((partial,), base_currency="USD"))
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
    assert (
        metrics["component_net_pnl:alpha"].calculation_definition.parameters[
            "attribution_method_digest"
        ]
        == METHOD
    )
    assert (
        MetricEvidenceReference("component_engine_evidence", EVIDENCE)
        in metrics["component_net_pnl:alpha"].evidence_references
    )
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
