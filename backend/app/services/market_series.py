"""Creation and lookup of explicitly scoped market-data series."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.market_data_foundation import (
    AdjustmentBasis,
    MarketSeries,
    MarketSeriesDefault,
)
from app.models.ohlcv import OHLCVBar, Timeframe


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


def adjustment_scope_predicate(adjusted: bool):
    """Match the user-facing split-adjusted/raw basis without conflating TR.

    The pre-basis Massive adapter wrote the exact immutable version label
    ``massive-split-adjusted`` under the generic provider-adjusted enum. Retain
    that proven legacy series as split-compatible while keeping Alpaca ``all``
    and other total-return series distinct.
    """
    if not adjusted:
        return MarketSeries.adjustment_basis == AdjustmentBasis.RAW
    return or_(
        MarketSeries.adjustment_basis == AdjustmentBasis.SPLIT_ADJUSTED,
        and_(
            MarketSeries.adjustment_basis == AdjustmentBasis.PROVIDER_ADJUSTED,
            MarketSeries.adjustment_version == "massive-split-adjusted",
        ),
    )


def series_adjustment_is_compatible(series: MarketSeries, adjusted: bool) -> bool:
    if not adjusted:
        return series.adjustment_basis == AdjustmentBasis.RAW
    return series.adjustment_basis == AdjustmentBasis.SPLIT_ADJUSTED or (
        series.adjustment_basis == AdjustmentBasis.PROVIDER_ADJUSTED
        and series.adjustment_version == "massive-split-adjusted"
    )


def normalize_adjustment_basis(
    basis: AdjustmentBasis | str | None,
    version: str | None,
    adjusted: bool,
) -> AdjustmentBasis:
    if basis is not None and not isinstance(basis, AdjustmentBasis):
        basis = AdjustmentBasis(str(getattr(basis, "value", basis)))
    if not adjusted:
        return AdjustmentBasis.RAW
    if basis == AdjustmentBasis.PROVIDER_ADJUSTED and version == "massive-split-adjusted":
        return AdjustmentBasis.SPLIT_ADJUSTED
    return basis or AdjustmentBasis.SPLIT_ADJUSTED


def effective_series_adjustment_basis(
    series: MarketSeries | None, adjusted: bool
) -> AdjustmentBasis:
    if series is None:
        return AdjustmentBasis.SPLIT_ADJUSTED if adjusted else AdjustmentBasis.RAW
    return normalize_adjustment_basis(series.adjustment_basis, series.adjustment_version, adjusted)


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


async def select_default_series_for_complete_range(
    db: AsyncSession,
    *,
    instrument_id: int,
    timeframe: str,
    adjusted: bool,
    market_series_id: int,
    start: datetime,
    end: datetime,
) -> bool:
    """Select a canonical provider series after its requested range is complete.

    Until the caller has proven full coverage, the current default remains
    selected so recent reads are useful while a deeper alternate is filling.
    Provider bars remain isolated in their own series throughout.
    """
    series = await db.get(MarketSeries, market_series_id)
    if (
        series is None
        or series.instrument_id != instrument_id
        or series.timeframe != timeframe
        or not series.is_active
        or not series.is_canonical
        or not series_adjustment_is_compatible(series, adjusted)
    ):
        return False

    instrument = await db.get(Instrument, instrument_id)
    if instrument is None:
        return False
    coverage_bars = list(
        (
            await db.execute(
                select(OHLCVBar)
                .where(
                    OHLCVBar.instrument_id == instrument_id,
                    OHLCVBar.market_series_id == market_series_id,
                    OHLCVBar.timeframe == Timeframe(timeframe),
                    OHLCVBar.is_adjusted.is_(adjusted),
                    OHLCVBar.ts >= start,
                    OHLCVBar.ts <= end,
                )
                .order_by(OHLCVBar.ts)
            )
        )
        .scalars()
        .all()
    )
    from app.services.ohlcv_coverage import assess_ohlcv_coverage

    coverage = assess_ohlcv_coverage(
        coverage_bars,
        Timeframe(timeframe),
        start,
        end,
        calendar="XNYS" if (instrument.currency or "").upper() == "USD" else None,
    )
    if coverage.status.value != "ready":
        return False

    statement = select(MarketSeriesDefault).where(
        MarketSeriesDefault.instrument_id == instrument_id,
        MarketSeriesDefault.timeframe == timeframe,
        MarketSeriesDefault.is_adjusted == adjusted,
    )
    default = (await db.execute(statement)).scalar_one_or_none()
    current_series = (
        await db.get(MarketSeries, default.market_series_id)
        if default is not None and default.market_series_id is not None
        else None
    )
    if (
        default is not None
        and default.market_series_id != market_series_id
        and current_series is not None
        and current_series.is_active
        and series_adjustment_is_compatible(current_series, adjusted)
    ):
        current_bounds = (
            await db.execute(
                select(func.min(OHLCVBar.ts), func.max(OHLCVBar.ts)).where(
                    OHLCVBar.instrument_id == instrument_id,
                    OHLCVBar.market_series_id == default.market_series_id,
                    OHLCVBar.timeframe == Timeframe(timeframe),
                    OHLCVBar.is_adjusted.is_(adjusted),
                )
            )
        ).one()
        current_start, current_end = current_bounds
        if current_start is not None and current_start.tzinfo is None:
            current_start = current_start.replace(tzinfo=UTC)
        if current_end is not None and current_end.tzinfo is None:
            current_end = current_end.replace(tzinfo=UTC)
        normalized_start = start if start.tzinfo is not None else start.replace(tzinfo=UTC)
        normalized_end = end if end.tzinfo is not None else end.replace(tzinfo=UTC)
        if (
            current_start is not None
            and current_end is not None
            and (normalized_start >= current_start or normalized_end < current_end)
        ):
            # A narrower range must not displace a more useful existing default.
            return False
    if default is None:
        default = MarketSeriesDefault(
            instrument_id=instrument_id,
            timeframe=timeframe,
            is_adjusted=adjusted,
            market_series_id=market_series_id,
        )
        db.add(default)
    default.market_series_id = market_series_id
    default.selection_reason = "complete_admitted_range"
    default.selected_at = datetime.now(UTC)
    default.provenance = {
        "selection": "complete_admitted_range",
        "market_series_id": market_series_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    await db.flush()
    return True


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
