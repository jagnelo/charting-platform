from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.screener import ScreenerDefinition
from app.models.user import User
from app.models.watchlist import Watchlist, WatchlistItem
from app.schemas.watchlist import (
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemRead,
    WatchlistRead,
)

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


def _item_to_read(item: WatchlistItem, instr: Instrument | None) -> WatchlistItemRead:
    return WatchlistItemRead(
        id=item.id,
        instrument_id=item.instrument_id,
        position=item.position,
        added_at=item.added_at,
        left_screener_at=item.left_screener_at,
        symbol=instr.symbol if instr else None,
        name=instr.name if instr else None,
    )


def _wl_to_read(wl: Watchlist, items: list[WatchlistItemRead]) -> WatchlistRead:
    screener_name: str | None = None
    if wl.screener is not None:
        screener_name = wl.screener.name
    return WatchlistRead(
        id=wl.id,
        name=wl.name,
        description=wl.description,
        is_default=wl.is_default,
        is_managed=wl.is_managed,
        is_locked=wl.is_locked,
        screener_id=wl.screener_id,
        screener_name=screener_name,
        last_screener_run_at=wl.last_screener_run_at,
        position=wl.position,
        created_at=wl.created_at,
        items=items,
    )


async def _load_items(db: AsyncSession, watchlist_id: int) -> list[WatchlistItemRead]:
    rows = (
        await db.execute(
            select(WatchlistItem, Instrument)
            .join(Instrument, WatchlistItem.instrument_id == Instrument.id)
            .where(WatchlistItem.watchlist_id == watchlist_id)
            .order_by(WatchlistItem.position)
        )
    ).all()
    return [_item_to_read(item, instr) for item, instr in rows]


async def _get_own_watchlist(db: AsyncSession, user_id: int, watchlist_id: int) -> Watchlist:
    wl = (
        await db.execute(
            select(Watchlist)
            .where(Watchlist.id == watchlist_id, Watchlist.user_id == user_id)
            .options(selectinload(Watchlist.screener))
        )
    ).scalar_one_or_none()
    if not wl:
        raise HTTPException(404, "Watchlist not found")
    return wl


@router.get("", response_model=list[WatchlistRead])
async def get_watchlists(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    watchlists = (
        (
            await db.execute(
                select(Watchlist)
                .where(Watchlist.user_id == current_user.id)
                .options(selectinload(Watchlist.screener))
                .order_by(Watchlist.position, Watchlist.created_at)
            )
        )
        .scalars()
        .all()
    )

    return [_wl_to_read(wl, await _load_items(db, wl.id)) for wl in watchlists]


async def _assert_unique_name(
    db: AsyncSession, user_id: int, name: str, exclude_id: int | None = None
) -> None:
    stmt = (
        select(func.count())
        .select_from(Watchlist)
        .where(
            Watchlist.user_id == user_id,
            func.lower(Watchlist.name) == name.lower(),
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(Watchlist.id != exclude_id)
    count = (await db.execute(stmt)).scalar_one()
    if count > 0:
        raise HTTPException(409, f"A watchlist named '{name}' already exists")


async def _next_watchlist_position(db: AsyncSession, user_id: int) -> int:
    max_position = (
        await db.execute(select(func.max(Watchlist.position)).where(Watchlist.user_id == user_id))
    ).scalar_one()
    return (max_position or 0) + 1


@router.post("", response_model=WatchlistRead)
async def create_watchlist(
    body: WatchlistCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await _assert_unique_name(db, current_user.id, body.name)
    is_managed = False
    if body.screener_id is not None:
        screener = (
            await db.execute(
                select(ScreenerDefinition).where(
                    ScreenerDefinition.id == body.screener_id,
                    ScreenerDefinition.user_id == current_user.id,
                )
            )
        ).scalar_one_or_none()
        if not screener:
            raise HTTPException(404, "Screener not found")
        is_managed = True

    wl = Watchlist(
        **body.model_dump(),
        user_id=current_user.id,
        is_managed=is_managed,
        position=await _next_watchlist_position(db, current_user.id),
    )
    db.add(wl)
    await db.flush()
    await db.refresh(wl)
    return _wl_to_read(wl, [])


@router.post("/{watchlist_id}/items", response_model=WatchlistItemRead)
async def add_item(
    watchlist_id: int,
    body: WatchlistItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wl = await _get_own_watchlist(db, current_user.id, watchlist_id)

    if wl.is_locked or wl.is_managed:
        raise HTTPException(403, "Cannot manually add items to a locked or managed watchlist")

    existing = (
        await db.execute(
            select(WatchlistItem).where(
                WatchlistItem.watchlist_id == watchlist_id,
                WatchlistItem.instrument_id == body.instrument_id,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Instrument already in watchlist")

    item = WatchlistItem(watchlist_id=watchlist_id, **body.model_dump())
    db.add(item)
    await db.flush()
    instr = (
        await db.execute(select(Instrument).where(Instrument.id == item.instrument_id))
    ).scalar_one_or_none()
    return _item_to_read(item, instr)


@router.delete("/{watchlist_id}/items/{item_id}")
async def remove_item(
    watchlist_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wl = await _get_own_watchlist(db, current_user.id, watchlist_id)

    if wl.is_locked or wl.is_managed:
        raise HTTPException(403, "Cannot manually remove items from a locked or managed watchlist")

    item = (
        await db.execute(
            select(WatchlistItem).where(
                WatchlistItem.id == item_id,
                WatchlistItem.watchlist_id == watchlist_id,
            )
        )
    ).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    await db.delete(item)
    return {"ok": True}


class WatchlistRenameBody(BaseModel):
    name: str


@router.patch("/{watchlist_id}", response_model=WatchlistRead)
async def rename_watchlist(
    watchlist_id: int,
    body: WatchlistRenameBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Rename a watchlist (name must be unique for this user)."""
    if not body.name.strip():
        raise HTTPException(400, "Name cannot be empty")
    wl = await _get_own_watchlist(db, current_user.id, watchlist_id)
    await _assert_unique_name(db, current_user.id, body.name.strip(), exclude_id=watchlist_id)
    wl.name = body.name.strip()
    await db.commit()
    items = await _load_items(db, watchlist_id)
    return _wl_to_read(wl, items)


class WatchlistSeedBody(BaseModel):
    instrument_ids: list[int]


@router.post("/{watchlist_id}/seed", response_model=WatchlistRead)
async def seed_watchlist(
    watchlist_id: int,
    body: WatchlistSeedBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Seed a managed (or any) watchlist with initial instruments, bypassing the managed check."""
    wl = await _get_own_watchlist(db, current_user.id, watchlist_id)

    existing_ids = set(
        (
            await db.execute(
                select(WatchlistItem.instrument_id).where(
                    WatchlistItem.watchlist_id == watchlist_id
                )
            )
        )
        .scalars()
        .all()
    )

    for pos, instr_id in enumerate(body.instrument_ids):
        if instr_id not in existing_ids:
            db.add(WatchlistItem(watchlist_id=watchlist_id, instrument_id=instr_id, position=pos))

    await db.commit()
    items = await _load_items(db, watchlist_id)
    return _wl_to_read(wl, items)


@router.post("/{watchlist_id}/lock")
async def lock_watchlist(
    watchlist_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Lock a watchlist to prevent manual add/remove."""
    wl = await _get_own_watchlist(db, current_user.id, watchlist_id)
    wl.is_locked = True
    await db.commit()
    return {"ok": True}


@router.post("/{watchlist_id}/unlock")
async def unlock_watchlist(
    watchlist_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Unlock a manually-locked watchlist (not applicable to managed watchlists)."""
    wl = await _get_own_watchlist(db, current_user.id, watchlist_id)
    if wl.is_managed:
        raise HTTPException(403, "Cannot unlock a screener-managed watchlist")
    wl.is_locked = False
    await db.commit()
    return {"ok": True}


@router.post("/{watchlist_id}/copy", response_model=WatchlistRead)
async def copy_watchlist(
    watchlist_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create an independent (non-managed) copy of a watchlist.
    Grace-period departed items (left_screener_at set) are excluded from the copy.
    """
    src = await _get_own_watchlist(db, current_user.id, watchlist_id)

    new_wl = Watchlist(
        user_id=current_user.id,
        name=f"{src.name} (copy)",
        description=src.description,
        is_managed=False,
        is_locked=False,
        position=await _next_watchlist_position(db, current_user.id),
    )
    db.add(new_wl)
    await db.flush()

    src_items = (
        (
            await db.execute(
                select(WatchlistItem)
                .where(
                    WatchlistItem.watchlist_id == watchlist_id,
                    WatchlistItem.left_screener_at.is_(None),
                )
                .order_by(WatchlistItem.position)
            )
        )
        .scalars()
        .all()
    )

    for src_item in src_items:
        db.add(
            WatchlistItem(
                watchlist_id=new_wl.id,
                instrument_id=src_item.instrument_id,
                position=src_item.position,
            )
        )

    await db.commit()
    await db.refresh(new_wl)
    items = await _load_items(db, new_wl.id)
    return _wl_to_read(new_wl, items)


@router.delete("/{watchlist_id}")
async def delete_watchlist(
    watchlist_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wl = await _get_own_watchlist(db, current_user.id, watchlist_id)
    if wl.is_locked and not wl.is_managed:
        raise HTTPException(403, "Unlock the watchlist before deleting it")
    await db.delete(wl)
    return {"ok": True}


class ReorderBody(BaseModel):
    ids: list[int]  # watchlist IDs in desired order


@router.post("/reorder")
async def reorder_watchlists(
    body: ReorderBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist user-defined ordering of their watchlists."""
    watchlists = (
        (
            await db.execute(
                select(Watchlist).where(
                    Watchlist.user_id == current_user.id,
                    Watchlist.id.in_(body.ids),
                )
            )
        )
        .scalars()
        .all()
    )
    wl_by_id = {wl.id: wl for wl in watchlists}
    for pos, wl_id in enumerate(body.ids):
        if wl_id in wl_by_id:
            wl_by_id[wl_id].position = pos
    await db.commit()
    return {"ok": True}
