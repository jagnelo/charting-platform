from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
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
        .order_by(ScreenerDefinition.name)
    )
    return result.scalars().all()


@router.post("", response_model=ScreenerOut, status_code=201)
async def create_screener(
    body: ScreenerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger an immediate screener run.
    For large universes this runs as a background task via ARQ.
    Returns a pending result immediately; poll /screeners/{id}/results for completion.
    """
    screener = await db.get(ScreenerDefinition, screener_id)
    if screener is None or screener.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Screener not found")

    # Enqueue as ARQ task for large universes
    try:
        from arq.connections import RedisSettings, create_pool

        from app.config import settings as cfg

        redis = await create_pool(RedisSettings.from_dsn(cfg.REDIS_URL))
        await redis.enqueue_job("task_run_screener", screener_id)
        await redis.aclose()
        # Return a placeholder — client polls for results
        from datetime import datetime

        return ScreenerResultOut(
            id=-1,
            screener_id=screener_id,
            run_at=datetime.now(UTC),
            duration_ms=None,
            matched_ids=[],
            result_data={},
            error=None,
        )
    except Exception:
        # Fallback: run synchronously in background thread
        from app.services.screener_engine import run_screener

        result = await run_screener(db, screener)
        return result


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
