from datetime import UTC, datetime

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
from app.schemas.ohlcv import OHLCVBarOut
from app.services.bar_transforms import TRANSFORM_REGISTRY, apply_transform
from app.services.market_data import fetch_ohlcv, fetch_ohlcv_latest, fetch_ohlcv_page_before
from app.services.provider_runtime import ProviderNoDataError, ProviderRateLimitError

router = APIRouter(prefix="/ohlcv", tags=["ohlcv"])


def _provider_capacity_http_error(exc: ProviderRateLimitError) -> HTTPException:
    headers: dict[str, str] = {"X-Provider": exc.provider_name}
    if exc.retry_at is not None:
        seconds = max(0, int((exc.retry_at - datetime.now(UTC)).total_seconds()))
        headers["Retry-After"] = str(seconds)
    return HTTPException(
        status_code=503,
        detail={
            "code": "provider_capacity_unavailable",
            "provider": exc.provider_name,
            "message": str(exc),
            "retry_at": exc.retry_at,
            "scope": exc.scope,
        },
        headers=headers,
    )

# Number of bars returned in one page. Chosen to be comfortable for rendering
# while giving enough history context for indicators (e.g. 200-period SMA).
PAGE_SIZE = 500


@router.get("/local/{symbol:path}/{timeframe}", response_model=list[OHLCVBarOut])
async def get_local_ohlcv(
    symbol: str,
    timeframe: Timeframe,
    limit: int = Query(PAGE_SIZE, ge=1, le=5000),
    adjusted: bool = Query(True),
    before: datetime | None = Query(
        None, description="Return the local page strictly before this timestamp."
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Canonical local read path; never triggers provider fan-out."""
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
        if before.tzinfo is None:
            before = before.replace(tzinfo=UTC)
        predicates.append(OHLCVBar.ts < before)
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

    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found.")

    await db.refresh(instrument, ["listings"])

    # Fetch enough raw bars to feed the transform (transforms may collapse bars)
    fetch_limit = PAGE_SIZE * 3
    if before is not None:
        if before.tzinfo is None:
            before = before.replace(tzinfo=UTC)
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
        except ProviderRateLimitError as exc:
            raise _provider_capacity_http_error(exc) from exc
        except ProviderNoDataError as exc:
            raise HTTPException(
                404, f"No OHLCV data available for instrument '{symbol}' on {timeframe.value}."
            ) from exc
    elif start is not None:
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
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
        except ProviderRateLimitError as exc:
            raise _provider_capacity_http_error(exc) from exc
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
        except ProviderRateLimitError as exc:
            raise _provider_capacity_http_error(exc) from exc
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
    local_only: bool = Query(
        False,
        description="Read only the canonical local cache; never hydrate from providers.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    instrument = result.scalar_one_or_none()
    if instrument is None:
        raise HTTPException(
            404, f"Instrument '{symbol}' not found. Visit /instruments/{symbol} first."
        )

    await db.refresh(instrument, ["listings"])

    if before is not None:
        # Paginated: return the PAGE_SIZE bars immediately before `before`
        if before.tzinfo is None:
            before = before.replace(tzinfo=UTC)
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
        except ProviderRateLimitError as exc:
            raise _provider_capacity_http_error(exc) from exc
        except ProviderNoDataError as exc:
            raise HTTPException(
                404, f"No OHLCV data available for instrument '{symbol}' on {timeframe.value}."
            ) from exc
        return bars[-limit:] if limit else bars

    if start is not None:
        # Explicit range query (used by alert engine, screener, sparklines, etc.)
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        if end and end.tzinfo is None:
            end = end.replace(tzinfo=UTC)
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
        except ProviderRateLimitError as exc:
            raise _provider_capacity_http_error(exc) from exc
        except ProviderNoDataError as exc:
            raise HTTPException(
                404, f"No OHLCV data available for instrument '{symbol}' on {timeframe.value}."
            ) from exc
        return bars[-limit:] if limit else bars

    # Default: initial load — return the latest N bars (capped at PAGE_SIZE)
    page = min(limit, PAGE_SIZE) if limit else PAGE_SIZE
    try:
        return await fetch_ohlcv_latest(
            db,
            instrument,
            timeframe,
            page,
            adjusted,
            allow_provider_fetch=not local_only,
        )
    except ProviderRateLimitError as exc:
        raise _provider_capacity_http_error(exc) from exc
    except ProviderNoDataError as exc:
        raise HTTPException(
            404, f"No OHLCV data available for instrument '{symbol}' on {timeframe.value}."
        ) from exc
