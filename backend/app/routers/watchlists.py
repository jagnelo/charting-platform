from datetime import UTC, datetime

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
from app.models.watchlist_history import WatchlistHistoryRefreshRun
from app.schemas.watchlist import (
    SavedExplicitWatchlistSourceCreate,
    WatchlistCreate,
    WatchlistHistoryRefreshRunOut,
    WatchlistItemCreate,
    WatchlistItemRead,
    WatchlistItemUpdate,
    WatchlistRead,
    WatchlistSourceHistoryRefreshRequest,
    WatchlistSourceHistoryRefreshSummary,
    WatchlistSourceHistoryStatus,
    WatchlistSourceMemberRead,
    WatchlistSourceRead,
    WatchlistSourceResolvedRead,
)
from app.services.benchmark_family_history import canonical_history_job_id
from app.services.watchlist_history import (
    build_watchlist_source_history_status,
    plan_watchlist_source_history_refresh,
)
from app.services.watchlist_sources import (
    list_watchlist_sources,
    resolve_watchlist_source,
    save_explicit_watchlist_source,
)

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


def _refresh_run_output(run: WatchlistHistoryRefreshRun) -> WatchlistHistoryRefreshRunOut:
    return WatchlistHistoryRefreshRunOut.model_validate(run)


async def _refresh_run_progress(run: WatchlistHistoryRefreshRun, redis) -> dict:
    """Aggregate existing per-instrument Redis progress without provider calls."""

    from app.services.bulk_fetch import get_fetch_progress

    counts = {"pending": 0, "in_progress": 0, "complete": 0, "failed": 0, "canceled": 0}
    by_instrument: dict[str, dict] = {}
    for instrument_id in run.instrument_ids or []:
        progress = await get_fetch_progress(instrument_id, redis)
        if progress is None:
            counts["pending"] += 1
            continue
        status = str(progress.get("status") or "pending")
        results = progress.get("results") or {}
        if status == "canceled":
            counts["canceled"] += 1
        elif status == "in_progress":
            counts["in_progress"] += 1
        elif status == "complete":
            if any(isinstance(value, str) and value.startswith("error:") for value in results.values()):
                counts["failed"] += 1
            else:
                counts["complete"] += 1
        else:
            counts["pending"] += 1
        by_instrument[str(instrument_id)] = progress

    progress = {
        "instrument_count": len(run.instrument_ids or []),
        **counts,
        "instruments": by_instrument,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    return progress


@router.get("/sources", response_model=list[WatchlistSourceRead])
async def get_watchlist_sources(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List every selectable universe through one watchlist-source contract."""

    return await list_watchlist_sources(db, current_user)


@router.post("/sources/explicit", response_model=WatchlistSourceRead)
async def save_explicit_watchlist_source_route(
    body: SavedExplicitWatchlistSourceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist a user-owned locked canonical selection as a reusable source."""

    try:
        source = await save_explicit_watchlist_source(
            db,
            current_user.id,
            name=body.name,
            instrument_ids=body.instrument_ids,
            parent_source_id=body.parent_source_id,
            parent_membership_version=body.parent_membership_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return source


@router.get(
    "/sources/history-status/{source_id:path}",
    response_model=WatchlistSourceHistoryStatus,
)
async def get_watchlist_source_history_status(
    source_id: str,
    timeframes: list[str] | None = Query(default=None),
    as_of: datetime | None = Query(default=None),
    max_instruments: int = Query(default=5000, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return local coverage and existing worker progress for one source.

    This endpoint is intentionally a status read.  It never starts a provider request;
    callers use ``POST /sources/history-refresh`` when they explicitly want hydration.
    The path is source-polymorphic so locked index/ETF/sector/industry sources and
    editable personal/combo/explicit sources expose the same readiness contract.
    """

    from arq.connections import RedisSettings, create_pool

    from app.config import settings
    from app.services.bulk_fetch import get_fetch_progress

    try:
        plan = await plan_watchlist_source_history_refresh(
            db,
            current_user.id,
            source_ids=[source_id],
            as_of=as_of,
            max_instruments=max_instruments,
            timeframes=timeframes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    progress_by_instrument: dict[int, dict] = {}
    if plan["instrument_ids"]:
        try:
            redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
            try:
                for instrument_id in plan["instrument_ids"]:
                    progress = await get_fetch_progress(instrument_id, redis)
                    if progress is not None:
                        progress_by_instrument[instrument_id] = progress
            finally:
                await redis.aclose()
        except Exception:
            # Coverage remains useful when Redis is unavailable; the response simply
            # omits live worker progress rather than turning a local read into an error.
            progress_by_instrument = {}

    return await build_watchlist_source_history_status(
        db,
        current_user.id,
        source_id=source_id,
        as_of=as_of,
        max_instruments=max_instruments,
        timeframes=timeframes,
        progress_by_instrument=progress_by_instrument,
    )


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


@router.post(
    "/sources/history-refresh",
    response_model=WatchlistSourceHistoryRefreshSummary,
)
async def queue_watchlist_source_history_refresh(
    body: WatchlistSourceHistoryRefreshRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Queue explicit, bounded history hydration for any resolved source.

    This is a maintenance action, not an interactive data fallback.  It uses
    the same canonical source resolver as Market Map and breadth, then queues
    the existing provider-neutral per-instrument worker.  Personal sources are
    resolved in the current user's scope; system-managed sources remain locked
    and retain their own membership provenance.
    """

    from arq.connections import RedisSettings, create_pool

    from app.config import settings

    try:
        plan = await plan_watchlist_source_history_refresh(
            db,
            current_user.id,
            source_ids=body.source_ids,
            as_of=body.as_of,
            max_instruments=body.max_instruments,
            timeframes=body.timeframes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run = WatchlistHistoryRefreshRun(
        user_id=current_user.id,
        source_ids=plan["source_ids"],
        timeframes=plan["timeframes"],
        membership_versions={
            source["source_id"]: source.get("membership_version")
            for source in plan["sources"]
        },
        instrument_ids=plan["instrument_ids"],
        as_of=plan["as_of"],
        max_instruments=plan["max_instruments"],
        available_instrument_count=plan["available_instrument_count"],
        selected_instrument_count=plan["selected_instrument_count"],
        progress={"instrument_count": len(plan["instrument_ids"]), "pending": len(plan["instrument_ids"])},
    )
    db.add(run)
    await db.flush()

    queued = 0
    already_queued = 0
    try:
        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        try:
            for instrument_id in plan["instrument_ids"]:
                job_args = [
                    "task_bulk_fetch_instrument",
                    instrument_id,
                    plan["timeframes"],
                    run.id,
                ]
                if plan["as_of"] is not None:
                    job_args.append(plan["as_of"].isoformat())
                job = await redis.enqueue_job(
                    *job_args,
                    _job_id=canonical_history_job_id(
                        instrument_id,
                        plan["timeframes"],
                        plan["as_of"],
                    ),
                )
                if job is None:
                    already_queued += 1
                else:
                    queued += 1
            run.queued_count = queued
            run.already_queued_count = already_queued
            run.status = "completed" if not plan["instrument_ids"] else "queued"
            run.progress = {
                "instrument_count": len(plan["instrument_ids"]),
                "pending": len(plan["instrument_ids"]),
                "queued": queued,
                "already_queued": already_queued,
            }
        finally:
            await redis.aclose()
    except Exception as exc:  # noqa: BLE001 - queue outage is explicit to the caller.
        run.status = "failed"
        run.error = str(exc)
        run.queued_count = queued
        run.already_queued_count = already_queued
        run.finished_at = datetime.now(UTC)
        run.progress = {
            "instrument_count": len(plan["instrument_ids"]),
            "queued": queued,
            "already_queued": already_queued,
        }
        await db.commit()
        return WatchlistSourceHistoryRefreshSummary(
            **{
                key: plan[key]
                for key in (
                    "source_ids",
                    "timeframes",
                    "as_of",
                    "max_instruments",
                    "available_instrument_count",
                    "selected_instrument_count",
                    "limited",
                    "sources",
                )
            },
            queued=queued,
            already_queued=already_queued,
            queue_unavailable=True,
            run_id=run.id,
            message=f"History queue unavailable after {queued + already_queued} jobs: {exc}",
        )

    await db.commit()

    return WatchlistSourceHistoryRefreshSummary(
        **{
            key: plan[key]
            for key in (
                "source_ids",
                "timeframes",
                "as_of",
                "max_instruments",
                "available_instrument_count",
                "selected_instrument_count",
                "limited",
                "sources",
            )
        },
        queued=queued,
        already_queued=already_queued,
        run_id=run.id,
        message=("Selection was bounded by max_instruments." if plan["limited"] else None),
    )


async def _get_own_history_refresh_run(
    db: AsyncSession, user_id: int, run_id: int
) -> WatchlistHistoryRefreshRun:
    run = (
        await db.execute(
            select(WatchlistHistoryRefreshRun).where(
                WatchlistHistoryRefreshRun.id == run_id,
                WatchlistHistoryRefreshRun.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="History refresh run not found")
    return run


@router.get(
    "/history-refresh-runs/{run_id}",
    response_model=WatchlistHistoryRefreshRunOut,
)
async def get_watchlist_history_refresh_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return durable scope plus opportunistic worker progress for a refresh run."""

    run = await _get_own_history_refresh_run(db, current_user.id, run_id)
    if run.status not in {"completed", "canceled", "failed"}:
        from arq.connections import RedisSettings, create_pool

        from app.config import settings

        try:
            redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
            try:
                run.progress = await _refresh_run_progress(run, redis)
            finally:
                await redis.aclose()
        except Exception:
            # The persisted run remains useful when Redis is unavailable.
            pass

        progress = run.progress or {}
        if progress.get("in_progress", 0):
            run.status = "running"
            run.started_at = run.started_at or datetime.now(UTC)
        elif progress.get("failed", 0):
            run.status = "failed"
        elif progress.get("complete", 0) + progress.get("canceled", 0) >= len(
            run.instrument_ids or []
        ):
            run.status = "completed"
            run.finished_at = run.finished_at or datetime.now(UTC)
        await db.commit()

    return _refresh_run_output(run)


@router.post(
    "/history-refresh-runs/{run_id}/cancel",
    response_model=WatchlistHistoryRefreshRunOut,
)
async def cancel_watchlist_history_refresh_run(
    run_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a durable run and signal currently running worker jobs."""

    run = await _get_own_history_refresh_run(db, current_user.id, run_id)
    if run.status in {"completed", "canceled", "failed"}:
        raise HTTPException(status_code=409, detail=f"History refresh run is already {run.status}")

    run.cancel_requested = True
    run.status = "canceled"
    run.finished_at = datetime.now(UTC)
    run.progress = {**(run.progress or {}), "status": "canceled", "cancel_requested": True}

    try:
        from arq.connections import RedisSettings, create_pool

        from app.config import settings
        from app.services.bulk_fetch import refresh_cancel_key

        redis = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
        try:
            await redis.set(refresh_cancel_key(run.id), "1", ex=86_400)
        finally:
            await redis.aclose()
    except Exception:
        # Persisted cancellation is authoritative even if the worker queue is down.
        pass

    await db.commit()
    return _refresh_run_output(run)


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
