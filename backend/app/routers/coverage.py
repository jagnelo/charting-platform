"""Canonical local coverage and freshness APIs for workstation tools."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_observation import InstrumentDatasetState
from app.models.user import User
from app.schemas.coverage import (
    DatasetCoverageStateOut,
    InstrumentCoverageOut,
    LocalCoverageRangeOut,
    OhlcvCoverageOut,
)
from app.services.ohlcv_coverage import assess_ohlcv_coverage

router = APIRouter(prefix="/coverage", tags=["coverage"])


@router.get("/instruments/{symbol}/ohlcv", response_model=OhlcvCoverageOut)
async def instrument_ohlcv_coverage(
    symbol: str,
    timeframe: Timeframe = Query(default=Timeframe.D1),
    start: datetime = Query(...),
    end: datetime = Query(...),
    mode: str = Query(default="historical", pattern="^(historical|latest)$"),
    adjusted: bool = Query(default=True),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Assess local OHLCV readiness without contacting any provider."""
    if end < start:
        raise HTTPException(
            422,
            detail={"code": "invalid_coverage_range", "message": "end must be on or after start"},
        )
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, detail={"code": "instrument_not_found", "symbol": symbol.upper()})

    bars = (
        await db.execute(
            select(OHLCVBar)
            .where(
                OHLCVBar.instrument_id == instrument.id,
                OHLCVBar.timeframe == timeframe,
                OHLCVBar.is_adjusted.is_(adjusted),
                OHLCVBar.ts >= start,
                OHLCVBar.ts <= end,
            )
            .order_by(OHLCVBar.ts)
        )
    ).scalars().all()
    assessment = assess_ohlcv_coverage(
        bars,
        timeframe,
        start,
        end,
        mode=mode,
        freshness_seconds=86_400 if timeframe == Timeframe.D1 else None,
        calendar="XNYS" if (instrument.currency or "").upper() == "USD" else None,
    )
    return OhlcvCoverageOut(
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        timeframe=timeframe.value,
        adjusted=adjusted,
        mode=mode,
        requested_start=start,
        requested_end=end,
        status=assessment.status.value,
        covered_start=assessment.covered_start,
        covered_end=assessment.covered_end,
        bar_count=assessment.bar_count,
        missing_slices=[{"start": gap_start, "end": gap_end} for gap_start, gap_end in assessment.missing_slices],
        explanation=assessment.explanation,
    )


@router.get("/instruments/{symbol}", response_model=InstrumentCoverageOut)
async def instrument_coverage(
    symbol: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return only persisted canonical coverage/freshness, never provider routing."""
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, detail={"code": "instrument_not_found", "symbol": symbol.upper()})

    aggregate_rows = (
        await db.execute(
            select(
                OHLCVBar.timeframe,
                func.min(OHLCVBar.ts).label("oldest"),
                func.max(OHLCVBar.ts).label("newest"),
                func.count().label("bar_count"),
            )
            .where(OHLCVBar.instrument_id == instrument.id, OHLCVBar.is_adjusted.is_(True))
            .group_by(OHLCVBar.timeframe)
        )
    ).all()
    states = (
        (
            await db.execute(
                select(InstrumentDatasetState)
                .where(InstrumentDatasetState.instrument_id == instrument.id)
                .order_by(InstrumentDatasetState.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return InstrumentCoverageOut(
        instrument_id=instrument.id,
        symbol=instrument.symbol,
        adjustment="split_adjusted",
        local_coverage={
            row.timeframe.value: LocalCoverageRangeOut(
                oldest=row.oldest, newest=row.newest, bar_count=int(row.bar_count)
            )
            for row in aggregate_rows
        },
        dataset_states=[
            DatasetCoverageStateOut(
                dataset_type=state.dataset_type,
                dataset_key=state.dataset_key,
                status=state.status.value,
                coverage_start=state.coverage_start,
                coverage_end=state.coverage_end,
                observed_at=state.observed_at,
                fetched_at=state.fetched_at,
                stale_after=state.stale_after,
                version=state.version,
            )
            for state in states
        ],
        refreshed_at=datetime.now(UTC),
    )
