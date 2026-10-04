"""Host-side metric-set construction from a verified native OOS equity trace."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
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
)
from app.strategy_lab_v2.metrics import (
    METRIC_DEFINITION_VERSION,
    calculate_event_aligned_equity_metrics,
)
from app.strategy_lab_v2.nautilus_equity_trace import NautilusAccountEquityTraceReference
from app.strategy_lab_v2.nautilus_native_reports import (
    NautilusNativeReportsReference,
    iter_nautilus_native_report_records,
)

_NATIVE_REPORT_TIME_FIELDS = {
    "fills": "ts_event",
    "orders": "ts_init",
    "positions": "ts_opened",
}
_ISO_TIMESTAMP = re.compile(
    r"(?P<whole>.+?)(?:\.(?P<fraction>[0-9]+))?(?P<zone>Z|[+-][0-9]{2}:[0-9]{2})$"
)


def build_nautilus_oos_equity_metric_set(
    reference: NautilusAccountEquityTraceReference,
    equity_marks: Iterable[Decimal],
    *,
    created_at: datetime,
) -> MetricSet:
    """Build reproducible official OOS equity metrics for one native attempt.

    ``equity_marks`` must be streamed from the byte-verified Parquet artifact
    identified by ``reference``. Its opening row is the first scoring-window
    account mark and the receipt count is enforced during metric calculation.
    Other native reports (fills, positions, and costs) can be added as further
    metric families without changing this equity-only evidence binding.
    """

    if not isinstance(reference, NautilusAccountEquityTraceReference):
        raise TypeError("reference must be a NautilusAccountEquityTraceReference")
    if reference.evaluation_window_fingerprint is None:
        raise ValueError("official Nautilus metrics require an OOS evaluation window")
    values = calculate_event_aligned_equity_metrics(
        equity_marks,
        base_currency=reference.base_currency,
        evidence_digest=reference.artifact.content_digest,
        expected_mark_count=reference.observation_count,
    )
    metric_set_identity = content_digest(
        {
            "attempt_id": reference.attempt_id,
            "definition_version": METRIC_DEFINITION_VERSION,
            "equity_trace_digest": reference.artifact.content_digest,
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
    created_at: datetime,
) -> MetricSet:
    """Build one OOS metric set from byte-verified native engine outputs.

    Only rows whose native event timestamp falls in the reference's half-open
    scoring interval contribute to the native-report metrics. Commission and
    realized P&L remain in the currencies printed by Nautilus; no FX conversion,
    cadence, session calendar, or missing report field is inferred here.
    """

    _require_matching_oos_references(equity_reference, native_reports_reference)
    if (
        not isinstance(created_at, datetime)
        or created_at.tzinfo is None
        or created_at.utcoffset() is None
    ):
        raise ValueError("created_at must be timezone-aware")

    equity_values = calculate_event_aligned_equity_metrics(
        equity_marks,
        base_currency=equity_reference.base_currency,
        evidence_digest=equity_reference.artifact.content_digest,
        expected_mark_count=equity_reference.observation_count,
    )
    native_values = _native_oos_report_metrics(native_reports_reference, native_reports_path)
    identity = content_digest(
        {
            "attempt_id": equity_reference.attempt_id,
            "definition_version": METRIC_DEFINITION_VERSION,
            "equity_trace_digest": equity_reference.artifact.content_digest,
            "native_reports_digest": native_reports_reference.artifact.content_digest,
            "trial_id": equity_reference.trial_id,
            "window_fingerprint": equity_reference.evaluation_window_fingerprint,
        }
    )
    return MetricSet(
        metric_set_id=f"metrics-{identity.removeprefix('sha256:')}",
        trial_id=equity_reference.trial_id,
        attempt_id=equity_reference.attempt_id,
        definition_version=METRIC_DEFINITION_VERSION,
        values=(*equity_values, *native_values),
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
    realized_pnl_amounts: dict[str, Decimal] = defaultdict(Decimal)
    realized_pnl_counts: dict[str, int] = defaultdict(int)
    realized_pnl_unreported = 0

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
            closed_value = row["ts_closed"]
            if closed_value is None:
                continue
            closed = _timestamp_ns(closed_value, field_name="positions.ts_closed")
            if start_ns <= closed < end_ns:
                closed_positions += 1
                realized = _reported_money(row, "realized_pnl")
                if realized is None:
                    realized_pnl_unreported += 1
                else:
                    currency, amount = realized
                    realized_pnl_amounts[currency] += amount
                    realized_pnl_counts[currency] += 1

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
                (
                    None
                    if not closed_position_time_coverage
                    else Decimal(sum(realized_pnl_counts.values()))
                ),
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
            parameters=parameters,
        ),
        evidence_references=(MetricEvidenceReference("native_execution_reports", evidence_digest),),
    )


def _row_timestamp_ns(row: Mapping[str, Any], field_name: str) -> int | None:
    if field_name not in row or row[field_name] is None:
        return None
    return _timestamp_ns(row[field_name], field_name=field_name)


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
