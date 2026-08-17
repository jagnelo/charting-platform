from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
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
    WatchlistItemUpdate,
    WatchlistRead,
    WatchlistSourceMemberRead,
    WatchlistSourceRead,
    WatchlistSourceResolvedRead,
)
from app.services.watchlist_sources import list_watchlist_sources, resolve_watchlist_source

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


@router.get("/sources", response_model=list[WatchlistSourceRead])
async def get_watchlist_sources(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List every selectable universe through one watchlist-source contract."""

    return await list_watchlist_sources(db, current_user)


@router.get("/sources/{source_id:path}", response_model=WatchlistSourceResolvedRead)
async def get_watchlist_source_members(
    source_id: str,
    as_of: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Resolve a source for batch tools while preserving historical exclusions."""

    try:
        resolved = await resolve_watchlist_source(db, current_user.id, source_id, as_of=as_of)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return WatchlistSourceResolvedRead(
        source=resolved.descriptor,
        members=[
            WatchlistSourceMemberRead(
                instrument_id=member.instrument_id,
                position=member.position,
                weight=member.weight,
                relationship_type=member.relationship_type,
                source=member.source,
                effective_at=member.effective_at,
                known_at=member.known_at,
            )
            for member in resolved.members
        ],
        exclusions=list(resolved.exclusions),
    )


def _item_to_read(item: WatchlistItem, instr: Instrument | None) -> WatchlistItemRead:
    return WatchlistItemRead(
        id=item.id,
        instrument_id=item.instrument_id,
        position=item.position,
        added_at=item.added_at,
        flagged=item.flagged,
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


class ReorderItemsBody(BaseModel):
    ids: list[int]


class TransferItemBody(BaseModel):
    """Atomically copy or move one item between user-owned watchlists."""

    model_config = ConfigDict(extra="forbid")

    source_watchlist_id: int
    item_id: int
    mode: str


class TransferItemsBody(BaseModel):
    """Atomically copy or move multiple items between user-owned watchlists."""

    model_config = ConfigDict(extra="forbid")

    source_watchlist_id: int
    item_ids: list[int]
    mode: str


@router.post("/{watchlist_id}/items/reorder")
async def reorder_items(
    watchlist_id: int,
    body: ReorderItemsBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist manual ordering for a user's personal watchlist items."""
    wl = await _get_own_watchlist(db, current_user.id, watchlist_id)
    if wl.is_locked or wl.is_managed:
        raise HTTPException(403, "Cannot manually reorder a locked or managed watchlist")
    if len(body.ids) != len(set(body.ids)):
        raise HTTPException(400, "Item IDs must be unique")
    items = (
        (
            await db.execute(
                select(WatchlistItem).where(
                    WatchlistItem.watchlist_id == watchlist_id,
                    WatchlistItem.id.in_(body.ids),
                )
            )
        )
        .scalars()
        .all()
    )
    if {item.id for item in items} != set(body.ids):
        raise HTTPException(400, "Item IDs must contain every item in the watchlist")
    by_id = {item.id: item for item in items}
    for position, item_id in enumerate(body.ids):
        by_id[item_id].position = position
    await db.commit()
    return {"ok": True}


@router.post("/{watchlist_id}/items/transfer", response_model=WatchlistItemRead)
async def transfer_item(
    watchlist_id: int,
    body: TransferItemBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Copy or move a membership without exposing a partial two-request state."""
    if body.mode not in {"copy", "move"}:
        raise HTTPException(400, "mode must be 'copy' or 'move'")
    if body.source_watchlist_id == watchlist_id:
        raise HTTPException(400, "Source and destination watchlists must differ")

    list_ids = sorted({body.source_watchlist_id, watchlist_id})
    lists = (
        (
            await db.execute(
                select(Watchlist)
                .where(Watchlist.user_id == current_user.id, Watchlist.id.in_(list_ids))
                .order_by(Watchlist.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    by_id = {watchlist.id: watchlist for watchlist in lists}
    source = by_id.get(body.source_watchlist_id)
    target = by_id.get(watchlist_id)
    if source is None or target is None:
        raise HTTPException(404, "Watchlist not found")
    if target.is_locked or target.is_managed:
        raise HTTPException(403, "Cannot manually add items to a locked or managed watchlist")
    if body.mode == "move" and (source.is_locked or source.is_managed):
        raise HTTPException(403, "Cannot move items from a locked or managed watchlist")

    source_item = (
        await db.execute(
            select(WatchlistItem)
            .where(
                WatchlistItem.id == body.item_id,
                WatchlistItem.watchlist_id == source.id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if source_item is None:
        raise HTTPException(404, "Item not found")

    existing = (
        await db.execute(
            select(WatchlistItem)
            .where(
                WatchlistItem.watchlist_id == target.id,
                WatchlistItem.instrument_id == source_item.instrument_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "Instrument already in destination watchlist")

    max_position = (
        await db.execute(
            select(func.max(WatchlistItem.position)).where(WatchlistItem.watchlist_id == target.id)
        )
    ).scalar_one()
    transferred = WatchlistItem(
        watchlist_id=target.id,
        instrument_id=source_item.instrument_id,
        position=(max_position if max_position is not None else -1) + 1,
        flagged=source_item.flagged,
        notes=source_item.notes,
    )
    db.add(transferred)
    if body.mode == "move":
        await db.delete(source_item)
    await db.flush()
    instr = (
        await db.execute(select(Instrument).where(Instrument.id == transferred.instrument_id))
    ).scalar_one_or_none()
    return _item_to_read(transferred, instr)


@router.post("/{watchlist_id}/items/transfer-batch", response_model=list[WatchlistItemRead])
async def transfer_items(
    watchlist_id: int,
    body: TransferItemsBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Atomically copy or move a selected set of memberships."""
    if body.mode not in {"copy", "move"}:
        raise HTTPException(400, "mode must be 'copy' or 'move'")
    item_ids = list(dict.fromkeys(body.item_ids))
    if not item_ids:
        raise HTTPException(400, "item_ids must contain at least one item")
    if body.source_watchlist_id == watchlist_id:
        raise HTTPException(400, "Source and destination watchlists must differ")
    list_ids = sorted({body.source_watchlist_id, watchlist_id})
    lists = (
        (
            await db.execute(
                select(Watchlist)
                .where(Watchlist.user_id == current_user.id, Watchlist.id.in_(list_ids))
                .order_by(Watchlist.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    by_id = {watchlist.id: watchlist for watchlist in lists}
    source = by_id.get(body.source_watchlist_id)
    target = by_id.get(watchlist_id)
    if source is None or target is None:
        raise HTTPException(404, "Watchlist not found")
    if target.is_locked or target.is_managed:
        raise HTTPException(403, "Cannot manually add items to a locked or managed watchlist")
    if body.mode == "move" and (source.is_locked or source.is_managed):
        raise HTTPException(403, "Cannot move items from a locked or managed watchlist")
    source_items = (
        (
            await db.execute(
                select(WatchlistItem)
                .where(WatchlistItem.watchlist_id == source.id, WatchlistItem.id.in_(item_ids))
                .order_by(WatchlistItem.position, WatchlistItem.id)
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if len(source_items) != len(item_ids):
        raise HTTPException(404, "One or more source watchlist items were not found")
    instrument_ids = [item.instrument_id for item in source_items]
    existing = (
        (
            await db.execute(
                select(WatchlistItem.instrument_id)
                .where(
                    WatchlistItem.watchlist_id == target.id,
                    WatchlistItem.instrument_id.in_(instrument_ids),
                )
                .with_for_update()
            )
        )
        .scalars()
        .all()
    )
    if existing:
        raise HTTPException(409, "One or more instruments are already in the destination watchlist")
    max_position = (
        await db.execute(
            select(func.max(WatchlistItem.position)).where(WatchlistItem.watchlist_id == target.id)
        )
    ).scalar_one()
    next_position = (max_position if max_position is not None else -1) + 1
    transferred: list[WatchlistItem] = []
    for offset, source_item in enumerate(source_items):
        item = WatchlistItem(
            watchlist_id=target.id,
            instrument_id=source_item.instrument_id,
            position=next_position + offset,
            flagged=source_item.flagged,
            notes=source_item.notes,
        )
        db.add(item)
        transferred.append(item)
    if body.mode == "move":
        for source_item in source_items:
            await db.delete(source_item)
    await db.flush()
    instruments = (
        (await db.execute(select(Instrument).where(Instrument.id.in_(instrument_ids))))
        .scalars()
        .all()
    )
    by_instrument_id = {instrument.id: instrument for instrument in instruments}
    return [_item_to_read(item, by_instrument_id.get(item.instrument_id)) for item in transferred]


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


@router.patch("/{watchlist_id}/items/{item_id}", response_model=WatchlistItemRead)
async def update_item(
    watchlist_id: int,
    item_id: int,
    body: WatchlistItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user annotations without changing list membership.

    Flags and notes remain editable even on locked or managed lists; those controls do
    not alter the source-managed membership and are therefore safe personal annotations.
    """
    await _get_own_watchlist(db, current_user.id, watchlist_id)
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
    if body.flagged is not None:
        item.flagged = body.flagged
    if body.notes is not None:
        item.notes = body.notes
    await db.commit()
    instr = (
        await db.execute(select(Instrument).where(Instrument.id == item.instrument_id))
    ).scalar_one_or_none()
    return _item_to_read(item, instr)


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
                flagged=src_item.flagged,
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
