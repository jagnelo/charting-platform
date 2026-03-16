from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.indicator_alert import IndicatorAlert
from app.models.ohlcv import Timeframe
from app.models.price_alert import AlertCondition, AlertStatus
from app.models.user import User
from app.services.auth import get_current_user

router = APIRouter(prefix="/indicator-alerts", tags=["indicator-alerts"])


class IndicatorAlertCreate(BaseModel):
    instrument_id: int
    timeframe: Timeframe
    indicator_type: str
    indicator_params: dict = {}
    condition: AlertCondition
    threshold_value: Decimal | None = None
    compare_indicator_type: str | None = None
    compare_indicator_params: dict | None = None
    repeat: bool = False
    notes: str | None = None


class IndicatorAlertOut(BaseModel):
    id: int
    instrument_id: int
    timeframe: Timeframe
    indicator_type: str
    indicator_params: dict
    condition: AlertCondition
    threshold_value: Decimal | None
    compare_indicator_type: str | None
    compare_indicator_params: dict | None
    status: AlertStatus
    repeat: bool
    notes: str | None
    triggered_at: datetime | None
    trigger_count: int
    last_indicator_value: Decimal | None
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("", response_model=list[IndicatorAlertOut])
async def list_indicator_alerts(
    instrument_id: int | None = Query(None),
    status: AlertStatus | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = select(IndicatorAlert).where(IndicatorAlert.user_id == user.id)
    if instrument_id:
        stmt = stmt.where(IndicatorAlert.instrument_id == instrument_id)
    if status:
        stmt = stmt.where(IndicatorAlert.status == status)
    return (await db.execute(stmt.order_by(IndicatorAlert.created_at.desc()))).scalars().all()


@router.post("", response_model=IndicatorAlertOut, status_code=201)
async def create_indicator_alert(
    body: IndicatorAlertCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    alert = IndicatorAlert(**body.model_dump(), user_id=user.id)
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/{alert_id}", status_code=204)
async def delete_indicator_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    alert = (
        await db.execute(
            select(IndicatorAlert).where(
                IndicatorAlert.id == alert_id, IndicatorAlert.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(404, "Alert not found")
    await db.delete(alert)
    await db.commit()


@router.post("/{alert_id}/rearm", response_model=IndicatorAlertOut)
async def rearm_indicator_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    alert = (
        await db.execute(
            select(IndicatorAlert).where(
                IndicatorAlert.id == alert_id, IndicatorAlert.user_id == user.id
            )
        )
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(404, "Alert not found")
    alert.status = AlertStatus.ACTIVE
    await db.commit()
    await db.refresh(alert)
    return alert
