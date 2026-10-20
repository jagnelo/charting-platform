"""Creation and lookup of explicitly scoped market-data series."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import (
    AdjustmentBasis,
    MarketSeries,
    MarketSeriesDefault,
)


@dataclass(frozen=True, slots=True)
class SeriesScope:
    instrument_id: int
    timeframe: str
    exchange_id: int | None = None
    data_source_id: int | None = None
    feed_scope: str = "consolidated"
    session_code: str = "regular"
    adjustment_basis: AdjustmentBasis = AdjustmentBasis.RAW
    adjustment_version: str = "v1"


async def get_or_create_series(
    db: AsyncSession,
    scope: SeriesScope,
    *,
    canonical: bool = False,
    source_series_key: str | None = None,
    provenance: dict[str, Any] | None = None,
) -> MarketSeries:
    """Return a deterministic series row, safe for repeated reconciliation."""

    query = select(MarketSeries).where(
        MarketSeries.instrument_id == scope.instrument_id,
        MarketSeries.exchange_id == scope.exchange_id,
        MarketSeries.data_source_id == scope.data_source_id,
        MarketSeries.feed_scope == scope.feed_scope,
        MarketSeries.session_code == scope.session_code,
        MarketSeries.timeframe == scope.timeframe,
        MarketSeries.adjustment_basis == scope.adjustment_basis,
        MarketSeries.adjustment_version == scope.adjustment_version,
    )
    series = (await db.execute(query)).scalar_one_or_none()
    if series is None:
        series = MarketSeries(
            instrument_id=scope.instrument_id,
            exchange_id=scope.exchange_id,
            data_source_id=scope.data_source_id,
            feed_scope=scope.feed_scope,
            session_code=scope.session_code,
            timeframe=scope.timeframe,
            adjustment_basis=scope.adjustment_basis,
            adjustment_version=scope.adjustment_version,
            is_canonical=canonical,
            source_series_key=source_series_key,
            provenance=provenance or {},
        )
        db.add(series)
        await db.flush()
    else:
        if canonical:
            series.is_canonical = True
        if source_series_key:
            series.source_series_key = source_series_key
        if provenance:
            series.provenance = {**(series.provenance or {}), **provenance}
    if canonical:
        await _ensure_default_series(db, scope, series, provenance=provenance)
    return series


async def _ensure_default_series(
    db: AsyncSession,
    scope: SeriesScope,
    series: MarketSeries,
    *,
    provenance: dict[str, Any] | None = None,
) -> None:
    """Create the first canonical compatibility mapping without replacement.

    Multiple providers can produce valid series for one instrument.  The first
    provider admitted by the reviewed chain becomes the compatibility default;
    alternate series remain queryable through their explicit ID and never
    overwrite ordinary symbol/timeframe reads.  A stale or deleted target is
    repaired, and concurrent creators use the unique scope constraint as the
    arbitration point.
    """

    is_adjusted = scope.adjustment_basis != AdjustmentBasis.RAW
    query = select(MarketSeriesDefault).where(
        MarketSeriesDefault.instrument_id == scope.instrument_id,
        MarketSeriesDefault.timeframe == scope.timeframe,
        MarketSeriesDefault.is_adjusted == is_adjusted,
    )
    default = (await db.execute(query)).scalar_one_or_none()
    if default is None:
        candidate = MarketSeriesDefault(
            instrument_id=scope.instrument_id,
            timeframe=scope.timeframe,
            is_adjusted=is_adjusted,
            market_series_id=series.id,
            selection_reason="first_canonical",
            selected_at=datetime.now(UTC),
            provenance={
                "selection": "first_canonical",
                "market_series_id": series.id,
                **(provenance or {}),
            },
        )
        try:
            savepoint = db.begin_nested()
            if hasattr(savepoint, "__aenter__"):
                async with savepoint:
                    db.add(candidate)
                    await db.flush()
            else:
                with savepoint:
                    db.add(candidate)
                    await db.flush()
            default = candidate
        except IntegrityError:
            default = (await db.execute(query)).scalar_one_or_none()
            if default is None:
                raise
    if default.market_series_id == series.id:
        return
    target = await db.get(MarketSeries, default.market_series_id)
    prefer_regular = scope.session_code == "regular" and (
        target is not None and target.session_code != "regular"
    )
    if target is None or not target.is_active or prefer_regular:
        default.market_series_id = series.id
        default.selection_reason = (
            "prefer_regular_session" if prefer_regular else "repair_missing_or_inactive"
        )
        default.selected_at = datetime.now(UTC)
        default.provenance = {
            "selection": default.selection_reason,
            "market_series_id": series.id,
            **(provenance or {}),
        }


def series_key(scope: SeriesScope) -> str:
    """Stable human/debug key used for coalescing and routing telemetry."""

    exchange = scope.exchange_id if scope.exchange_id is not None else "global"
    source = scope.data_source_id if scope.data_source_id is not None else "canonical"
    return ":".join(
        (
            str(scope.instrument_id),
            str(exchange),
            str(source),
            scope.feed_scope,
            scope.session_code,
            scope.timeframe,
            scope.adjustment_basis.value,
            scope.adjustment_version,
        )
    )
