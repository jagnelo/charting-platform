from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.config import settings
from app.database import get_db
from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.user import User
from app.schemas.ohlcv import LocalSplitMaterializationOut, OHLCVBarOut
from app.services.adjustment_factors import (
    materialize_local_provider_adjusted_view,
    materialize_local_split_adjusted_view,
)
from app.services.bar_transforms import TRANSFORM_REGISTRY, apply_transform
from app.services.derived_timeframes import materialize_derived_timeframes
from app.services.market_data import fetch_ohlcv, fetch_ohlcv_latest, fetch_ohlcv_page_before
from app.services.ohlcv_coverage import _as_utc
from app.services.provider_runtime import ProviderNoDataError

router = APIRouter(prefix="/ohlcv", tags=["ohlcv"])

# Number of bars returned in one page. Chosen to be comfortable for rendering
# while giving enough history context for indicators (e.g. 200-period SMA).
PAGE_SIZE = 500
OhlcvView = Literal["canonical", "provider", "derived"]


def _filter_ohlcv_view(bars: list[OHLCVBar], view: OhlcvView) -> list[OHLCVBar]:
    """Select an explicit persisted lineage view without changing canonical defaults."""

    if view == "provider":
        return [bar for bar in bars if bar.is_derived is False]
    if view == "derived":
        return [bar for bar in bars if bar.is_derived is True]
    return bars


@router.post(
    "/{symbol:path}/{timeframe}/materialize-local-split",
    response_model=LocalSplitMaterializationOut,
)
async def materialize_local_split(
    symbol: str,
    timeframe: Timeframe,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Build a persisted local split-adjusted view from canonical raw bars."""

    start = _as_utc(start) if start is not None else None
    end = _as_utc(end) if end is not None else None
    if start is not None and end is not None and end < start:
        raise HTTPException(
            422,
            detail={"code": "invalid_ohlcv_range", "message": "end must be on or after start"},
        )
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found.")
    result = await materialize_local_split_adjusted_view(
        db,
        instrument_id=instrument.id,
        timeframe=timeframe,
        start=start,
        end=end,
    )
    await db.commit()
    return result


@router.post(
    "/{symbol:path}/{timeframe}/materialize-local-provider",
    response_model=LocalSplitMaterializationOut,
)
async def materialize_local_provider(
    symbol: str,
    timeframe: Timeframe,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Build a local adjusted view from explicit provider adjustment factors."""

    start = _as_utc(start) if start is not None else None
    end = _as_utc(end) if end is not None else None
    if start is not None and end is not None and end < start:
        raise HTTPException(
            422,
            detail={"code": "invalid_ohlcv_range", "message": "end must be on or after start"},
        )
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found.")
    result = await materialize_local_provider_adjusted_view(
        db,
        instrument_id=instrument.id,
        timeframe=timeframe,
        start=start,
        end=end,
    )
    await db.commit()
    return result


@router.get("/local/{symbol:path}/{timeframe}", response_model=list[OHLCVBarOut])
async def get_local_ohlcv(
    symbol: str,
    timeframe: Timeframe,
    limit: int = Query(PAGE_SIZE, ge=1, le=5000),
    adjusted: bool = Query(True),
    view: OhlcvView = Query(
        "canonical",
        description=(
            "Persisted lineage view: canonical merges provider and derived rows; "
            "provider or derived isolates one lineage."
        ),
    ),
    before: datetime | None = Query(
        None, description="Return the local page strictly before this timestamp."
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Canonical local read path; never triggers provider fan-out."""
    before = _as_utc(before) if before is not None else None
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    ).scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found.")
    predicates = [
        OHLCVBar.instrument_id == instrument.id,
        OHLCVBar.timeframe == timeframe,
        OHLCVBar.is_adjusted.is_(adjusted),
    ]
    if before is not None:
        predicates.append(OHLCVBar.ts < before)
    if view == "provider":
        predicates.append(OHLCVBar.is_derived.is_(False))
    elif view == "derived":
        predicates.append(OHLCVBar.is_derived.is_(True))
    if settings.E2E_SEED_MARKET_DATA:
        predicates.append(
            OHLCVBar.data_source_id
            == select(DataSource.id).where(DataSource.name == "e2e_reference").scalar_subquery()
        )
    bars = (
        (
            await db.execute(
                select(OHLCVBar).where(*predicates).order_by(OHLCVBar.ts.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    # Local reads never call providers, but a real canonical cache may contain
    # only adjusted D1 evidence when W1/MN were unavailable upstream.  Build
    # those coarse rows from the shared provider-neutral materializer so chart
    # and watchlist consumers see the same explicit lineage as normal reads.
    # Seeded browser fixtures intentionally remain source-scoped and must not
    # receive provider-neutral rows during deterministic visual runs.
    if (
        view in {"canonical", "derived"}
        and not settings.E2E_SEED_MARKET_DATA
        and timeframe in (Timeframe.W1, Timeframe.MN)
    ):
        d1_exists = await db.execute(
            select(OHLCVBar.id)
            .where(
                OHLCVBar.instrument_id == instrument.id,
                OHLCVBar.timeframe == Timeframe.D1,
                OHLCVBar.is_adjusted.is_(adjusted),
            )
            .limit(1)
        )
        if d1_exists.scalar_one_or_none() is not None:
            derived_exists = await db.execute(
                select(OHLCVBar.id)
                .where(
                    OHLCVBar.instrument_id == instrument.id,
                    OHLCVBar.timeframe == timeframe,
                    OHLCVBar.is_adjusted.is_(adjusted),
                    OHLCVBar.is_derived.is_(True),
                )
                .limit(1)
            )
            if derived_exists.scalar_one_or_none() is None:
                await materialize_derived_timeframes(db, instrument.id, adjusted=adjusted)
                await db.commit()
            # Re-read even when provider rows were already present: a partial
            # provider series must be merged with derived periods from D1.
            bars = (
                (
                    await db.execute(
                        select(OHLCVBar)
                        .where(*predicates)
                        .order_by(OHLCVBar.ts.desc())
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )
    return list(reversed(bars))


@router.get("/{symbol:path}/{timeframe}/transformed", response_model=list[OHLCVBarOut])
async def get_ohlcv_transformed(
    symbol: str,
    timeframe: Timeframe,
    bar_type: str = Query(
        ..., description=f"Bar transformation type. One of: {', '.join(TRANSFORM_REGISTRY)}"
    ),
    brick_size: float | None = Query(None, description="Renko: fixed brick size (auto if omitted)"),
    reversal_pct: float | None = Query(None, description="Kagi: reversal % (default 1.0)"),
    box_size: float | None = Query(None, description="Point & Figure: box size (auto if omitted)"),
    reversal: int | None = Query(None, description="Point & Figure: reversal boxes (default 3)"),
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    before: datetime | None = Query(
        None, description="Return a transformed page ending before this timestamp"
    ),
    limit: int | None = Query(None, ge=1),
    adjusted: bool = Query(True),
    view: OhlcvView = Query(
        "canonical",
        description=(
            "Persisted lineage view: canonical merges provider and derived rows; "
            "provider or derived isolates one lineage before transformation."
        ),
    ),
    local_only: bool = Query(
        False,
        description="Read only the canonical local cache; never hydrate from providers.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return OHLCV bars transformed into the requested bar type.
    Fetches the raw bars first (up to PAGE_SIZE * 3 to give transforms enough
    source material), then applies the transform.
    """
    if bar_type not in TRANSFORM_REGISTRY:
        raise HTTPException(
            400, f"Unknown bar_type '{bar_type}'. Valid: {list(TRANSFORM_REGISTRY)}"
        )

    start = _as_utc(start) if start is not None else None
    end = _as_utc(end) if end is not None else None
    before = _as_utc(before) if before is not None else None

    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found.")

    await db.refresh(instrument, ["listings"])

    # Fetch enough raw bars to feed the transform (transforms may collapse bars)
    fetch_limit = PAGE_SIZE * 3
    if before is not None:
        try:
            raw_bars = await fetch_ohlcv_page_before(
                db,
                instrument,
                timeframe,
                before,
                fetch_limit,
                adjusted,
                allow_provider_fetch=not local_only,
            )
        except ProviderNoDataError as exc:
            raise HTTPException(
                404, f"No OHLCV data available for instrument '{symbol}' on {timeframe.value}."
            ) from exc
    elif start is not None:
        try:
            raw_bars = await fetch_ohlcv(
                db,
                instrument,
                timeframe,
                start,
                end,
                adjusted,
                allow_provider_fetch=not local_only,
            )
        except ProviderNoDataError as exc:
            raise HTTPException(
                404, f"No OHLCV data available for instrument '{symbol}' on {timeframe.value}."
            ) from exc
    else:
        try:
            raw_bars = await fetch_ohlcv_latest(
                db,
                instrument,
                timeframe,
                fetch_limit,
                adjusted,
                allow_provider_fetch=not local_only,
            )
        except ProviderNoDataError as exc:
            raise HTTPException(
                404, f"No OHLCV data available for instrument '{symbol}' on {timeframe.value}."
            ) from exc

    # Build transform params from query string
    params: dict = {}
    if brick_size is not None:
        params["brick_size"] = brick_size
    if reversal_pct is not None:
        params["reversal_pct"] = reversal_pct
    if box_size is not None:
        params["box_size"] = box_size
    if reversal is not None:
        params["reversal"] = reversal

    raw_bars = _filter_ohlcv_view(raw_bars, view)
    transformed = apply_transform(bar_type, raw_bars, params or None)
    if limit:
        transformed = transformed[-limit:]
    return transformed


@router.get("/{symbol:path}/{timeframe}", response_model=list[OHLCVBarOut])
async def get_ohlcv(
    symbol: str,
    timeframe: Timeframe,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    before: datetime | None = Query(
        None, description="Return PAGE_SIZE bars strictly before this timestamp (for pagination)"
    ),
    limit: int | None = Query(None, ge=1, description="Cap the number of bars returned"),
    adjusted: bool = Query(True),
    view: OhlcvView = Query(
        "canonical",
        description=(
            "Persisted lineage view: canonical merges provider and derived rows; "
            "provider or derived isolates one lineage."
        ),
    ),
    local_only: bool = Query(
        False,
        description="Read only the canonical local cache; never hydrate from providers.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    start = _as_utc(start) if start is not None else None
    end = _as_utc(end) if end is not None else None
    before = _as_utc(before) if before is not None else None
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(
            404, f"Instrument '{symbol}' not found. Visit /instruments/{symbol} first."
        )

    await db.refresh(instrument, ["listings"])

    if before is not None:
        # Paginated: return the PAGE_SIZE bars immediately before `before`
        try:
            bars = await fetch_ohlcv_page_before(
                db,
                instrument,
                timeframe,
                before,
                PAGE_SIZE,
                adjusted,
                allow_provider_fetch=not local_only,
            )
        except ProviderNoDataError as exc:
            raise HTTPException(
                404, f"No OHLCV data available for instrument '{symbol}' on {timeframe.value}."
            ) from exc
        bars = _filter_ohlcv_view(bars, view)
        return bars[-limit:] if limit else bars

    if start is not None:
        # Explicit range query (used by alert engine, screener, sparklines, etc.)
        try:
            bars = await fetch_ohlcv(
                db,
                instrument,
                timeframe,
                start,
                end,
                adjusted,
                allow_provider_fetch=not local_only,
            )
        except ProviderNoDataError as exc:
            raise HTTPException(
                404, f"No OHLCV data available for instrument '{symbol}' on {timeframe.value}."
            ) from exc
        bars = _filter_ohlcv_view(bars, view)
        return bars[-limit:] if limit else bars

    # Default: initial load — return the latest N bars (capped at PAGE_SIZE)
    page = min(limit, PAGE_SIZE) if limit else PAGE_SIZE
    try:
        bars = await fetch_ohlcv_latest(
            db,
            instrument,
            timeframe,
            page,
            adjusted,
            allow_provider_fetch=not local_only,
        )
        return _filter_ohlcv_view(bars, view)
    except ProviderNoDataError as exc:
        raise HTTPException(
            404, f"No OHLCV data available for instrument '{symbol}' on {timeframe.value}."
        ) from exc
