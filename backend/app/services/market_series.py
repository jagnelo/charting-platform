"""Creation and lookup of explicitly scoped market-data series."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import AdjustmentBasis, MarketSeries


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
    return series


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
