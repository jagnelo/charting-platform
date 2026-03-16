from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.indicator_preset import IndicatorPreset
from app.models.user import User
from app.schemas.preset import IndicatorPresetCreate, IndicatorPresetOut, IndicatorPresetUpdate

router = APIRouter(prefix="/presets", tags=["presets"])


@router.get("", response_model=list[IndicatorPresetOut])
async def list_presets(
    db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)
):
    result = await db.execute(
        select(IndicatorPreset)
        .where(IndicatorPreset.user_id == current_user.id)
        .order_by(IndicatorPreset.name)
    )
    return result.scalars().all()


@router.post("", response_model=IndicatorPresetOut, status_code=201)
async def create_preset(
    body: IndicatorPresetCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.is_default:
        result = await db.execute(
            select(IndicatorPreset).where(
                IndicatorPreset.user_id == current_user.id, IndicatorPreset.is_default.is_(True)
            )
        )
        for p in result.scalars().all():
            p.is_default = False
    preset = IndicatorPreset(**body.model_dump(), user_id=current_user.id)
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset


@router.patch("/{preset_id}", response_model=IndicatorPresetOut)
async def update_preset(
    preset_id: int,
    body: IndicatorPresetUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    preset = await db.get(IndicatorPreset, preset_id)
    if preset is None or preset.user_id != current_user.id:
        raise HTTPException(404, "Preset not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(preset, k, v)
    await db.commit()
    await db.refresh(preset)
    return preset


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(
    preset_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    preset = await db.get(IndicatorPreset, preset_id)
    if preset is None or preset.user_id != current_user.id:
        raise HTTPException(404, "Preset not found")
    await db.delete(preset)
    await db.commit()
