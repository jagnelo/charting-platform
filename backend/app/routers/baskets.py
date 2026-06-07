from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.ohlcv import Timeframe
from app.models.user import User
from app.schemas.basket import (
    BasketCreateRequest,
    BasketOut,
    BasketSnapshotOut,
    BasketUpdateRequest,
)
from app.schemas.ohlcv import OHLCVBarOut
from app.services.baskets import (
    BasketReadOnlyError,
    BasketValidationError,
    basket_snapshot_to_out,
    basket_to_out,
    create_basket,
    delete_basket,
    get_basket,
    get_basket_synthetic_ohlcv,
    list_basket_snapshots,
    list_baskets,
    update_basket,
)

router = APIRouter(prefix="/baskets", tags=["baskets"])


@router.get("", response_model=list[BasketOut])
async def list_available_baskets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    baskets = await list_baskets(db, current_user.id)
    return [basket_to_out(basket) for basket in baskets]


@router.post("", response_model=BasketOut)
async def create_user_basket(
    body: BasketCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        basket = await create_basket(db, current_user.id, body)
        await db.commit()
    except BasketValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    return basket_to_out(basket)


@router.get("/{basket_id}", response_model=BasketOut)
async def read_basket(
    basket_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    basket = await get_basket(db, basket_id, current_user.id)
    if basket is None:
        raise HTTPException(404, "Basket not found")
    return basket_to_out(basket)


@router.get("/{basket_id}/ohlcv/{timeframe}", response_model=list[OHLCVBarOut])
async def read_basket_synthetic_ohlcv(
    basket_id: int,
    timeframe: Timeframe,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    limit: int | None = Query(None, ge=1),
    adjusted: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    basket = await get_basket(db, basket_id, current_user.id)
    if basket is None:
        raise HTTPException(404, "Basket not found")
    if start is not None and start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end is not None and end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return await get_basket_synthetic_ohlcv(
        db,
        basket_id,
        current_user.id,
        timeframe,
        start=start,
        end=end,
        limit=limit,
        adjusted=adjusted,
    )


@router.get("/{basket_id}/snapshots", response_model=list[BasketSnapshotOut])
async def read_basket_snapshots(
    basket_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        snapshots = await list_basket_snapshots(db, basket_id, current_user.id)
    except BasketValidationError as exc:
        raise HTTPException(404, str(exc)) from exc
    return [basket_snapshot_to_out(snapshot) for snapshot in snapshots]


@router.patch("/{basket_id}", response_model=BasketOut)
async def update_user_basket(
    basket_id: int,
    body: BasketUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        basket = await update_basket(db, basket_id, current_user.id, body)
        if basket is None:
            raise HTTPException(404, "Basket not found")
        await db.commit()
    except BasketValidationError as exc:
        raise HTTPException(400, str(exc)) from exc
    except BasketReadOnlyError as exc:
        raise HTTPException(403, str(exc)) from exc
    return basket_to_out(basket)


@router.delete("/{basket_id}", status_code=204)
async def delete_user_basket(
    basket_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        deleted = await delete_basket(db, basket_id, current_user.id)
        if not deleted:
            raise HTTPException(404, "Basket not found")
        await db.commit()
    except BasketReadOnlyError as exc:
        raise HTTPException(403, str(exc)) from exc
