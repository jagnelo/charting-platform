from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.auth.jwt import decode_token
from app.database import get_db
from app.models.indicator_alert import IndicatorAlert
from app.models.price_alert import AlertStatus, PriceAlert
from app.models.user import User
from app.schemas.alert import (
    IndicatorAlertCreate,
    IndicatorAlertOut,
    IndicatorAlertUpdate,
    PriceAlertCreate,
    PriceAlertOut,
    PriceAlertUpdate,
)
from app.websocket.manager import ws_manager

router = APIRouter(prefix="/alerts", tags=["alerts"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _enrich_price(alert: PriceAlert) -> PriceAlertOut:
    """Build PriceAlertOut from a fully-loaded ORM object (instrument must be loaded)."""
    d = PriceAlertOut.model_validate(alert)
    d.instrument_currency = alert.instrument.currency if alert.instrument else None
    d.instrument_symbol = alert.instrument.symbol if alert.instrument else ""
    return d


def _enrich_indicator(alert: IndicatorAlert) -> IndicatorAlertOut:
    """Build IndicatorAlertOut from a fully-loaded ORM object (instrument must be loaded)."""
    d = IndicatorAlertOut.model_validate(alert)
    d.instrument_currency = alert.instrument.currency if alert.instrument else None
    d.instrument_symbol = alert.instrument.symbol if alert.instrument else ""
    return d


async def _get_price_alert_enriched(db: AsyncSession, alert_id: int) -> PriceAlertOut:
    """Re-fetch a price alert with instrument loaded and return enriched schema."""
    stmt = (
        select(PriceAlert)
        .options(selectinload(PriceAlert.instrument))
        .where(PriceAlert.id == alert_id)
    )
    result = await db.execute(stmt)
    return _enrich_price(result.scalar_one())


async def _get_indicator_alert_enriched(db: AsyncSession, alert_id: int) -> IndicatorAlertOut:
    """Re-fetch an indicator alert with instrument loaded and return enriched schema."""
    stmt = (
        select(IndicatorAlert)
        .options(selectinload(IndicatorAlert.instrument))
        .where(IndicatorAlert.id == alert_id)
    )
    result = await db.execute(stmt)
    return _enrich_indicator(result.scalar_one())


# ── Price Alerts ──────────────────────────────────────────────────────────────


@router.get("/price", response_model=list[PriceAlertOut])
async def list_price_alerts(
    instrument_id: int | None = Query(None),
    status: AlertStatus | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(PriceAlert)
        .options(selectinload(PriceAlert.instrument))
        .where(PriceAlert.user_id == current_user.id)
    )
    if instrument_id:
        stmt = stmt.where(PriceAlert.instrument_id == instrument_id)
    if status:
        stmt = stmt.where(PriceAlert.status == status)
    result = await db.execute(stmt.order_by(PriceAlert.created_at.desc()))
    return [_enrich_price(a) for a in result.scalars().all()]


@router.post("/price", response_model=PriceAlertOut, status_code=201)
async def create_price_alert(
    body: PriceAlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = PriceAlert(**body.model_dump(), user_id=current_user.id)
    db.add(alert)
    await db.commit()
    return await _get_price_alert_enriched(db, alert.id)


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
    return await _get_price_alert_enriched(db, alert_id)


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
    return await _get_price_alert_enriched(db, alert_id)


# ── Indicator Alerts ──────────────────────────────────────────────────────────


@router.get("/indicator", response_model=list[IndicatorAlertOut])
async def list_indicator_alerts(
    instrument_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(IndicatorAlert)
        .options(selectinload(IndicatorAlert.instrument))
        .where(IndicatorAlert.user_id == current_user.id)
    )
    if instrument_id:
        stmt = stmt.where(IndicatorAlert.instrument_id == instrument_id)
    result = await db.execute(stmt.order_by(IndicatorAlert.created_at.desc()))
    return [_enrich_indicator(a) for a in result.scalars().all()]


@router.post("/indicator", response_model=IndicatorAlertOut, status_code=201)
async def create_indicator_alert(
    body: IndicatorAlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.indicators import INDICATOR_REGISTRY, normalize_indicator_params

    if body.indicator_a_type not in INDICATOR_REGISTRY:
        raise HTTPException(400, f"Unknown indicator: {body.indicator_a_type}")
    if body.indicator_b_type and body.indicator_b_type not in INDICATOR_REGISTRY:
        raise HTTPException(400, f"Unknown indicator: {body.indicator_b_type}")
    if body.threshold_value is None and body.indicator_b_type is None:
        raise HTTPException(400, "Must provide either threshold_value or indicator_b_type")

    payload = body.model_dump()
    payload["indicator_a_params"] = normalize_indicator_params(
        body.indicator_a_type, body.indicator_a_params
    )
    if body.indicator_b_type:
        payload["indicator_b_params"] = normalize_indicator_params(
            body.indicator_b_type, body.indicator_b_params or {}
        )

    alert = IndicatorAlert(**payload, user_id=current_user.id)
    db.add(alert)
    await db.commit()
    return await _get_indicator_alert_enriched(db, alert.id)


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


@router.post("/indicator/{alert_id}/rearm", response_model=IndicatorAlertOut)
async def rearm_indicator_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = await db.get(IndicatorAlert, alert_id)
    if alert is None or alert.user_id != current_user.id:
        raise HTTPException(404, "Alert not found")
    alert.status = AlertStatus.ACTIVE
    await db.commit()
    return await _get_indicator_alert_enriched(db, alert_id)


@router.patch("/indicator/{alert_id}", response_model=IndicatorAlertOut)
async def update_indicator_alert(
    alert_id: int,
    body: IndicatorAlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = await db.get(IndicatorAlert, alert_id)
    if alert is None or alert.user_id != current_user.id:
        raise HTTPException(404, "Alert not found")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(alert, k, v)
    await db.commit()
    return await _get_indicator_alert_enriched(db, alert_id)


# ── WebSocket ─────────────────────────────────────────────────────────────────


@router.websocket("/ws")
async def alerts_websocket(websocket: WebSocket):
    user_id = None
    token = websocket.query_params.get("token")
    if token:
        try:
            payload = decode_token(token)
            if payload.get("type") != "access":
                raise ValueError("wrong token type")
            user_id = int(payload["sub"])
        except Exception:
            await websocket.close(code=4401)
            return
    await ws_manager.connect(websocket, user_id=user_id)
    try:
        while True:
            data = await websocket.receive_text()
            if data:
                await ws_manager.send_personal(websocket, {"type": "pong"})
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
