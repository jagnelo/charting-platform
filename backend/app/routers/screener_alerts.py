from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.screener import ScreenerDefinition
from app.models.screener_alert import ScreenerAlert
from app.models.user import User
from app.schemas.screener_alert import ScreenerAlertCreate, ScreenerAlertOut, ScreenerAlertUpdate

router = APIRouter(prefix="/alerts/screener", tags=["screener-alerts"])


def _to_out(alert: ScreenerAlert) -> ScreenerAlertOut:
    return ScreenerAlertOut(
        id=alert.id,
        screener_id=alert.screener_id,
        screener_name=alert.screener.name if alert.screener else "",
        trigger_type=alert.trigger_type,
        status=alert.status,
        repeat=alert.repeat,
        notes=alert.notes,
        triggered_at=alert.triggered_at,
        last_checked_run_id=alert.last_checked_run_id,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


@router.get("", response_model=list[ScreenerAlertOut])
async def list_screener_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        (
            await db.execute(
                select(ScreenerAlert)
                .where(ScreenerAlert.user_id == current_user.id)
                .order_by(ScreenerAlert.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    # Eagerly populate screener names
    screener_ids = {r.screener_id for r in rows}
    screeners = {}
    if screener_ids:
        sd_rows = (
            (
                await db.execute(
                    select(ScreenerDefinition).where(ScreenerDefinition.id.in_(screener_ids))
                )
            )
            .scalars()
            .all()
        )
        screeners = {sd.id: sd for sd in sd_rows}

    out = []
    for row in rows:
        row.screener = screeners.get(row.screener_id)
        out.append(_to_out(row))
    return out


@router.post("", response_model=ScreenerAlertOut, status_code=201)
async def create_screener_alert(
    body: ScreenerAlertCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.trigger_type not in ("entered", "left", "both"):
        raise HTTPException(400, "trigger_type must be 'entered', 'left', or 'both'")

    # Verify screener belongs to user
    sd = (
        await db.execute(
            select(ScreenerDefinition).where(
                ScreenerDefinition.id == body.screener_id,
                ScreenerDefinition.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if sd is None:
        raise HTTPException(404, "Screener not found")

    alert = ScreenerAlert(
        user_id=current_user.id,
        screener_id=body.screener_id,
        trigger_type=body.trigger_type,
        repeat=body.repeat,
        notes=body.notes,
        status="active",
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    alert.screener = sd
    return _to_out(alert)


@router.patch("/{alert_id}", response_model=ScreenerAlertOut)
async def update_screener_alert(
    alert_id: int,
    body: ScreenerAlertUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = (
        await db.execute(
            select(ScreenerAlert).where(
                ScreenerAlert.id == alert_id,
                ScreenerAlert.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(404, "Screener alert not found")

    if body.trigger_type is not None:
        if body.trigger_type not in ("entered", "left", "both"):
            raise HTTPException(400, "trigger_type must be 'entered', 'left', or 'both'")
        alert.trigger_type = body.trigger_type
    if body.repeat is not None:
        alert.repeat = body.repeat
    if body.notes is not None:
        alert.notes = body.notes
    if body.status is not None:
        if body.status not in ("active", "triggered", "paused", "disabled"):
            raise HTTPException(400, "status must be 'active', 'triggered', 'paused', or 'disabled'")
        alert.status = body.status

    await db.commit()
    await db.refresh(alert)

    sd = (
        await db.execute(
            select(ScreenerDefinition).where(ScreenerDefinition.id == alert.screener_id)
        )
    ).scalar_one_or_none()
    alert.screener = sd
    return _to_out(alert)


@router.post("/{alert_id}/rearm", response_model=ScreenerAlertOut)
async def rearm_screener_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-arm a triggered alert so it fires again on the next qualifying screener run."""
    alert = (
        await db.execute(
            select(ScreenerAlert).where(
                ScreenerAlert.id == alert_id,
                ScreenerAlert.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(404, "Screener alert not found")

    alert.status = "active"
    alert.triggered_at = None
    await db.commit()
    await db.refresh(alert)

    sd = (
        await db.execute(
            select(ScreenerDefinition).where(ScreenerDefinition.id == alert.screener_id)
        )
    ).scalar_one_or_none()
    alert.screener = sd
    return _to_out(alert)


@router.delete("/{alert_id}")
async def delete_screener_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    alert = (
        await db.execute(
            select(ScreenerAlert).where(
                ScreenerAlert.id == alert_id,
                ScreenerAlert.user_id == current_user.id,
            )
        )
    ).scalar_one_or_none()
    if alert is None:
        raise HTTPException(404, "Screener alert not found")

    await db.delete(alert)
    await db.commit()
    return {"ok": True}
