from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.chart_drawing import ChartDrawing
from app.models.ohlcv import Timeframe
from app.models.user import User
from app.schemas.drawing import ChartDrawingCreate, ChartDrawingOut, ChartDrawingUpdate

router = APIRouter(prefix="/drawings", tags=["drawings"])


@router.get("", response_model=list[ChartDrawingOut])
async def get_drawings(
    instrument_id: int = Query(...),
    timeframe: Timeframe | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base = and_(
        ChartDrawing.instrument_id == instrument_id, ChartDrawing.user_id == current_user.id
    )
    if timeframe:
        stmt = select(ChartDrawing).where(
            and_(base, or_(ChartDrawing.timeframe == timeframe, ChartDrawing.pin_to_all.is_(True)))
        )
    else:
        stmt = select(ChartDrawing).where(base)
    result = await db.execute(stmt.order_by(ChartDrawing.position))
    return result.scalars().all()


@router.post("", response_model=ChartDrawingOut, status_code=201)
async def create_drawing(
    body: ChartDrawingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    drawing = ChartDrawing(**body.model_dump(), user_id=current_user.id)
    db.add(drawing)
    await db.commit()
    await db.refresh(drawing)
    return drawing


@router.patch("/{drawing_id}", response_model=ChartDrawingOut)
async def update_drawing(
    drawing_id: int,
    body: ChartDrawingUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    drawing = await db.get(ChartDrawing, drawing_id)
    if drawing is None or drawing.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Drawing not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(drawing, field, value)
    await db.commit()
    await db.refresh(drawing)
    return drawing


@router.delete("/{drawing_id}", status_code=204)
async def delete_drawing(
    drawing_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    drawing = await db.get(ChartDrawing, drawing_id)
    if drawing is None or drawing.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Drawing not found")
    await db.delete(drawing)
    await db.commit()


class DrawingReorderBody(BaseModel):
    ids: list[int]


@router.post("/reorder")
async def reorder_drawings(
    body: DrawingReorderBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist user-defined ordering of drawings (top of list = highest z-index)."""
    drawings = (
        (
            await db.execute(
                select(ChartDrawing).where(
                    ChartDrawing.user_id == current_user.id,
                    ChartDrawing.id.in_(body.ids),
                )
            )
        )
        .scalars()
        .all()
    )
    d_by_id = {d.id: d for d in drawings}
    for pos, d_id in enumerate(body.ids):
        if d_id in d_by_id:
            d_by_id[d_id].position = pos
    await db.commit()
    return {"ok": True}
