from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.user import User
from app.models.watchlist import Watchlist, WatchlistItem
from app.schemas.watchlist import (
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemRead,
    WatchlistRead,
)

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.get("", response_model=list[WatchlistRead])
async def get_watchlists(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Watchlist)
        .where(Watchlist.user_id == current_user.id)
        .order_by(Watchlist.created_at)
    )
    watchlists = result.scalars().all()
    out = []
    for wl in watchlists:
        items_result = await db.execute(
            select(WatchlistItem, Instrument)
            .join(Instrument, WatchlistItem.instrument_id == Instrument.id)
            .where(WatchlistItem.watchlist_id == wl.id)
            .order_by(WatchlistItem.position)
        )
        items = [
            WatchlistItemRead(
                id=item.id,
                instrument_id=item.instrument_id,
                position=item.position,
                added_at=item.added_at,
                symbol=instr.symbol,
                name=instr.name,
            )
            for item, instr in items_result.all()
        ]
        out.append(
            WatchlistRead(
                id=wl.id,
                name=wl.name,
                description=wl.description,
                is_default=wl.is_default,
                created_at=wl.created_at,
                items=items,
            )
        )
    return out


@router.post("", response_model=WatchlistRead)
async def create_watchlist(
    body: WatchlistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wl = Watchlist(**body.model_dump(), user_id=current_user.id)
    db.add(wl)
    await db.flush()
    await db.refresh(wl)
    return WatchlistRead(
        id=wl.id,
        name=wl.name,
        description=wl.description,
        is_default=wl.is_default,
        created_at=wl.created_at,
        items=[],
    )


@router.post("/{watchlist_id}/items", response_model=WatchlistItemRead)
async def add_item(
    watchlist_id: int,
    body: WatchlistItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wl_result = await db.execute(
        select(Watchlist).where(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id,
        )
    )
    wl = wl_result.scalar_one_or_none()
    if not wl:
        raise HTTPException(404, "Watchlist not found")

    # Prevent duplicate entries
    existing = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.instrument_id == body.instrument_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Instrument already in watchlist")

    item = WatchlistItem(watchlist_id=watchlist_id, **body.model_dump())
    db.add(item)
    await db.flush()
    instr_result = await db.execute(select(Instrument).where(Instrument.id == item.instrument_id))
    instr = instr_result.scalar_one_or_none()
    return WatchlistItemRead(
        id=item.id,
        instrument_id=item.instrument_id,
        position=item.position,
        added_at=item.added_at,
        symbol=instr.symbol if instr else None,
        name=instr.name if instr else None,
    )


@router.delete("/{watchlist_id}/items/{item_id}")
async def remove_item(
    watchlist_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Ownership check via watchlist
    wl_result = await db.execute(
        select(Watchlist).where(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id,
        )
    )
    if not wl_result.scalar_one_or_none():
        raise HTTPException(404, "Watchlist not found")

    result = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.id == item_id,
            WatchlistItem.watchlist_id == watchlist_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    await db.delete(item)
    return {"ok": True}


@router.delete("/{watchlist_id}")
async def delete_watchlist(
    watchlist_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Watchlist).where(
            Watchlist.id == watchlist_id,
            Watchlist.user_id == current_user.id,
        )
    )
    wl = result.scalar_one_or_none()
    if not wl:
        raise HTTPException(404, "Watchlist not found")
    await db.delete(wl)
    return {"ok": True}
