"""Backend-only coverage, shadow, and anomaly evidence helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import (
    MarketCoverageSnapshot,
    MarketDataAnomaly,
    ProviderShadowObservation,
)
from app.models.provider_runtime import ProviderCapacityEvent


def _utc(value: datetime | None) -> datetime:
    current = value or datetime.now(UTC)
    return current if current.tzinfo is not None else current.replace(tzinfo=UTC)


async def record_coverage_snapshot(
    db: AsyncSession,
    *,
    instrument_id: int,
    market_series_id: int | None,
    timeframe: str,
    expected_bars: int,
    observed_bars: int,
    expected_start: datetime | None = None,
    expected_end: datetime | None = None,
    missing_slices: list[dict[str, Any]] | None = None,
    evaluated_at: datetime | None = None,
    provenance: dict[str, Any] | None = None,
) -> MarketCoverageSnapshot:
    """Upsert an immutable-in-time coverage measurement without inventing bars."""

    evaluated = _utc(evaluated_at)
    expected = max(0, int(expected_bars))
    observed = max(0, int(observed_bars))
    ratio = min(Decimal("1"), Decimal(observed) / Decimal(expected)) if expected else Decimal("0")
    status = (
        "complete"
        if expected and observed >= expected
        else "partial"
        if observed
        else "unavailable"
    )
    query = select(MarketCoverageSnapshot).where(
        MarketCoverageSnapshot.instrument_id == instrument_id,
        MarketCoverageSnapshot.market_series_id == market_series_id,
        MarketCoverageSnapshot.timeframe == timeframe,
        MarketCoverageSnapshot.evaluated_at == evaluated,
    )
    row = (await db.execute(query)).scalar_one_or_none()
    values = {
        "instrument_id": instrument_id,
        "market_series_id": market_series_id,
        "timeframe": timeframe,
        "expected_start": expected_start,
        "expected_end": expected_end,
        "expected_bars": expected,
        "observed_bars": observed,
        "coverage_ratio": ratio,
        "status": status,
        "missing_slices": missing_slices or [],
        "evaluated_at": evaluated,
        "provenance": provenance or {},
    }
    if row is None:
        row = MarketCoverageSnapshot(**values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    await db.flush()
    return row


async def record_shadow_observation(
    db: AsyncSession,
    *,
    request_key: str,
    capability: str,
    comparison_status: str,
    discrepancy_metrics: dict[str, Any] | None = None,
    instrument_id: int | None = None,
    primary_data_source_id: int | None = None,
    alternate_data_source_id: int | None = None,
    routing_enabled: bool = False,
    observed_at: datetime | None = None,
    provenance: dict[str, Any] | None = None,
) -> ProviderShadowObservation:
    """Persist one comparison; defaults make shadow-only behavior explicit."""

    row = ProviderShadowObservation(
        request_key=request_key,
        capability=capability,
        comparison_status=comparison_status,
        discrepancy_metrics=discrepancy_metrics or {},
        instrument_id=instrument_id,
        primary_data_source_id=primary_data_source_id,
        alternate_data_source_id=alternate_data_source_id,
        routing_enabled=bool(routing_enabled),
        observed_at=_utc(observed_at),
        provenance=provenance or {},
    )
    db.add(row)
    await db.flush()
    return row


async def record_market_data_anomaly(
    db: AsyncSession,
    *,
    anomaly_type: str,
    source: str,
    details: dict[str, Any],
    instrument_id: int | None = None,
    market_series_id: int | None = None,
    severity: str = "info",
    detected_at: datetime | None = None,
) -> MarketDataAnomaly:
    """Coalesce identical open anomalies within a short review window."""

    detected = _utc(detected_at)
    query = select(MarketDataAnomaly).where(
        MarketDataAnomaly.anomaly_type == anomaly_type,
        MarketDataAnomaly.source == source,
        MarketDataAnomaly.instrument_id == instrument_id,
        MarketDataAnomaly.status == "open",
        MarketDataAnomaly.detected_at >= detected - timedelta(hours=24),
    )
    row = (await db.execute(query)).scalars().first()
    if row is not None:
        row.details = {**(row.details or {}), **details}
        row.severity = severity
        row.detected_at = detected
        return row
    row = MarketDataAnomaly(
        anomaly_type=anomaly_type,
        source=source,
        details=details,
        instrument_id=instrument_id,
        market_series_id=market_series_id,
        severity=severity,
        status="open",
        detected_at=detected,
    )
    db.add(row)
    await db.flush()
    return row


async def build_shadow_report(
    db: AsyncSession,
    *,
    since: datetime | None = None,
    capability: str | None = None,
) -> dict[str, Any]:
    """Return an AI-readable aggregate without implying activation."""

    query = select(ProviderShadowObservation).order_by(ProviderShadowObservation.observed_at)
    cutoff = _utc(since) if since else None
    if cutoff is not None:
        query = query.where(ProviderShadowObservation.observed_at >= cutoff)
    if capability:
        query = query.where(ProviderShadowObservation.capability == capability)
    rows = (await db.execute(query)).scalars().all()
    statuses: dict[str, int] = {}
    for row in rows:
        statuses[row.comparison_status] = statuses.get(row.comparison_status, 0) + 1
    discrepancies = sum(
        value for key, value in statuses.items() if key in {"discrepancy", "mismatch"}
    )

    coverage_query = select(MarketCoverageSnapshot).where(
        MarketCoverageSnapshot.timeframe == "D1"
    )
    if cutoff is not None:
        coverage_query = coverage_query.where(MarketCoverageSnapshot.evaluated_at >= cutoff)
    coverage_rows = (await db.execute(coverage_query)).scalars().all()
    eligible_coverage = [
        row
        for row in coverage_rows
        if isinstance(row.provenance, dict)
        and row.provenance.get("source") == "core_daily_coverage"
    ]
    expected_bars = sum(max(0, int(row.expected_bars or 0)) for row in eligible_coverage)
    observed_bars = sum(max(0, int(row.observed_bars or 0)) for row in eligible_coverage)
    coverage_ratio = observed_bars / expected_bars if expected_bars else None
    coverage_threshold = 0.99

    capacity_query = select(ProviderCapacityEvent)
    if cutoff is not None:
        capacity_query = capacity_query.where(ProviderCapacityEvent.observed_at >= cutoff)
    capacity_events = (await db.execute(capacity_query)).scalars().all()

    anomaly_query = select(MarketDataAnomaly).where(MarketDataAnomaly.status == "open")
    if cutoff is not None:
        anomaly_query = anomaly_query.where(MarketDataAnomaly.detected_at >= cutoff)
    open_anomalies = (await db.execute(anomaly_query)).scalars().all()
    anomaly_severities: dict[str, int] = {}
    for anomaly in open_anomalies:
        severity = str(anomaly.severity or "unknown")
        anomaly_severities[severity] = anomaly_severities.get(severity, 0) + 1

    return {
        "mode": "shadow_only",
        "routing_enabled": any(row.routing_enabled for row in rows),
        "since": cutoff,
        "capability": capability,
        "observations": len(rows),
        "status_counts": statuses,
        "discrepancies": discrepancies,
        "discrepancy_rate": (discrepancies / len(rows)) if rows else 0.0,
        "first_observed_at": rows[0].observed_at if rows else None,
        "last_observed_at": rows[-1].observed_at if rows else None,
        "core_daily_coverage": {
            "status": (
                "insufficient_evidence"
                if expected_bars == 0
                else "pass"
                if coverage_ratio is not None and coverage_ratio >= coverage_threshold
                else "fail"
            ),
            "timeframe": "D1",
            "eligible_snapshots": len(eligible_coverage),
            "expected_bars": expected_bars,
            "observed_bars": observed_bars,
            "coverage_ratio": coverage_ratio,
            "threshold": coverage_threshold,
            "threshold_met": bool(
                coverage_ratio is not None and coverage_ratio >= coverage_threshold
            ),
        },
        "quota_capacity_events": {
            "count": len(capacity_events),
            "latest_observed_at": (
                max(event.observed_at for event in capacity_events)
                if capacity_events
                else None
            ),
        },
        "open_anomalies": {
            "count": len(open_anomalies),
            "by_severity": anomaly_severities,
        },
    }
