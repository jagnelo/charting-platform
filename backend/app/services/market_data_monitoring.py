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
    status = "complete" if expected and observed >= expected else "partial" if observed else "unavailable"
    query = select(MarketCoverageSnapshot).where(
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
    discrepancies = sum(value for key, value in statuses.items() if key in {"discrepancy", "mismatch"})
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
    }
