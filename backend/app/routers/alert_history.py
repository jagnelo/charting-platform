from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.alert_firing_event import AlertFiringEvent
from app.models.user import User
from app.schemas.alert_history import AlertFiringEventOut

router = APIRouter(prefix="/alerts", tags=["alert-history"])


def _enrich(event: AlertFiringEvent) -> AlertFiringEventOut:
    out = AlertFiringEventOut.model_validate(event)
    out.instrument_symbol = event.instrument.symbol if event.instrument else None
    return out


# ── Inbox / history list ─────────────────────────────────────────────────────


@router.get("/history", response_model=list[AlertFiringEventOut])
async def list_alert_history(
    instrument_id: int | None = Query(None),
    alert_type: str | None = Query(None),
    unviewed_only: bool = Query(False),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(AlertFiringEvent)
        .options(selectinload(AlertFiringEvent.instrument))
        .where(
            AlertFiringEvent.user_id == current_user.id,
            AlertFiringEvent.deleted_at.is_(None),
        )
    )
    if instrument_id:
        stmt = stmt.where(AlertFiringEvent.instrument_id == instrument_id)
    if alert_type:
        stmt = stmt.where(AlertFiringEvent.alert_type == alert_type)
    if unviewed_only:
        stmt = stmt.where(AlertFiringEvent.is_viewed.is_(False))
    stmt = stmt.order_by(AlertFiringEvent.fired_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    return [_enrich(r) for r in rows]


@router.get("/history/unviewed-count")
async def get_unviewed_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    from sqlalchemy import func

    count = (
        await db.execute(
            select(func.count()).where(
                AlertFiringEvent.user_id == current_user.id,
                AlertFiringEvent.is_viewed.is_(False),
                AlertFiringEvent.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    return {"count": count}


# ── Per-instrument chart overlay ─────────────────────────────────────────────


@router.get("/history/instrument/{instrument_id}", response_model=list[AlertFiringEventOut])
async def get_instrument_alert_history(
    instrument_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(AlertFiringEvent)
        .options(selectinload(AlertFiringEvent.instrument))
        .where(
            AlertFiringEvent.user_id == current_user.id,
            AlertFiringEvent.instrument_id == instrument_id,
            AlertFiringEvent.deleted_at.is_(None),
        )
        .order_by(AlertFiringEvent.fired_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [_enrich(r) for r in rows]


# ── Mark viewed ──────────────────────────────────────────────────────────────


@router.patch("/history/{event_id}/view", response_model=AlertFiringEventOut)
async def mark_viewed(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await db.get(
        AlertFiringEvent, event_id, options=[selectinload(AlertFiringEvent.instrument)]
    )
    if event is None or event.user_id != current_user.id or event.deleted_at is not None:
        raise HTTPException(404, "Event not found")
    event.is_viewed = True
    await db.commit()
    return _enrich(event)


@router.post("/history/view-all")
async def mark_all_viewed(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    from sqlalchemy import update

    await db.execute(
        update(AlertFiringEvent)
        .where(
            AlertFiringEvent.user_id == current_user.id,
            AlertFiringEvent.is_viewed.is_(False),
            AlertFiringEvent.deleted_at.is_(None),
        )
        .values(is_viewed=True)
    )
    await db.commit()
    return {"ok": True}


# ── Soft delete ──────────────────────────────────────────────────────────────


@router.delete("/history/{event_id}", status_code=204)
async def delete_firing_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    event = await db.get(AlertFiringEvent, event_id)
    if event is None or event.user_id != current_user.id:
        raise HTTPException(404, "Event not found")
    event.deleted_at = datetime.now(UTC)
    await db.commit()
