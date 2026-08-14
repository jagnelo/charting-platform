import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_current_user_detached
from app.database import (
    close_session_safely,
    get_db,
    get_stream_session_factory,
    rollback_session_safely,
)
from app.models.ohlcv import Timeframe
from app.models.research import CodeAsset, CodeVersion
from app.models.screener import ScreenerDefinition, ScreenerResult
from app.models.user import User
from app.models.workstation import WorkspaceLibraryItem

router = APIRouter(prefix="/screeners", tags=["screeners"])


class ScreenerCreate(BaseModel):
    name: str
    description: str | None = None
    universe_type: str = "all"
    universe_watchlist_id: int | None = None
    universe_asset_class_id: int | None = None
    universe_basket_id: int | None = None
    universe_instrument_ids: list[int] | None = None
    timeframe: Timeframe = Timeframe.D1
    conditions: dict
    schedule: str | None = None
    is_active: bool = True


class ScreenerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    universe_type: str
    universe_watchlist_id: int | None = None
    universe_asset_class_id: int | None = None
    universe_basket_id: int | None = None
    universe_instrument_ids: list[int] | None = None
    timeframe: str
    conditions: dict
    schedule: str | None
    is_active: bool
    position: int = 0
    created_at: datetime
    updated_at: datetime


class ScreenerResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    screener_id: int
    run_at: datetime
    duration_ms: int | None
    matched_ids: list
    result_data: dict
    error: str | None


class ScreenerPlotPoint(BaseModel):
    timestamp: datetime
    value: float | None = None
    matched_count: int = 0
    evaluated_count: int = 0
    coverage: float = 0.0


class ScreenerPlotOut(BaseModel):
    screener_id: int
    screener_name: str
    metric: str
    points: list[ScreenerPlotPoint]
    history_count: int
    warning: str | None = None


class ScreenerFromCondition(BaseModel):
    name: str
    description: str | None = None
    universe_type: str = "all"
    universe_watchlist_id: int | None = None
    universe_asset_class_id: int | None = None
    universe_basket_id: int | None = None
    universe_instrument_ids: list[int] | None = None
    timeframe: Timeframe = Timeframe.D1
    schedule: str | None = None
    is_active: bool = True


class ScreenerFromPythonCondition(ScreenerFromCondition):
    """A persisted Boolean code version is the authoritative scan condition."""


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


@router.post("/from-condition/{stable_key}", response_model=ScreenerOut, status_code=201)
async def create_screener_from_condition(
    stable_key: str,
    body: ScreenerFromCondition,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Copy a versioned condition into an EasyScan definition with explicit provenance."""
    condition = (
        await db.execute(
            select(WorkspaceLibraryItem).where(
                WorkspaceLibraryItem.user_id == current_user.id,
                WorkspaceLibraryItem.kind == "condition",
                WorkspaceLibraryItem.stable_key == stable_key,
            )
        )
    ).scalar_one_or_none()
    if condition is None:
        raise HTTPException(status_code=404, detail="Condition not found")
    condition_tree = condition.payload.get("condition")
    if not isinstance(condition_tree, dict) or not condition_tree:
        raise HTTPException(
            status_code=422, detail="Condition asset has no executable condition AST"
        )
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
    python_version_id = condition.payload.get("python_code_version_id")
    if isinstance(python_version_id, int):
        version = (
            await db.execute(
                select(CodeVersion)
                .join(CodeAsset)
                .where(
                    CodeVersion.id == python_version_id,
                    CodeAsset.user_id == current_user.id,
                    CodeAsset.kind == "condition",
                    CodeVersion.output_contract == "boolean",
                )
            )
        ).scalar_one_or_none()
        if version is None:
            raise HTTPException(status_code=422, detail="Condition's Python version is unavailable")
        conditions = {"type": "python_condition", "code_version_id": version.id}
    else:
        # Compatibility path for condition records created before the unified
        # Python visual editor.  These records remain executable but are never
        # produced by a new visual save.
        conditions = condition_tree
    screener = ScreenerDefinition(
        **body.model_dump(exclude={"description"}),
        conditions=conditions,
        user_id=current_user.id,
        description=body.description or condition.payload.get("description"),
    )
    db.add(screener)
    await db.commit()
    await db.refresh(screener)
    return screener


@router.post(
    "/from-python-condition/{code_version_id}", response_model=ScreenerOut, status_code=201
)
async def create_screener_from_python_condition(
    code_version_id: int,
    body: ScreenerFromPythonCondition,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    version = (
        await db.execute(
            select(CodeVersion)
            .join(CodeAsset)
            .where(
                CodeVersion.id == code_version_id,
                CodeAsset.user_id == current_user.id,
                CodeAsset.kind.in_(["condition", "study"]),
                CodeVersion.output_contract == "boolean",
            )
        )
    ).scalar_one_or_none()
    if version is None:
        raise HTTPException(404, "Boolean Python condition version not found")
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
    screener = ScreenerDefinition(
        **body.model_dump(exclude={"description"}),
        conditions={"type": "python_condition", "code_version_id": version.id},
        user_id=current_user.id,
        description=body.description,
    )
    db.add(screener)
    await db.commit()
    await db.refresh(screener)
    return screener


async def _queue_python_screener_run(
    db: AsyncSession, screener: ScreenerDefinition
) -> ScreenerResult:
    """Materialize a screener universe and queue it in the isolated Boolean runner."""
    from app.services.screener_engine import queue_python_screener_run

    try:
        return await queue_python_screener_run(db, screener)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


async def _collect_python_screener_result(db: AsyncSession, result: ScreenerResult) -> None:
    from app.services.screener_engine import collect_python_screener_result

    await collect_python_screener_result(db, result)


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

    if screener.conditions.get("type") == "python_condition":
        return await _queue_python_screener_run(db, screener)

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
    limit: int = Query(default=10, ge=1, le=100),
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
    values = results.scalars().all()
    for result in values:
        await _collect_python_screener_result(db, result)
    return values


@router.get("/{screener_id}/plot", response_model=ScreenerPlotOut)
async def get_screener_plot(
    screener_id: int,
    metric: str = Query(default="percentage", pattern="^(count|percentage)$"),
    limit: int = Query(default=500, ge=1, le=2_000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return a reusable numeric series from retained EasyScan history.

    A plot is deliberately empty until the scan has recorded real result
    snapshots.  This endpoint never re-runs a scan or fabricates historical
    observations from the current result.
    """
    screener = await db.get(ScreenerDefinition, screener_id)
    if screener is None or screener.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Screener not found")

    recent_results = (
        (
            await db.execute(
                select(ScreenerResult)
                .where(ScreenerResult.screener_id == screener_id)
                .order_by(ScreenerResult.run_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    # Fetch newest history within the bound, then restore chronological order
    # for uPlot and consumers that calculate transitions between points.
    results = list(reversed(recent_results))
    points: list[ScreenerPlotPoint] = []
    for result in results:
        # Python-backed screeners may only have a queued result at first.  Reconcile
        # it through the same durable path used by the results list before deciding
        # whether a point is valid.
        await _collect_python_screener_result(db, result)
        result_data = result.result_data if isinstance(result.result_data, dict) else {}
        coverage = result_data.get("_coverage")
        if not isinstance(coverage, dict):
            coverage = {}
        try:
            evaluated = max(0, int(coverage.get("evaluated_count", 0)))
        except (TypeError, ValueError):
            evaluated = 0
        try:
            universe = max(evaluated, int(coverage.get("universe_count", evaluated)))
        except (TypeError, ValueError):
            universe = evaluated
        matched = len(result.matched_ids) if isinstance(result.matched_ids, list) else 0
        valid = result.error is None and evaluated > 0
        points.append(
            ScreenerPlotPoint(
                timestamp=result.run_at,
                value=(
                    float(matched)
                    if metric == "count" and valid
                    else (float(matched) / evaluated * 100.0 if valid else None)
                ),
                matched_count=matched,
                evaluated_count=evaluated,
                coverage=(evaluated / universe if universe else 0.0),
            )
        )

    warning = None
    if not points:
        warning = "No retained scan history is available; run the EasyScan before adding a plot."
    elif not any(point.value is not None for point in points):
        warning = "Retained scan history has no complete evaluated observations."
    return ScreenerPlotOut(
        screener_id=screener.id,
        screener_name=screener.name,
        metric=metric,
        points=points,
        history_count=len(points),
        warning=warning,
    )


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
    current_user: User = Depends(get_current_user_detached),
    session_factory=Depends(get_stream_session_factory),
):
    """
    Streaming screener run — returns newline-delimited JSON (NDJSON).

    Each line is a JSON object with a "type" field:
      {"type": "progress", "evaluated": N, "total": N, "matches": N}
      {"type": "match",    "instrument_id": N, "computed": {...}}
      {"type": "done",     "evaluated": N, "total": N, "matches": N,
                           "duration_ms": N, "result_id": N}

    The stream evaluates canonical local history only.  Instruments without
    sufficient local bars are returned as explicit coverage errors; a UI scan
    never fans out to providers.
    """
    lookup_db = session_factory()
    try:
        screener = await lookup_db.get(ScreenerDefinition, screener_id)
    finally:
        await close_session_safely(lookup_db)
    if screener is None or screener.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Screener not found")

    from app.services.screener_engine import stream_screener

    async def event_gen():
        db = session_factory()
        try:
            stream_screener_definition = await db.get(ScreenerDefinition, screener_id)
            if stream_screener_definition is None:
                return
            async for event in stream_screener(db, stream_screener_definition):
                yield json.dumps(event) + "\n"
        except BaseException:
            # Roll back an interrupted scan before returning the dedicated
            # stream connection to the pool.
            await rollback_session_safely(db)
            raise
        finally:
            # Return the dedicated connection as soon as the body ends (or is
            # cancelled); the helper also handles an already-cancelled task.
            await close_session_safely(db)

    return StreamingResponse(
        event_gen(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
