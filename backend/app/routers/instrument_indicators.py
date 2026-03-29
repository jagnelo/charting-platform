from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument_indicator_config import InstrumentIndicatorConfig
from app.models.user import User

router = APIRouter(prefix="/instrument-indicators", tags=["instrument-indicators"])


class IndicatorConfigBody(BaseModel):
    indicators: list[dict]


@router.get("/{instrument_id}")
async def get_indicators(
    instrument_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(InstrumentIndicatorConfig).where(
            InstrumentIndicatorConfig.user_id == current_user.id,
            InstrumentIndicatorConfig.instrument_id == instrument_id,
        )
    )
    config = result.scalar_one_or_none()
    return {"indicators": config.indicators if config else []}


@router.put("/{instrument_id}")
async def set_indicators(
    instrument_id: int,
    body: IndicatorConfigBody,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(InstrumentIndicatorConfig).where(
            InstrumentIndicatorConfig.user_id == current_user.id,
            InstrumentIndicatorConfig.instrument_id == instrument_id,
        )
    )
    config = result.scalar_one_or_none()
    if config:
        config.indicators = body.indicators
    else:
        config = InstrumentIndicatorConfig(
            user_id=current_user.id,
            instrument_id=instrument_id,
            indicators=body.indicators,
        )
        db.add(config)
    await db.commit()
    return {"indicators": config.indicators}
