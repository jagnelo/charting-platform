import json
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.ohlcv import Timeframe
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.models.user import User

router = APIRouter(prefix="/screeners", tags=["screeners"])


class ScreenerCreate(BaseModel):
    name: str
    description: str | None = None
    universe_type: str = "all"
    universe_watchlist_id: int | None = None
    universe_asset_class_id: int | None = None
    universe_instrument_ids: list[int] | None = None
    timeframe: Timeframe = Timeframe.D1
    conditions: dict
    schedule: str | None = None
    is_active: bool = True


class ScreenerOut(BaseModel):
    id: int
    name: str
    description: str | None
    universe_type: str
    timeframe: str
    conditions: dict
    schedule: str | None
    is_active: bool
    position: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScreenerResultOut(BaseModel):
    id: int
    screener_id: int
    run_at: datetime
    duration_ms: int | None
    matched_ids: list
    result_data: dict
    error: str | None

    class Config:
        from_attributes = True


@router.get("", response_model=list[ScreenerOut])
async def list_screeners(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ScreenerDefinition)
        .where(ScreenerDefinition.user_id == current_user.id)
        .order_by(ScreenerDefinition.position, ScreenerDefinition.name)
    )
    return result.scalars().all()


class ScreenerReorderBody(BaseModel):
    ids: list[int]


@router.post("/reorder")
async def reorder_screeners(
    body: ScreenerReorderBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist user-defined ordering of their screeners."""
    screeners = (
        (
            await db.execute(
                select(ScreenerDefinition).where(
                    ScreenerDefinition.user_id == current_user.id,
                    ScreenerDefinition.id.in_(body.ids),
                )
            )
        )
        .scalars()
        .all()
    )
    s_by_id = {s.id: s for s in screeners}
    for pos, s_id in enumerate(body.ids):
        if s_id in s_by_id:
            s_by_id[s_id].position = pos
    await db.commit()
    return {"ok": True}


@router.post("", response_model=ScreenerOut, status_code=201)
async def create_screener(
    body: ScreenerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = (
        await db.execute(
            select(func.count())
            .select_from(ScreenerDefinition)
            .where(
                ScreenerDefinition.user_id == current_user.id,
                func.lower(ScreenerDefinition.name) == body.name.lower(),
            )
        )
    ).scalar_one()
    if existing > 0:
        raise HTTPException(409, f"A screener named '{body.name}' already exists")
    screener = ScreenerDefinition(**body.model_dump(), user_id=current_user.id)
    db.add(screener)
    await db.commit()
    await db.refresh(screener)
    return screener


@router.get("/{screener_id}", response_model=ScreenerOut)
async def get_screener(
    screener_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    screener = await db.get(ScreenerDefinition, screener_id)
    if screener is None or screener.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Screener not found")
    return screener


@router.post("/{screener_id}/run", response_model=ScreenerResultOut)
async def run_screener_now(
    screener_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger an immediate synchronous screener run."""
    screener = await db.get(ScreenerDefinition, screener_id)
    if screener is None or screener.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Screener not found")

    from app.services.screener_engine import run_screener

    result = await run_screener(db, screener)
    return result


@router.patch("/{screener_id}", response_model=ScreenerOut)
async def update_screener(
    screener_id: int,
    body: ScreenerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    screener = await db.get(ScreenerDefinition, screener_id)
    if screener is None or screener.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Screener not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(screener, field, value)
    await db.commit()
    await db.refresh(screener)
    return screener


@router.get("/{screener_id}/results", response_model=list[ScreenerResultOut])
async def get_screener_results(
    screener_id: int,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    screener = await db.get(ScreenerDefinition, screener_id)
    if screener is None or screener.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Screener not found")

    results = await db.execute(
        select(ScreenerResult)
        .where(ScreenerResult.screener_id == screener_id)
        .order_by(ScreenerResult.run_at.desc())
        .limit(limit)
    )
    return results.scalars().all()


@router.delete("/{screener_id}", status_code=204)
async def delete_screener(
    screener_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    screener = await db.get(ScreenerDefinition, screener_id)
    if screener is None or screener.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Screener not found")
    await db.delete(screener)
    await db.commit()


@router.post("/{screener_id}/run/stream")
async def stream_screener_run(
    screener_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Streaming screener run — returns newline-delimited JSON (NDJSON).

    Each line is a JSON object with a "type" field:
      {"type": "progress", "evaluated": N, "total": N, "matches": N}
      {"type": "match",    "instrument_id": N, "computed": {...}}
      {"type": "done",     "evaluated": N, "total": N, "matches": N,
                           "duration_ms": N, "result_id": N}

    Pass 1 evaluates instruments already in the DB (fast).
    Pass 2 fetches missing OHLCV from yfinance then evaluates (slow, rate-limited).
    """
    screener = await db.get(ScreenerDefinition, screener_id)
    if screener is None or screener.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Screener not found")

    from app.services.screener_engine import stream_screener

    async def event_gen():
        async for event in stream_screener(db, screener):
            yield json.dumps(event) + "\n"

    return StreamingResponse(
        event_gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/admin/bootstrap-isins", status_code=202)
async def bootstrap_isins(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger a background job to fetch and store stable identifiers (ISIN /
    compositeFIGI) for all active instruments that don't have one yet.
    """
    from app.services.instrument_sync import bootstrap_isins as _bootstrap

    async def _run():
        await _bootstrap(db)

    background_tasks.add_task(_run)
    return {"status": "started", "message": "ISIN bootstrap running in background"}


@router.post("/admin/seed-universe", status_code=202)
async def seed_universe_endpoint(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger a background job that downloads the full US-listed ticker universe
    from NASDAQ Trader, creates Instrument rows for any symbols not already in
    the DB, and enriches every instrument with yfinance metadata (sector,
    industry, country, market-cap tier, etc.).

    Idempotent — safe to re-run.  Expect 15–45 min for ~8 000 tickers.
    """
    from app.services.instrument_sync import seed_universe as _seed

    async def _run():
        await _seed(db)

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Universe seed running in background"}


@router.post("/admin/sync-instruments", status_code=202)
async def sync_instruments_endpoint(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger a background metadata sync: refresh names/currencies and detect
    delistings for all active instruments.
    """
    from app.services.instrument_sync import sync_instruments as _sync

    async def _run():
        await _sync(db)

    background_tasks.add_task(_run)
    return {"status": "started", "message": "Instrument sync running in background"}
