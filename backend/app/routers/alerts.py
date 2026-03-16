from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.indicator_alert import IndicatorAlert
from app.models.ohlcv import Timeframe
from app.models.price_alert import AlertStatus, PriceAlert
from app.models.user import User
from app.schemas.alert import PriceAlertCreate, PriceAlertOut, PriceAlertUpdate
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ── Price Alerts ──────────────────────────────────────────────────────────────


@router.get("/price", response_model=list[PriceAlertOut])
async def list_price_alerts(
    instrument_id: int | None = Query(None),
    status: AlertStatus | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(PriceAlert).where(PriceAlert.user_id == current_user.id)
    if instrument_id:
        stmt = stmt.where(PriceAlert.instrument_id == instrument_id)
    if status:
        stmt = stmt.where(PriceAlert.status == status)
    result = await db.execute(stmt.order_by(PriceAlert.created_at.desc()))
    return result.scalars().all()


@router.post("/price", response_model=PriceAlertOut, status_code=201)
async def create_price_alert(
    body: PriceAlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = PriceAlert(**body.model_dump(), user_id=current_user.id)
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.patch("/price/{alert_id}", response_model=PriceAlertOut)
async def update_price_alert(
    alert_id: int,
    body: PriceAlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = await db.get(PriceAlert, alert_id)
    if alert is None or alert.user_id != current_user.id:
        raise HTTPException(404, "Alert not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(alert, k, v)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/price/{alert_id}", status_code=204)
async def delete_price_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = await db.get(PriceAlert, alert_id)
    if alert is None or alert.user_id != current_user.id:
        raise HTTPException(404, "Alert not found")
    await db.delete(alert)
    await db.commit()


@router.post("/price/{alert_id}/rearm", response_model=PriceAlertOut)
async def rearm_price_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = await db.get(PriceAlert, alert_id)
    if alert is None or alert.user_id != current_user.id:
        raise HTTPException(404, "Alert not found")
    alert.status = AlertStatus.ACTIVE
    await db.commit()
    await db.refresh(alert)
    return alert


# ── Indicator Alerts ──────────────────────────────────────────────────────────


class IndicatorAlertCreate(BaseModel):
    instrument_id: int
    timeframe: Timeframe
    indicator_a_type: str
    indicator_a_params: dict = {}
    condition: str
    threshold_value: Decimal | None = None
    indicator_b_type: str | None = None
    indicator_b_params: dict | None = None
    repeat: bool = False
    notes: str | None = None


class IndicatorAlertOut(BaseModel):
    id: int
    instrument_id: int
    timeframe: str
    indicator_a_type: str
    indicator_a_params: dict
    condition: str
    threshold_value: Decimal | None
    indicator_b_type: str | None
    indicator_b_params: dict | None
    status: str
    repeat: bool
    notes: str | None
    triggered_at: datetime | None
    trigger_count: int
    last_value_a: Decimal | None
    last_value_b: Decimal | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.get("/indicator", response_model=list[IndicatorAlertOut])
async def list_indicator_alerts(
    instrument_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(IndicatorAlert).where(IndicatorAlert.user_id == current_user.id)
    if instrument_id:
        stmt = stmt.where(IndicatorAlert.instrument_id == instrument_id)
    result = await db.execute(stmt.order_by(IndicatorAlert.created_at.desc()))
    return result.scalars().all()


@router.post("/indicator", response_model=IndicatorAlertOut, status_code=201)
async def create_indicator_alert(
    body: IndicatorAlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.indicators import INDICATOR_REGISTRY

    if body.indicator_a_type not in INDICATOR_REGISTRY:
        raise HTTPException(400, f"Unknown indicator: {body.indicator_a_type}")
    if body.indicator_b_type and body.indicator_b_type not in INDICATOR_REGISTRY:
        raise HTTPException(400, f"Unknown indicator: {body.indicator_b_type}")
    if body.threshold_value is None and body.indicator_b_type is None:
        raise HTTPException(400, "Must provide either threshold_value or indicator_b_type")

    alert = IndicatorAlert(**body.model_dump(), user_id=current_user.id)
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


@router.delete("/indicator/{alert_id}", status_code=204)
async def delete_indicator_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = await db.get(IndicatorAlert, alert_id)
    if alert is None or alert.user_id != current_user.id:
        raise HTTPException(404, "Alert not found")
    await db.delete(alert)
    await db.commit()


# ── WebSocket ─────────────────────────────────────────────────────────────────


@router.websocket("/ws")
async def alerts_websocket(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data:
                await ws_manager.send_personal(websocket, {"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
