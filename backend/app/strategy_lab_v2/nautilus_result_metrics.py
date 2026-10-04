"""Host-side metric-set construction from a verified native OOS equity trace."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from math import isnan
from pathlib import Path
from typing import Any

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import (
    METRIC_CALCULATION_CONTRACT_VERSION,
    MetricBasis,
    MetricCalculationDefinition,
    MetricEvidenceReference,
    MetricSet,
    MetricValue,
    PortfolioComposition,
)
from app.strategy_lab_v2.decimal_math import DECIMAL_PRECISION, deterministic_decimal_math
from app.strategy_lab_v2.metrics import (
    METRIC_DEFINITION_VERSION,
    calculate_event_aligned_equity_metrics,
    calculate_performance_metrics,
    calculate_session_return_distribution_metrics,
)
from app.strategy_lab_v2.nautilus_equity_trace import NautilusAccountEquityTraceReference
from app.strategy_lab_v2.nautilus_native_reports import (
    NautilusNativeReportsReference,
    iter_nautilus_native_report_records,
)
from app.strategy_lab_v2.observations import AccountEquityIntervalObservation
from app.strategy_lab_v2.rebalance import SessionCalendarSnapshot

_NATIVE_REPORT_TIME_FIELDS = {
    "fills": "ts_event",
    "orders": "ts_init",
    "positions": "ts_opened",
}
_ISO_TIMESTAMP = re.compile(
    r"(?P<whole>.+?)(?:\.(?P<fraction>[0-9]+))?(?P<zone>Z|[+-][0-9]{2}:[0-9]{2})$"
)
_SESSION_RISK_METRIC_NAMES = frozenset(
    {
        "annualized_volatility",
        "sharpe_ratio",
        "sortino_ratio",
        "historical_value_at_risk",
        "historical_expected_shortfall",
    }
)
_SESSION_ANNUALIZED_RISK_METRIC_NAMES = frozenset(
    {"annualized_volatility", "sharpe_ratio", "sortino_ratio"}
)


def _datetime_to_unix_nanoseconds(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    delta = normalized - datetime(1970, 1, 1, tzinfo=UTC)
    elapsed_microseconds = (delta.days * 86_400 + delta.seconds) * 1_000_000
    elapsed_microseconds += delta.microseconds
    return elapsed_microseconds * 1_000


def _session_interval_metrics(
    reference: NautilusAccountEquityTraceReference,
    *,
    observations: Sequence[AccountEquityIntervalObservation] | None,
    calendar: SessionCalendarSnapshot | None,
    periods_per_year: int | None,
    risk_free_return_per_period: Decimal,
    historical_confidence_level: Decimal,
) -> tuple[tuple[MetricValue, ...], str | None]:
    if observations is None:
        if (
            calendar is not None
            or periods_per_year is not None
            or risk_free_return_per_period != Decimal(0)
            or historical_confidence_level != Decimal("0.95")
        ):
            raise ValueError(
                "session calendar and periods_per_year require session equity intervals"
            )
        return (), None
    if calendar is None:
        raise ValueError("session equity intervals require an explicit session calendar")
    if not isinstance(calendar, SessionCalendarSnapshot):
        raise TypeError("session_calendar must be a SessionCalendarSnapshot")
    if (
        not isinstance(periods_per_year, int)
        or isinstance(periods_per_year, bool)
        or periods_per_year < 1
    ):
        raise ValueError("session periods_per_year must be a positive integer")
    if (
        not isinstance(risk_free_return_per_period, Decimal)
        or not risk_free_return_per_period.is_finite()
        or risk_free_return_per_period <= -1
    ):
        raise ValueError("session risk-free return must be finite and greater than -1")
    if (
        not isinstance(historical_confidence_level, Decimal)
        or not historical_confidence_level.is_finite()
        or not Decimal(0) < historical_confidence_level < Decimal(1)
    ):
        raise ValueError("session historical confidence must be strictly between zero and one")
    intervals = tuple(observations)
    if not intervals:
        raise ValueError("session equity intervals must not be empty")
    if any(not isinstance(item, AccountEquityIntervalObservation) for item in intervals):
        raise TypeError(
            "session equity intervals must contain AccountEquityIntervalObservation values"
        )
    if any(
        item.run_attempt_id != reference.attempt_id
        or item.portfolio_fingerprint != reference.portfolio_fingerprint
        or item.base_currency != reference.base_currency
        for item in intervals
    ):
        raise ValueError("session equity intervals differ from the native OOS attempt scope")
    engine_evidence_digests = {item.engine_evidence_digest for item in intervals}
    if len(engine_evidence_digests) != 1:
        raise ValueError("session equity intervals must share one engine evidence digest")
    engine_evidence_digest = next(iter(engine_evidence_digests))
    if reference.scoring_start_ns is None or reference.scoring_end_ns is None:
        raise ValueError("session risk metrics require an OOS evaluation window")
    if _datetime_to_unix_nanoseconds(intervals[0].start_point.event_time) != (
        reference.scoring_start_ns
    ):
        raise ValueError("first session interval must start at the OOS opening valuation")
    if any(
        _datetime_to_unix_nanoseconds(item.end_point.event_time) < reference.scoring_start_ns
        or _datetime_to_unix_nanoseconds(item.end_point.event_time) >= reference.scoring_end_ns
        for item in intervals
    ):
        raise ValueError("session interval closes must fall inside the half-open OOS window")

    distribution = calculate_session_return_distribution_metrics(
        intervals,
        calendar=calendar,
        start_session_label=intervals[0].session_label,
        end_session_label=intervals[-1].session_label,
    )
    metrics = [
        replace(
            metric,
            evidence_references=(
                *metric.evidence_references,
                MetricEvidenceReference("session_engine_evidence", engine_evidence_digest),
            ),
        )
        for metric in distribution.metrics
    ]
    can_calculate_cadence_risk = (
        distribution.coverage_complete
        and distribution.external_cash_flow_reports_complete
        and distribution.external_flows_occurred is False
    )
    if can_calculate_cadence_risk:
        sampled_values = calculate_performance_metrics(
            tuple(item.ending_equity for item in intervals),
            initial_capital=intervals[0].starting_equity,
            base_currency=reference.base_currency,
            periods_per_year=periods_per_year,
            risk_free_return_per_period=risk_free_return_per_period,
            historical_confidence_level=historical_confidence_level,
            basis=MetricBasis.NET,
        )
        for metric in sampled_values:
            if metric.name not in _SESSION_RISK_METRIC_NAMES:
                continue
            definition = metric.calculation_definition
            if definition is None:
                raise ValueError("session risk metrics require versioned calculation definitions")
            parameters = dict(definition.parameters)
            parameters.update(
                {
                    "sampling_basis": "complete_actual_session_close_intervals",
                    "session_calendar_id": calendar.calendar_id,
                    "session_calendar_fingerprint": calendar.fingerprint,
                    "session_interval_observation_digest": distribution.observation_digest,
                }
            )
            annualization_basis = metric.annualization_basis
            if metric.name in _SESSION_ANNUALIZED_RISK_METRIC_NAMES:
                annualization_basis = (
                    f"{periods_per_year} actual session-close intervals per year; "
                    f"calendar={calendar.calendar_id}"
                )
            metrics.append(
                replace(
                    metric,
                    annualization_basis=annualization_basis,
                    calculation_basis=(
                        f"complete actual session-close interval sampling; "
                        f"calendar={calendar.calendar_id}; {metric.calculation_basis}"
                    ),
                    calculation_definition=replace(definition, parameters=parameters),
                    evidence_references=(
                        *metric.evidence_references,
                        MetricEvidenceReference(
                            "session_equity_intervals", distribution.observation_digest
                        ),
                        MetricEvidenceReference("session_engine_evidence", engine_evidence_digest),
                        MetricEvidenceReference("session_calendar", calendar.fingerprint),
                    ),
                )
            )
    return tuple(metrics), content_digest(
        {
            "distribution": distribution,
            "periods_per_year": periods_per_year,
            "risk_free_return_per_period": risk_free_return_per_period,
            "historical_confidence_level": historical_confidence_level,
        }
    )


def _merge_session_metrics(
    event_metrics: Sequence[MetricValue],
    session_metrics: Sequence[MetricValue],
) -> tuple[MetricValue, ...]:
    sampled_risk = {
        (item.name, item.basis): item
        for item in session_metrics
        if item.name in _SESSION_RISK_METRIC_NAMES
    }
    merged = [sampled_risk.get((item.name, item.basis), item) for item in event_metrics]
    merged.extend(item for item in session_metrics if item.name not in _SESSION_RISK_METRIC_NAMES)
    return tuple(merged)


def _build_oos_equity_metric_values(
    reference: NautilusAccountEquityTraceReference,
    equity_marks: Iterable[Decimal],
    *,
    event_time_ns: Iterable[int] | None,
    session_equity_intervals: Sequence[AccountEquityIntervalObservation] | None,
    session_calendar: SessionCalendarSnapshot | None,
    session_periods_per_year: int | None,
    session_risk_free_return_per_period: Decimal,
    session_historical_confidence_level: Decimal,
) -> tuple[tuple[MetricValue, ...], str | None]:
    event_metrics = calculate_event_aligned_equity_metrics(
        equity_marks,
        base_currency=reference.base_currency,
        evidence_digest=reference.artifact.content_digest,
        expected_mark_count=reference.observation_count,
        event_time_ns=event_time_ns,
    )
    session_metrics, session_input_digest = _session_interval_metrics(
        reference,
        observations=session_equity_intervals,
        calendar=session_calendar,
        periods_per_year=session_periods_per_year,
        risk_free_return_per_period=session_risk_free_return_per_period,
        historical_confidence_level=session_historical_confidence_level,
    )
    return _merge_session_metrics(event_metrics, session_metrics), session_input_digest


def build_nautilus_oos_equity_metric_set(
    reference: NautilusAccountEquityTraceReference,
    equity_marks: Iterable[Decimal],
    *,
    event_time_ns: Iterable[int] | None = None,
    created_at: datetime,
    session_equity_intervals: Sequence[AccountEquityIntervalObservation] | None = None,
    session_calendar: SessionCalendarSnapshot | None = None,
    session_periods_per_year: int | None = None,
    session_risk_free_return_per_period: Decimal = Decimal(0),
    session_historical_confidence_level: Decimal = Decimal("0.95"),
) -> MetricSet:
    """Build reproducible official OOS equity metrics for one native attempt.

    ``equity_marks`` must be streamed from the byte-verified Parquet artifact
    identified by ``reference``. Its opening row is the first scoring-window
    account mark and the receipt count is enforced during metric calculation.
    This equity-only builder stays independently usable; the OOS result builder
    composes it with separately verified native execution-report metrics.
    Optional cadence-sensitive statistics require explicit, attempt-bound
    session intervals, their versioned calendar, and a declared sessions-per-
    year convention; irregular event marks never supply cadence implicitly.
    """

    if not isinstance(reference, NautilusAccountEquityTraceReference):
        raise TypeError("reference must be a NautilusAccountEquityTraceReference")
    if reference.evaluation_window_fingerprint is None:
        raise ValueError("official Nautilus metrics require an OOS evaluation window")
    values, session_input_digest = _build_oos_equity_metric_values(
        reference,
        equity_marks,
        event_time_ns=event_time_ns,
        session_equity_intervals=session_equity_intervals,
        session_calendar=session_calendar,
        session_periods_per_year=session_periods_per_year,
        session_risk_free_return_per_period=session_risk_free_return_per_period,
        session_historical_confidence_level=session_historical_confidence_level,
    )
    metric_set_identity = content_digest(
        {
            "attempt_id": reference.attempt_id,
            "definition_version": METRIC_DEFINITION_VERSION,
            "equity_trace_digest": reference.artifact.content_digest,
            "session_input_digest": session_input_digest,
            "trial_id": reference.trial_id,
        }
    )
    return MetricSet(
        metric_set_id=f"metrics-{metric_set_identity.removeprefix('sha256:')}",
        trial_id=reference.trial_id,
        attempt_id=reference.attempt_id,
        definition_version=METRIC_DEFINITION_VERSION,
        values=values,
        created_at=created_at,
    )


def build_nautilus_oos_metric_set(
    equity_reference: NautilusAccountEquityTraceReference,
    equity_marks: Iterable[Decimal],
    native_reports_reference: NautilusNativeReportsReference,
    native_reports_path: str | Path,
    *,
    event_time_ns: Iterable[int] | None = None,
    created_at: datetime,
    portfolio: PortfolioComposition | None = None,
    session_equity_intervals: Sequence[AccountEquityIntervalObservation] | None = None,
    session_calendar: SessionCalendarSnapshot | None = None,
    session_periods_per_year: int | None = None,
    session_risk_free_return_per_period: Decimal = Decimal(0),
    session_historical_confidence_level: Decimal = Decimal("0.95"),
) -> MetricSet:
    """Build one OOS metric set from byte-verified native engine outputs.

    Only rows whose native event timestamp falls in the reference's half-open
    scoring interval contribute to the native-report metrics. Commission and
    realized P&L remain in the currencies printed by Nautilus; no FX conversion
    or missing report field is inferred. Cadence-sensitive risk metrics are
    added only from complete, explicitly supplied session-close intervals and
    their declared calendar and annualization convention.
    """

    _require_matching_oos_references(equity_reference, native_reports_reference)
    if portfolio is not None:
        if not isinstance(portfolio, PortfolioComposition):
            raise TypeError("portfolio must be a PortfolioComposition")
        if (
            portfolio.fingerprint != equity_reference.portfolio_fingerprint
            or portfolio.fingerprint != native_reports_reference.portfolio_fingerprint
        ):
            raise ValueError("component attribution portfolio differs from native result scope")
    if (
        not isinstance(created_at, datetime)
        or created_at.tzinfo is None
        or created_at.utcoffset() is None
    ):
        raise ValueError("created_at must be timezone-aware")

    equity_endpoints: list[Decimal] = []

    def capture_equity_endpoints() -> Iterable[Decimal]:
        for mark in equity_marks:
            if not equity_endpoints:
                equity_endpoints.extend((mark, mark))
            else:
                equity_endpoints[1] = mark
            yield mark

    equity_values, session_input_digest = _build_oos_equity_metric_values(
        equity_reference,
        capture_equity_endpoints(),
        event_time_ns=event_time_ns,
        session_equity_intervals=session_equity_intervals,
        session_calendar=session_calendar,
        session_periods_per_year=session_periods_per_year,
        session_risk_free_return_per_period=session_risk_free_return_per_period,
        session_historical_confidence_level=session_historical_confidence_level,
    )
    native_values = _native_oos_report_metrics(native_reports_reference, native_reports_path)
    component_values: tuple[MetricValue, ...] = ()
    if portfolio is not None:
        from app.strategy_lab_v2.nautilus_component_pnl import (
            build_nautilus_component_pnl_metrics,
        )

        if not equity_endpoints:
            raise ValueError("native equity trace has no OOS account marks")
        component_values = build_nautilus_component_pnl_metrics(
            equity_reference,
            native_reports_reference,
            native_reports_path,
            portfolio,
            account_net_pnl=equity_endpoints[1] - equity_endpoints[0],
        )
    identity = content_digest(
        {
            "attempt_id": equity_reference.attempt_id,
            "definition_version": METRIC_DEFINITION_VERSION,
            "equity_trace_digest": equity_reference.artifact.content_digest,
            "native_reports_digest": native_reports_reference.artifact.content_digest,
            "session_input_digest": session_input_digest,
            "trial_id": equity_reference.trial_id,
            "window_fingerprint": equity_reference.evaluation_window_fingerprint,
        }
    )
    return MetricSet(
        metric_set_id=f"metrics-{identity.removeprefix('sha256:')}",
        trial_id=equity_reference.trial_id,
        attempt_id=equity_reference.attempt_id,
        definition_version=METRIC_DEFINITION_VERSION,
        values=(*equity_values, *native_values, *component_values),
        created_at=created_at,
    )


def _require_matching_oos_references(
    equity: NautilusAccountEquityTraceReference,
    reports: NautilusNativeReportsReference,
) -> None:
    if not isinstance(equity, NautilusAccountEquityTraceReference):
        raise TypeError("equity_reference must be a NautilusAccountEquityTraceReference")
    if not isinstance(reports, NautilusNativeReportsReference):
        raise TypeError("native_reports_reference must be a NautilusNativeReportsReference")
    if equity.evaluation_window_fingerprint is None:
        raise ValueError("official Nautilus metrics require an OOS evaluation window")
    fields = (
        "trial_id",
        "attempt_id",
        "portfolio_fingerprint",
        "snapshot_fingerprint",
        "source_tape_fingerprint",
        "evaluation_window_fingerprint",
        "scoring_start_ns",
        "scoring_end_ns",
    )
    if any(getattr(equity, field) != getattr(reports, field) for field in fields):
        raise ValueError("native reports and account-equity trace do not share one OOS scope")
    if equity.scoring_start_ns is None or equity.scoring_end_ns is None:
        raise ValueError("official Nautilus metrics require explicit OOS scoring bounds")


@deterministic_decimal_math
def _native_oos_report_metrics(
    reference: NautilusNativeReportsReference,
    path: str | Path,
) -> tuple[MetricValue, ...]:
    start_ns = reference.scoring_start_ns
    end_ns = reference.scoring_end_ns
    if start_ns is None or end_ns is None:
        raise ValueError("native report metrics require explicit OOS scoring bounds")

    counts = {kind: 0 for kind in _NATIVE_REPORT_TIME_FIELDS}
    time_coverage = {kind: True for kind in _NATIVE_REPORT_TIME_FIELDS}
    commission_amounts: dict[str, Decimal] = defaultdict(Decimal)
    commission_counts: dict[str, int] = defaultdict(int)
    commission_reported = 0
    commission_unreported = 0
    closed_positions = 0
    closed_position_time_coverage = True
    holding_duration_time_coverage = True
    holding_durations_ns: list[int] = []
    realized_pnl_amounts: dict[str, Decimal] = defaultdict(Decimal)
    realized_pnl_counts: dict[str, int] = defaultdict(int)
    realized_pnl_values: dict[str, list[Decimal]] = defaultdict(list)
    realized_position_win_counts: dict[str, int] = defaultdict(int)
    realized_position_loss_counts: dict[str, int] = defaultdict(int)
    realized_position_break_even_counts: dict[str, int] = defaultdict(int)
    realized_position_gross_wins: dict[str, Decimal] = defaultdict(Decimal)
    realized_position_gross_loss_magnitudes: dict[str, Decimal] = defaultdict(Decimal)
    realized_pnl_unreported = 0
    realized_position_wins = 0
    realized_position_losses = 0
    realized_position_break_even = 0

    for kind, _, row in iter_nautilus_native_report_records(reference, path):
        if kind == "fills":
            timestamp = _row_timestamp_ns(row, "ts_event")
            if timestamp is None:
                time_coverage[kind] = False
                continue
            if start_ns <= timestamp < end_ns:
                counts[kind] += 1
                money = _reported_money(row, "commission")
                if money is None:
                    commission_unreported += 1
                else:
                    currency, amount = money
                    commission_amounts[currency] += amount
                    commission_counts[currency] += 1
                    commission_reported += 1
        elif kind == "orders":
            timestamp = _row_timestamp_ns(row, "ts_init")
            if timestamp is None:
                time_coverage[kind] = False
            elif start_ns <= timestamp < end_ns:
                counts[kind] += 1
        elif kind == "positions":
            opened = _row_timestamp_ns(row, "ts_opened")
            if opened is None:
                time_coverage[kind] = False
            elif start_ns <= opened < end_ns:
                counts[kind] += 1

            if "ts_closed" not in row:
                closed_position_time_coverage = False
                continue
            closed = _row_timestamp_ns(row, "ts_closed")
            if closed is None:
                continue
            if start_ns <= closed < end_ns:
                closed_positions += 1
                if opened is None:
                    holding_duration_time_coverage = False
                elif opened > closed:
                    raise ValueError("native position ts_opened must not follow ts_closed")
                else:
                    holding_durations_ns.append(closed - opened)
                realized = _reported_money(row, "realized_pnl")
                if realized is None:
                    realized_pnl_unreported += 1
                else:
                    currency, amount = realized
                    realized_pnl_amounts[currency] += amount
                    realized_pnl_counts[currency] += 1
                    realized_pnl_values[currency].append(amount)
                    if amount > 0:
                        realized_position_wins += 1
                        realized_position_win_counts[currency] += 1
                        realized_position_gross_wins[currency] += amount
                    elif amount < 0:
                        realized_position_losses += 1
                        realized_position_loss_counts[currency] += 1
                        realized_position_gross_loss_magnitudes[currency] += amount.copy_abs()
                    else:
                        realized_position_break_even += 1
                        realized_position_break_even_counts[currency] += 1

    artifact = reference.artifact.content_digest
    window = reference.evaluation_window_fingerprint
    assert window is not None
    shared_parameters = {
        "evaluation_window_fingerprint": window,
        "scoring_start_ns": start_ns,
        "scoring_end_ns": end_ns,
        "interval_semantics": "half_open_start_inclusive_end_exclusive",
    }
    result: list[MetricValue] = []
    for kind, metric_name in (
        ("orders", "oos_order_submission_count"),
        ("fills", "oos_fill_count"),
        ("positions", "oos_position_records_opened_count"),
    ):
        result.append(
            _native_metric(
                metric_name,
                None if not time_coverage[kind] else Decimal(counts[kind]),
                unit="records",
                sample_size=counts[kind],
                formula=f"count of native {kind} report rows by {_NATIVE_REPORT_TIME_FIELDS[kind]}",
                parameters={
                    "report_kind": kind,
                    "timestamp_field": _NATIVE_REPORT_TIME_FIELDS[kind],
                    **shared_parameters,
                },
                evidence_digest=artifact,
                null_reason=(
                    f"native {kind} report lacks a usable OOS timestamp field"
                    if not time_coverage[kind]
                    else None
                ),
            )
        )

    result.append(
        _native_metric(
            "oos_position_records_closed_count",
            None if not closed_position_time_coverage else Decimal(closed_positions),
            unit="records",
            sample_size=closed_positions,
            formula="count of native position report rows by ts_closed",
            parameters={
                "report_kind": "positions",
                "timestamp_field": "ts_closed",
                **shared_parameters,
            },
            evidence_digest=artifact,
            null_reason=(
                "native positions report lacks ts_closed needed to identify closed records"
                if not closed_position_time_coverage
                else None
            ),
        )
    )
    holding_duration_reported = len(holding_durations_ns)
    holding_duration_coverage_complete = (
        closed_position_time_coverage
        and holding_duration_time_coverage
        and holding_duration_reported == closed_positions
    )
    holding_duration_null_reason = (
        "native positions report lacks complete ts_closed coverage"
        if not closed_position_time_coverage
        else "native positions report lacks ts_opened for one or more OOS-closed positions"
        if not holding_duration_time_coverage
        else None
    )
    holding_seconds = [Decimal(value) / Decimal(1_000_000_000) for value in holding_durations_ns]
    median_holding_seconds = _median_decimal(holding_seconds)
    result.extend(
        (
            _native_metric(
                "oos_position_holding_duration_reported_count",
                None if not closed_position_time_coverage else Decimal(holding_duration_reported),
                unit="positions",
                sample_size=closed_positions,
                formula=("count of OOS-closed native positions with both ts_opened and ts_closed"),
                parameters={
                    "report_kind": "positions",
                    "open_timestamp_field": "ts_opened",
                    "close_timestamp_field": "ts_closed",
                    **shared_parameters,
                },
                evidence_digest=artifact,
                null_reason=(
                    "native positions report lacks complete ts_closed coverage"
                    if not closed_position_time_coverage
                    else None
                ),
            ),
            _native_metric(
                "oos_position_holding_duration_coverage",
                (
                    Decimal(holding_duration_reported) / Decimal(closed_positions)
                    if closed_position_time_coverage and closed_positions > 0
                    else None
                ),
                unit="fraction",
                sample_size=closed_positions,
                formula=(
                    "OOS-closed native positions with both open and close timestamps "
                    "divided by all OOS-closed native positions"
                ),
                parameters={
                    "report_kind": "positions",
                    "open_timestamp_field": "ts_opened",
                    "close_timestamp_field": "ts_closed",
                    **shared_parameters,
                },
                evidence_digest=artifact,
                null_reason=(
                    "native positions report lacks complete ts_closed coverage"
                    if not closed_position_time_coverage
                    else "no OOS-closed native positions"
                    if closed_positions == 0
                    else None
                ),
            ),
            _native_metric(
                "oos_position_mean_holding_duration_seconds",
                (
                    sum(holding_seconds, Decimal(0)) / Decimal(holding_duration_reported)
                    if holding_duration_coverage_complete and holding_duration_reported > 0
                    else None
                ),
                unit="seconds",
                sample_size=holding_duration_reported,
                formula=(
                    "arithmetic mean of full native position ts_closed minus ts_opened "
                    "elapsed durations, in seconds, for positions closed in the half-open OOS window"
                ),
                parameters={
                    "report_kind": "positions",
                    "open_timestamp_field": "ts_opened",
                    "close_timestamp_field": "ts_closed",
                    "duration_basis": "full_position_lifecycle_elapsed_time",
                    "timestamp_unit": "unix_nanoseconds",
                    **shared_parameters,
                },
                evidence_digest=artifact,
                null_reason=(
                    holding_duration_null_reason
                    if not holding_duration_coverage_complete
                    else "no OOS-closed native positions"
                    if closed_positions == 0
                    else None
                ),
            ),
            _native_metric(
                "oos_position_median_holding_duration_seconds",
                (
                    median_holding_seconds
                    if holding_duration_coverage_complete and holding_duration_reported > 0
                    else None
                ),
                unit="seconds",
                sample_size=holding_duration_reported,
                formula=(
                    "median full native position ts_closed minus ts_opened elapsed durations "
                    "in seconds; even samples use the arithmetic mean of the two middle values; "
                    "positions are selected by close timestamp in the half-open OOS window"
                ),
                parameters={
                    "report_kind": "positions",
                    "open_timestamp_field": "ts_opened",
                    "close_timestamp_field": "ts_closed",
                    "duration_basis": "full_position_lifecycle_elapsed_time",
                    "timestamp_unit": "unix_nanoseconds",
                    "median_rule": "middle value; even sample averages the two middle values",
                    **shared_parameters,
                },
                evidence_digest=artifact,
                null_reason=(
                    holding_duration_null_reason
                    if not holding_duration_coverage_complete
                    else "no OOS-closed native positions"
                    if closed_positions == 0
                    else None
                ),
            ),
        )
    )
    realized_pnl_reported_positions = sum(realized_pnl_counts.values())
    realized_pnl_is_complete = closed_position_time_coverage and realized_pnl_unreported == 0
    realized_pnl_null_reason = (
        "native positions report lacks complete ts_closed coverage"
        if not closed_position_time_coverage
        else "native realized P&L is missing for one or more OOS-closed positions"
        if realized_pnl_unreported
        else None
    )
    for name, count, formula in (
        (
            "oos_realized_position_win_count",
            realized_position_wins,
            "count of OOS-closed native positions with strictly positive reported realized P&L",
        ),
        (
            "oos_realized_position_loss_count",
            realized_position_losses,
            "count of OOS-closed native positions with strictly negative reported realized P&L",
        ),
        (
            "oos_realized_position_break_even_count",
            realized_position_break_even,
            "count of OOS-closed native positions with zero reported realized P&L",
        ),
    ):
        result.append(
            _native_metric(
                name,
                Decimal(count) if realized_pnl_is_complete else None,
                unit="positions",
                sample_size=closed_positions,
                formula=formula,
                parameters={
                    "report_kind": "positions",
                    "value_field": "realized_pnl",
                    "realized_pnl_source": "native_positions_report",
                    "currency_aggregation": "sign_only; native currencies are not summed",
                    **shared_parameters,
                },
                evidence_digest=artifact,
                null_reason=realized_pnl_null_reason,
            )
        )

    for name, numerator, formula in (
        (
            "oos_realized_position_win_rate",
            realized_position_wins,
            "OOS-closed positions with positive reported realized P&L divided by all OOS-closed positions",
        ),
        (
            "oos_realized_position_loss_rate",
            realized_position_losses,
            "OOS-closed positions with negative reported realized P&L divided by all OOS-closed positions",
        ),
        (
            "oos_realized_position_break_even_rate",
            realized_position_break_even,
            "OOS-closed positions with zero reported realized P&L divided by all OOS-closed positions",
        ),
    ):
        result.append(
            _native_metric(
                name,
                (
                    Decimal(numerator) / Decimal(closed_positions)
                    if realized_pnl_is_complete and closed_positions > 0
                    else None
                ),
                unit="fraction",
                sample_size=closed_positions,
                formula=formula,
                parameters={
                    "report_kind": "positions",
                    "value_field": "realized_pnl",
                    "realized_pnl_source": "native_positions_report",
                    "currency_aggregation": "sign_only; native currencies are not summed",
                    **shared_parameters,
                },
                evidence_digest=artifact,
                null_reason=(
                    realized_pnl_null_reason
                    if not realized_pnl_is_complete
                    else "no OOS-closed positions"
                    if closed_positions == 0
                    else None
                ),
            )
        )

    result.extend(
        (
            _native_metric(
                "oos_commission_reported_fill_count",
                None if not time_coverage["fills"] else Decimal(commission_reported),
                unit="fills",
                sample_size=counts["fills"],
                formula="count of OOS native fills with an explicit commission amount and currency",
                parameters={"report_kind": "fills", **shared_parameters},
                evidence_digest=artifact,
                null_reason=(
                    "native fills lack complete OOS timestamp coverage"
                    if not time_coverage["fills"]
                    else None
                ),
            ),
            _native_metric(
                "oos_commission_unreported_fill_count",
                None if not time_coverage["fills"] else Decimal(commission_unreported),
                unit="fills",
                sample_size=counts["fills"],
                formula="count of OOS native fills without an explicit commission amount and currency",
                parameters={"report_kind": "fills", **shared_parameters},
                evidence_digest=artifact,
                null_reason=(
                    "native fills lack complete OOS timestamp coverage"
                    if not time_coverage["fills"]
                    else None
                ),
            ),
            _native_metric(
                "oos_commission_reporting_coverage",
                (
                    Decimal(commission_reported) / Decimal(counts["fills"])
                    if counts["fills"] > 0 and time_coverage["fills"]
                    else None
                ),
                unit="ratio",
                sample_size=counts["fills"],
                formula="reported-commission fills divided by OOS native fills",
                parameters={"report_kind": "fills", **shared_parameters},
                evidence_digest=artifact,
                null_reason=(
                    "native fills lack complete OOS timestamp coverage"
                    if not time_coverage["fills"]
                    else "no OOS native fills"
                    if counts["fills"] == 0
                    else None
                ),
            ),
        )
    )
    for currency in sorted(commission_amounts):
        result.append(
            _native_metric(
                f"oos_reported_commission:{currency}",
                commission_amounts[currency],
                unit=f"currency:{currency}",
                sample_size=commission_counts[currency],
                formula="sum of explicitly reported native commission amounts in the named currency; no FX conversion",
                parameters={"currency": currency, "report_kind": "fills", **shared_parameters},
                evidence_digest=artifact,
            )
        )

    result.extend(
        (
            _native_metric(
                "oos_realized_pnl_reported_position_count",
                None
                if not closed_position_time_coverage
                else Decimal(realized_pnl_reported_positions),
                unit="positions",
                sample_size=closed_positions,
                formula="count of OOS-closed native position rows with explicit realized P&L and currency",
                parameters={
                    "report_kind": "positions",
                    "value_field": "realized_pnl",
                    **shared_parameters,
                },
                evidence_digest=artifact,
                null_reason=(
                    "native positions report lacks complete ts_closed coverage"
                    if not closed_position_time_coverage
                    else None
                ),
            ),
            _native_metric(
                "oos_realized_pnl_unreported_position_count",
                None if not closed_position_time_coverage else Decimal(realized_pnl_unreported),
                unit="positions",
                sample_size=closed_positions,
                formula="count of OOS-closed native position rows without explicit realized P&L and currency",
                parameters={
                    "report_kind": "positions",
                    "value_field": "realized_pnl",
                    **shared_parameters,
                },
                evidence_digest=artifact,
                null_reason=(
                    "native positions report lacks complete ts_closed coverage"
                    if not closed_position_time_coverage
                    else None
                ),
            ),
        )
    )
    for currency in sorted(realized_pnl_amounts):
        currency_sample_size = realized_pnl_counts[currency]
        gross_wins = realized_position_gross_wins[currency]
        gross_loss_magnitude = realized_position_gross_loss_magnitudes[currency]
        currency_metrics = (
            (
                "oos_realized_position_win_count",
                Decimal(realized_position_win_counts[currency]),
                "positions",
                "count of OOS-closed native positions with positive realized P&L in the named currency",
                None,
            ),
            (
                "oos_realized_position_loss_count",
                Decimal(realized_position_loss_counts[currency]),
                "positions",
                "count of OOS-closed native positions with negative realized P&L in the named currency",
                None,
            ),
            (
                "oos_realized_position_break_even_count",
                Decimal(realized_position_break_even_counts[currency]),
                "positions",
                "count of OOS-closed native positions with zero realized P&L in the named currency",
                None,
            ),
            (
                "oos_realized_position_win_rate",
                Decimal(realized_position_win_counts[currency]) / Decimal(currency_sample_size),
                "fraction",
                "positive-P&L OOS-closed positions divided by reported OOS-closed positions in the named currency",
                None,
            ),
            (
                "oos_realized_position_loss_rate",
                Decimal(realized_position_loss_counts[currency]) / Decimal(currency_sample_size),
                "fraction",
                "negative-P&L OOS-closed positions divided by reported OOS-closed positions in the named currency",
                None,
            ),
            (
                "oos_realized_position_break_even_rate",
                Decimal(realized_position_break_even_counts[currency])
                / Decimal(currency_sample_size),
                "fraction",
                "zero-P&L OOS-closed positions divided by reported OOS-closed positions in the named currency",
                None,
            ),
            (
                "oos_realized_position_gross_winning_pnl",
                gross_wins,
                f"currency:{currency}",
                "sum of positive native realized position P&L in the named currency",
                None,
            ),
            (
                "oos_realized_position_gross_losing_pnl_magnitude",
                gross_loss_magnitude,
                f"currency:{currency}",
                "absolute sum of negative native realized position P&L in the named currency",
                None,
            ),
            (
                "oos_realized_position_profit_factor",
                gross_wins / gross_loss_magnitude if gross_loss_magnitude > 0 else None,
                "ratio",
                "gross winning native realized position P&L divided by gross losing magnitude in the named currency",
                (
                    None
                    if gross_loss_magnitude > 0
                    else f"no losing OOS-closed positions in {currency}"
                ),
            ),
        )
        for metric_name, metric_value, unit, formula, specific_null_reason in currency_metrics:
            result.append(
                _native_metric(
                    f"{metric_name}:{currency}",
                    metric_value if realized_pnl_is_complete else None,
                    unit=unit,
                    sample_size=currency_sample_size,
                    formula=formula,
                    parameters={
                        "currency": currency,
                        "report_kind": "positions",
                        "value_field": "realized_pnl",
                        "currency_aggregation": "within_currency_only; no FX conversion",
                        **shared_parameters,
                    },
                    evidence_digest=artifact,
                    null_reason=(
                        realized_pnl_null_reason
                        if not realized_pnl_is_complete
                        else specific_null_reason
                    ),
                )
            )
        win_count = realized_position_win_counts[currency]
        loss_count = realized_position_loss_counts[currency]
        mean_loss_magnitude = gross_loss_magnitude / Decimal(loss_count) if loss_count else None
        position_distribution_metrics = (
            (
                "oos_realized_position_mean_pnl",
                realized_pnl_amounts[currency] / Decimal(currency_sample_size),
                f"currency:{currency}",
                "mean native realized P&L per reported OOS-closed position in the named currency",
                None,
                currency_sample_size,
            ),
            (
                "oos_realized_position_mean_win_pnl",
                gross_wins / Decimal(win_count) if win_count else None,
                f"currency:{currency}",
                "mean positive native realized P&L per winning OOS-closed position in the named currency",
                f"no winning OOS-closed positions in {currency}" if not win_count else None,
                win_count,
            ),
            (
                "oos_realized_position_mean_loss_pnl",
                -mean_loss_magnitude if mean_loss_magnitude is not None else None,
                f"currency:{currency}",
                "mean negative native realized P&L per losing OOS-closed position in the named currency",
                f"no losing OOS-closed positions in {currency}" if not loss_count else None,
                loss_count,
            ),
            (
                "oos_realized_position_win_loss_ratio",
                (
                    (gross_wins / Decimal(win_count)) / mean_loss_magnitude
                    if win_count and mean_loss_magnitude is not None
                    else None
                ),
                "ratio",
                "mean winning native realized P&L divided by absolute mean losing native realized P&L in the named currency",
                (
                    None
                    if win_count and loss_count
                    else f"win-loss ratio requires winning and losing positions in {currency}"
                ),
                currency_sample_size,
            ),
        )
        for (
            metric_name,
            metric_value,
            unit,
            formula,
            specific_null_reason,
            sample_size,
        ) in position_distribution_metrics:
            result.append(
                _native_metric(
                    f"{metric_name}:{currency}",
                    metric_value if realized_pnl_is_complete else None,
                    unit=unit,
                    sample_size=sample_size,
                    formula=formula,
                    parameters={
                        "currency": currency,
                        "report_kind": "positions",
                        "value_field": "realized_pnl",
                        "currency_aggregation": "within_currency_only; no FX conversion",
                        **shared_parameters,
                    },
                    evidence_digest=artifact,
                    null_reason=(
                        realized_pnl_null_reason
                        if not realized_pnl_is_complete
                        else specific_null_reason
                    ),
                )
            )
        ordered_pnl = sorted(realized_pnl_values[currency])
        for quantile_name, numerator, denominator in (
            ("p05", 1, 20),
            ("p25", 1, 4),
            ("p50", 1, 2),
            ("p75", 3, 4),
            ("p95", 19, 20),
        ):
            rank = max(
                1,
                (currency_sample_size * numerator + denominator - 1) // denominator,
            )
            quantile = Decimal(numerator) / Decimal(denominator)
            result.append(
                _native_metric(
                    f"oos_realized_position_pnl_quantile_{quantile_name}:{currency}",
                    ordered_pnl[rank - 1] if realized_pnl_is_complete else None,
                    unit=f"currency:{currency}",
                    sample_size=currency_sample_size,
                    formula=(
                        f"nearest-rank {quantile_name} of native realized OOS-closed "
                        "position P&L in the named currency; rank is ceil(p*n), one-based, "
                        "with no interpolation"
                    ),
                    parameters={
                        "currency": currency,
                        "quantile": str(quantile),
                        "quantile_rule": "ceil(p*n), one-based rank, no interpolation",
                        "report_kind": "positions",
                        "value_field": "realized_pnl",
                        "currency_aggregation": "within_currency_only; no FX conversion",
                        **shared_parameters,
                    },
                    evidence_digest=artifact,
                    null_reason=realized_pnl_null_reason,
                )
            )
        result.append(
            _native_metric(
                f"oos_reported_realized_position_pnl:{currency}",
                realized_pnl_amounts[currency],
                unit=f"currency:{currency}",
                sample_size=realized_pnl_counts[currency],
                formula="sum of explicitly reported native realized position P&L in the named currency; no FX conversion",
                parameters={"currency": currency, "report_kind": "positions", **shared_parameters},
                evidence_digest=artifact,
            )
        )
    return tuple(result)


def _native_metric(
    name: str,
    value: Decimal | None,
    *,
    unit: str,
    sample_size: int,
    formula: str,
    parameters: Mapping[str, Any],
    evidence_digest: str,
    null_reason: str | None = None,
) -> MetricValue:
    if {"decimal_precision", "decimal_rounding"} & parameters.keys():
        raise ValueError("native metric parameters cannot override the Decimal context")
    calculation_parameters = {
        **parameters,
        "decimal_precision": DECIMAL_PRECISION,
        "decimal_rounding": "ROUND_HALF_EVEN",
    }
    return MetricValue(
        name=name,
        value=value,
        unit=unit,
        definition_version=METRIC_DEFINITION_VERSION,
        basis=MetricBasis.NET,
        sample_size=sample_size,
        calculation_basis=formula,
        null_reason=null_reason,
        calculation_definition=MetricCalculationDefinition(
            formula_id=f"strategy-lab.metrics/{name.partition(':')[0]}",
            contract_version=METRIC_CALCULATION_CONTRACT_VERSION,
            parameters=calculation_parameters,
        ),
        evidence_references=(MetricEvidenceReference("native_execution_reports", evidence_digest),),
    )


def _row_timestamp_ns(row: Mapping[str, Any], field_name: str) -> int | None:
    value = row.get(field_name)
    if field_name not in row or value is None or (isinstance(value, float) and isnan(value)):
        return None
    return _timestamp_ns(value, field_name=field_name)


def _median_decimal(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _timestamp_ns(value: Any, *, field_name: str) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, float) and value.is_integer() and 0 <= value <= 9_007_199_254_740_991:
        # Pandas may widen an integer timestamp column to float when nulls are
        # present. Only binary64 integers in the exact range are lossless.
        return int(value)
    if isinstance(value, str) and value.isascii() and value.isdigit():
        return int(value)
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be Unix nanoseconds or an offset-aware ISO timestamp")
    match = _ISO_TIMESTAMP.fullmatch(value)
    if match is None:
        raise ValueError(f"{field_name} must be Unix nanoseconds or an offset-aware ISO timestamp")
    zone = "+00:00" if match["zone"] == "Z" else match["zone"]
    try:
        parsed = datetime.fromisoformat(f"{match['whole']}{zone}")
    except ValueError as error:
        raise ValueError(f"{field_name} is not a valid ISO timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} timestamp must include a timezone")
    utc = parsed.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = utc - epoch
    whole_seconds_ns = (delta.days * 86_400 + delta.seconds) * 1_000_000_000
    fractional = match["fraction"] or ""
    fraction_ns = int((fractional + "000000000")[:9]) if fractional else 0
    return whole_seconds_ns + fraction_ns


def _reported_money(row: Mapping[str, Any], field_name: str) -> tuple[str, Decimal] | None:
    if field_name not in row or row[field_name] is None:
        return None
    value = row[field_name]
    currency: Any = row.get(f"{field_name}_currency")
    amount_text: str
    if isinstance(value, str):
        parts = value.split()
        if len(parts) == 2:
            amount_text, parsed_currency = parts
            if currency is not None and currency != parsed_currency:
                raise ValueError(f"{field_name} currency fields disagree")
            currency = parsed_currency
        elif len(parts) == 1:
            amount_text = parts[0]
        else:
            raise ValueError(f"{field_name} must be a decimal amount with an explicit currency")
    elif isinstance(value, int) and not isinstance(value, bool):
        amount_text = str(value)
    elif isinstance(value, Decimal):
        amount_text = format(value, "f")
    else:
        raise ValueError(f"{field_name} must be an exact decimal report value")
    if (
        not isinstance(currency, str)
        or len(currency) != 3
        or not currency.isascii()
        or not currency.isalpha()
    ):
        raise ValueError(f"{field_name} must include its native currency")
    try:
        amount = Decimal(amount_text)
    except ArithmeticError as error:
        raise ValueError(f"{field_name} must be an exact decimal report value") from error
    if not amount.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return currency.upper(), amount


__all__ = [
    "build_nautilus_oos_equity_metric_set",
    "build_nautilus_oos_metric_set",
]
