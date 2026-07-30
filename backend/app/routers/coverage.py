"""Canonical local coverage and freshness APIs for workstation tools."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar
from app.models.provider_observation import InstrumentDatasetState
from app.models.user import User
from app.schemas.coverage import (
    DatasetCoverageStateOut,
    InstrumentCoverageOut,
    LocalCoverageRangeOut,
)

router = APIRouter(prefix="/coverage", tags=["coverage"])


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
