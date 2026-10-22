from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.favorite_instrument import FavoriteInstrument
from app.models.instrument import Instrument
from app.models.user import User
from app.schemas.favorites import FavoriteInstrumentOut

router = APIRouter(prefix="/favorites", tags=["favorites"])


def _favorite_out(favorite: FavoriteInstrument, instrument: Instrument) -> FavoriteInstrumentOut:
    return FavoriteInstrumentOut(
        id=favorite.id,
        instrument_id=favorite.instrument_id,
        position=favorite.position,
        added_at=favorite.added_at,
        symbol=instrument.symbol,
        name=instrument.name,
    )


@router.get("", response_model=list[FavoriteInstrumentOut])
async def list_favorites(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        await db.execute(
            select(FavoriteInstrument, Instrument)
            .join(Instrument, Instrument.id == FavoriteInstrument.instrument_id)
            .where(FavoriteInstrument.user_id == current_user.id)
            .order_by(
                FavoriteInstrument.position, FavoriteInstrument.added_at, FavoriteInstrument.id
            )
        )
    ).all()
    return [_favorite_out(favorite, instrument) for favorite, instrument in rows]


@router.put("/instruments/{instrument_id}", response_model=FavoriteInstrumentOut)
async def add_favorite(
    instrument_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    instrument = await db.get(Instrument, instrument_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found")
    user_id = current_user.id
    instrument_symbol = instrument.symbol
    instrument_name = instrument.name

    existing = (
        await db.execute(
            select(FavoriteInstrument).where(
                FavoriteInstrument.user_id == user_id,
                FavoriteInstrument.instrument_id == instrument_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _favorite_out(existing, instrument)

    max_position = (
        await db.execute(
            select(func.max(FavoriteInstrument.position)).where(
                FavoriteInstrument.user_id == user_id
            )
        )
    ).scalar_one()
    favorite = FavoriteInstrument(
        user_id=user_id,
        instrument_id=instrument_id,
        position=(max_position if max_position is not None else -1) + 1,
    )
    db.add(favorite)
    try:
        await db.flush()
    except IntegrityError:
        # A concurrent PUT for the same user/instrument is an idempotent add.
        await db.rollback()
        existing = (
            await db.execute(
                select(FavoriteInstrument).where(
                    FavoriteInstrument.user_id == user_id,
                    FavoriteInstrument.instrument_id == instrument_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise
        return FavoriteInstrumentOut(
            id=existing.id,
            instrument_id=existing.instrument_id,
            position=existing.position,
            added_at=existing.added_at,
            symbol=instrument_symbol,
            name=instrument_name,
        )
    await db.refresh(favorite)
    return _favorite_out(favorite, instrument)


@router.delete("/instruments/{instrument_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_favorite(
    instrument_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    favorite = (
        await db.execute(
            select(FavoriteInstrument).where(
                FavoriteInstrument.user_id == current_user.id,
                FavoriteInstrument.instrument_id == instrument_id,
            )
        )
    ).scalar_one_or_none()
    if favorite is not None:
        await db.delete(favorite)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
