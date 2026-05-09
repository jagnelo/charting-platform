from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.ohlcv import Timeframe
from app.models.price_alert import AlertCondition, AlertStatus, PriceAlert
from app.models.radar import (
    RadarDetection,
    RadarOutcomeStatus,
    RadarRun,
    RadarSetupThread,
    RadarSetupType,
    RadarState,
)
from app.models.user import User
from app.models.watchlist import Watchlist, WatchlistItem
from app.schemas.alert import PriceAlertOut
from app.schemas.radar import (
    RadarDetectionDetailOut,
    RadarDetectionSummaryOut,
    RadarEvidenceOut,
    RadarOutcomeSummaryOut,
    RadarRunOut,
    RadarSetupThreadOut,
    RadarThreadEventOut,
    RadarWatchlistActionOut,
)
from app.services.radar_engine import (
    LONG_BIASED_SETUPS,
    SHORT_BIASED_SETUPS,
    get_detection_with_instrument,
    latest_run,
    run_radar_scan,
)

router = APIRouter(prefix="/radar", tags=["radar"])


class RadarRunCreate(BaseModel):
    timeframe: Timeframe = Timeframe.D1


class RadarWatchlistActionCreate(BaseModel):
    watchlist_id: int | None = None


def _to_summary(detection: RadarDetection) -> RadarDetectionSummaryOut:
    instrument = detection.instrument
    return RadarDetectionSummaryOut(
        id=detection.id,
        run_id=detection.run_id,
        instrument_id=detection.instrument_id,
        instrument_symbol=instrument.symbol,
        instrument_name=instrument.name,
        timeframe=detection.timeframe,
        setup_type=detection.setup_type,
        score=float(detection.score),
        observed_at=detection.observed_at,
        signal_at=detection.signal_at,
        context_at=detection.context_at,
        state=detection.state,
        state_reason=detection.state_reason,
        fresh_until=detection.fresh_until,
        thread_id=detection.thread_id,
        thread_event_index=detection.thread_event_index,
        key_level_price=float(detection.key_level_price)
        if detection.key_level_price is not None
        else None,
        entry_price=float(detection.entry_price) if detection.entry_price is not None else None,
        invalidation_price=float(detection.invalidation_price)
        if detection.invalidation_price is not None
        else None,
        target_price=float(detection.target_price) if detection.target_price is not None else None,
        outcome_status=detection.outcome_status,
        outcome_last_evaluated_at=detection.outcome_last_evaluated_at,
        bars_since_signal=detection.bars_since_signal,
        max_favorable_excursion_pct=float(detection.max_favorable_excursion_pct)
        if detection.max_favorable_excursion_pct is not None
        else None,
        max_adverse_excursion_pct=float(detection.max_adverse_excursion_pct)
        if detection.max_adverse_excursion_pct is not None
        else None,
        target_hit_at=detection.target_hit_at,
        invalidated_at=detection.invalidated_at,
        summary=detection.summary,
        invalidation_hint=detection.invalidation_hint,
        score_factors=detection.score_factors or {},
        created_at=detection.created_at,
        updated_at=detection.updated_at,
    )


def _to_thread_event(detection: RadarDetection) -> RadarThreadEventOut:
    return RadarThreadEventOut(
        id=detection.id,
        setup_type=detection.setup_type,
        score=float(detection.score),
        observed_at=detection.observed_at,
        signal_at=detection.signal_at,
        context_at=detection.context_at,
        state=detection.state,
        state_reason=detection.state_reason,
        thread_event_index=detection.thread_event_index,
        key_level_price=float(detection.key_level_price)
        if detection.key_level_price is not None
        else None,
        entry_price=float(detection.entry_price) if detection.entry_price is not None else None,
        invalidation_price=float(detection.invalidation_price)
        if detection.invalidation_price is not None
        else None,
        target_price=float(detection.target_price) if detection.target_price is not None else None,
        outcome_status=detection.outcome_status,
        outcome_last_evaluated_at=detection.outcome_last_evaluated_at,
        bars_since_signal=detection.bars_since_signal,
        max_favorable_excursion_pct=float(detection.max_favorable_excursion_pct)
        if detection.max_favorable_excursion_pct is not None
        else None,
        max_adverse_excursion_pct=float(detection.max_adverse_excursion_pct)
        if detection.max_adverse_excursion_pct is not None
        else None,
        target_hit_at=detection.target_hit_at,
        invalidated_at=detection.invalidated_at,
        summary=detection.summary,
        invalidation_hint=detection.invalidation_hint,
        created_at=detection.created_at,
        updated_at=detection.updated_at,
    )


def _thread_history_rows(thread: RadarSetupThread) -> list[RadarDetection]:
    deduped_by_index: dict[int, RadarDetection] = {}
    passthrough: list[RadarDetection] = []
    ordered = sorted(
        list(thread.detections or []),
        key=lambda item: (
            item.signal_at,
            item.thread_event_index or 0,
            item.observed_at,
            item.id,
        ),
    )
    for detection in ordered:
        if detection.thread_event_index is None:
            passthrough.append(detection)
            continue
        existing = deduped_by_index.get(detection.thread_event_index)
        if (
            existing is None
            or detection.observed_at > existing.observed_at
            or detection.id > existing.id
        ):
            deduped_by_index[detection.thread_event_index] = detection
    return sorted(
        [*passthrough, *deduped_by_index.values()],
        key=lambda item: (item.signal_at, item.thread_event_index or 0, item.id),
    )


def _history_identity_key(detection: RadarDetection) -> tuple:
    return (
        detection.timeframe.value,
        detection.thread_id,
        detection.thread_event_index,
        detection.setup_type.value,
        detection.state.value,
        detection.signal_at,
        detection.context_at,
        round(float(detection.key_level_price or 0.0), 4),
    )


def _history_event_time(detection: RadarDetection) -> datetime:
    return (
        detection.invalidated_at
        or detection.target_hit_at
        or detection.outcome_last_evaluated_at
        or detection.signal_at
        or detection.observed_at
    )


def _dedupe_history_rows(rows: list[RadarDetection]) -> list[RadarDetection]:
    deduped: dict[tuple, RadarDetection] = {}
    for detection in rows:
        key = _history_identity_key(detection)
        existing = deduped.get(key)
        if (
            existing is None
            or detection.observed_at > existing.observed_at
            or detection.id > existing.id
        ):
            deduped[key] = detection
    return sorted(
        deduped.values(),
        key=lambda item: (
            _history_event_time(item),
            item.thread_event_index or 0,
            item.observed_at,
            item.id,
        ),
        reverse=True,
    )


def _to_detail(detection: RadarDetection) -> RadarDetectionDetailOut:
    summary = _to_summary(detection)
    thread = detection.thread
    thread_history = []
    thread_out = None
    if thread is not None:
        thread_out = RadarSetupThreadOut.model_validate(thread)
        ordered_history = _thread_history_rows(thread)
        thread_history = [_to_thread_event(item) for item in ordered_history]
    return RadarDetectionDetailOut(
        **summary.model_dump(),
        evidence=RadarEvidenceOut(
            overlays=(detection.evidence_json or {}).get("overlays", []),
            indicator_visuals=(detection.evidence_json or {}).get("indicator_visuals", []),
            drawing_visuals=(detection.evidence_json or {}).get("drawing_visuals", []),
            metrics=(detection.evidence_json or {}).get("metrics", {}),
            structures=(detection.evidence_json or {}).get("structures", []),
        ),
        thread=thread_out,
        thread_history=thread_history,
    )


@router.get("/runs", response_model=list[RadarRunOut])
async def list_radar_runs(
    limit: int = Query(5, ge=1, le=50),
    timeframe: Timeframe | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(RadarRun)
    if timeframe is not None:
        stmt = stmt.where(RadarRun.timeframe == timeframe)
    rows = (
        (
            await db.execute(
                stmt.order_by(RadarRun.started_at.desc(), RadarRun.id.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return rows


@router.post("/run", response_model=RadarRunOut)
async def trigger_radar_run(
    body: RadarRunCreate | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await run_radar_scan(db, timeframe=(body.timeframe if body else Timeframe.D1))
    return run


@router.get("/detections", response_model=list[RadarDetectionSummaryOut])
async def list_radar_detections(
    timeframe: Timeframe | None = Query(None),
    setup_type: RadarSetupType | None = Query(None),
    state: RadarState | None = Query(None),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    symbol: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    active_only: bool = Query(True),
    fresh_only: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await latest_run(db, timeframe=timeframe)
    if run is None:
        return []

    stmt = (
        select(RadarDetection)
        .where(RadarDetection.run_id == run.id, RadarDetection.score >= min_score)
        .options(selectinload(RadarDetection.instrument), selectinload(RadarDetection.thread))
        .order_by(RadarDetection.score.desc(), RadarDetection.id.desc())
        .limit(limit)
    )
    if setup_type is not None:
        stmt = stmt.where(RadarDetection.setup_type == setup_type)
    if state is not None:
        stmt = stmt.where(RadarDetection.state == state)
    effective_active_only = active_only if fresh_only is None else fresh_only
    if effective_active_only:
        stmt = stmt.where(
            RadarDetection.outcome_status == RadarOutcomeStatus.OPEN,
            RadarDetection.state.in_([RadarState.DEVELOPING, RadarState.CONFIRMED]),
        )

    detections = list((await db.execute(stmt)).scalars().all())
    if symbol:
        symbol_upper = symbol.upper()
        detections = [
            d for d in detections if d.instrument and symbol_upper in d.instrument.symbol.upper()
        ]
    return [_to_summary(d) for d in detections]


@router.get("/detections/{detection_id}", response_model=RadarDetectionDetailOut)
async def get_radar_detection(
    detection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    detection = await get_detection_with_instrument(db, detection_id)
    if detection is None:
        raise HTTPException(status_code=404, detail="Radar detection not found")
    return _to_detail(detection)


@router.get("/instruments/{instrument_id}/overlays", response_model=list[RadarDetectionDetailOut])
async def get_instrument_radar_overlays(
    instrument_id: int,
    timeframe: Timeframe | None = Query(None),
    detection_id: int | None = Query(None),
    active_only: bool = Query(True),
    fresh_only: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await latest_run(db, timeframe=timeframe)
    if run is None:
        return []

    stmt = (
        select(RadarDetection)
        .where(RadarDetection.run_id == run.id, RadarDetection.instrument_id == instrument_id)
        .options(
            selectinload(RadarDetection.instrument),
            selectinload(RadarDetection.thread).selectinload(RadarSetupThread.detections),
        )
        .order_by(RadarDetection.score.desc(), RadarDetection.id.desc())
    )
    if detection_id is not None:
        stmt = stmt.where(RadarDetection.id == detection_id)
    effective_active_only = active_only if fresh_only is None else fresh_only
    if effective_active_only:
        stmt = stmt.where(
            RadarDetection.outcome_status == RadarOutcomeStatus.OPEN,
            RadarDetection.state.in_([RadarState.DEVELOPING, RadarState.CONFIRMED]),
        )
    rows = list((await db.execute(stmt)).scalars().all())
    return [_to_detail(row) for row in rows]


@router.get("/instruments/{instrument_id}/history", response_model=list[RadarDetectionDetailOut])
async def get_instrument_radar_history(
    instrument_id: int,
    timeframe: Timeframe | None = Query(None),
    limit: int = Query(150, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(RadarDetection)
        .where(RadarDetection.instrument_id == instrument_id)
        .options(
            selectinload(RadarDetection.instrument),
            selectinload(RadarDetection.thread).selectinload(RadarSetupThread.detections),
        )
        .order_by(RadarDetection.signal_at.desc(), RadarDetection.id.desc())
        .limit(limit)
    )
    if timeframe is not None:
        stmt = stmt.where(RadarDetection.timeframe == timeframe)
    rows = list((await db.execute(stmt)).scalars().all())
    return [_to_detail(row) for row in _dedupe_history_rows(rows)]


@router.get("/outcomes/summary", response_model=list[RadarOutcomeSummaryOut])
async def get_radar_outcome_summary(
    timeframe: Timeframe | None = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(RadarDetection).order_by(RadarDetection.signal_at.desc()).limit(limit)
    if timeframe is not None:
        stmt = stmt.where(RadarDetection.timeframe == timeframe)
    rows = list((await db.execute(stmt)).scalars().all())
    grouped: dict[tuple[Timeframe, RadarSetupType], list[RadarDetection]] = {}
    for row in rows:
        grouped.setdefault((row.timeframe, row.setup_type), []).append(row)

    summaries: list[RadarOutcomeSummaryOut] = []
    for (row_timeframe, setup_type), detections in sorted(
        grouped.items(),
        key=lambda item: (item[0][0].value, item[0][1].value),
    ):
        total = len(detections)
        open_count = sum(1 for row in detections if row.outcome_status.value == "open")
        target_hit_count = sum(1 for row in detections if row.outcome_status.value == "target_hit")
        invalidated_count = sum(
            1 for row in detections if row.outcome_status.value == "invalidated"
        )
        stale_count = sum(1 for row in detections if row.outcome_status.value == "stale")
        mfes = [
            float(row.max_favorable_excursion_pct)
            for row in detections
            if row.max_favorable_excursion_pct is not None
        ]
        maes = [
            float(row.max_adverse_excursion_pct)
            for row in detections
            if row.max_adverse_excursion_pct is not None
        ]
        summaries.append(
            RadarOutcomeSummaryOut(
                timeframe=row_timeframe,
                setup_type=setup_type,
                total=total,
                open_count=open_count,
                target_hit_count=target_hit_count,
                invalidated_count=invalidated_count,
                stale_count=stale_count,
                target_hit_rate=target_hit_count / total if total else 0.0,
                invalidated_rate=invalidated_count / total if total else 0.0,
                stale_rate=stale_count / total if total else 0.0,
                avg_mfe_pct=(sum(mfes) / len(mfes)) if mfes else None,
                avg_mae_pct=(sum(maes) / len(maes)) if maes else None,
            )
        )
    summaries.sort(
        key=lambda row: (row.timeframe.value, -row.target_hit_rate, row.setup_type.value)
    )
    return summaries


def _default_radar_watchlist_name() -> str:
    return "Radar Discoveries"


async def _resolve_watchlist_for_action(
    db: AsyncSession,
    user_id: int,
    requested_watchlist_id: int | None,
) -> Watchlist:
    if requested_watchlist_id is not None:
        watchlist = (
            await db.execute(
                select(Watchlist).where(
                    Watchlist.id == requested_watchlist_id,
                    Watchlist.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if watchlist is None:
            raise HTTPException(404, "Watchlist not found")
        return watchlist

    watchlist = (
        await db.execute(
            select(Watchlist).where(
                Watchlist.user_id == user_id,
                Watchlist.is_default.is_(True),
            )
        )
    ).scalar_one_or_none()
    if watchlist is not None:
        return watchlist

    watchlist = (
        await db.execute(
            select(Watchlist).where(
                Watchlist.user_id == user_id,
                Watchlist.name == _default_radar_watchlist_name(),
            )
        )
    ).scalar_one_or_none()
    if watchlist is not None:
        return watchlist

    watchlist = Watchlist(
        user_id=user_id,
        name=_default_radar_watchlist_name(),
        description="Radar-promoted discoveries",
        is_default=False,
        is_managed=False,
        is_locked=False,
        position=9999,
    )
    db.add(watchlist)
    await db.flush()
    return watchlist


@router.post(
    "/detections/{detection_id}/actions/add-to-watchlist",
    response_model=RadarWatchlistActionOut,
)
async def add_radar_detection_to_watchlist(
    detection_id: int,
    body: RadarWatchlistActionCreate | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    detection = await get_detection_with_instrument(db, detection_id)
    if detection is None:
        raise HTTPException(status_code=404, detail="Radar detection not found")
    watchlist = await _resolve_watchlist_for_action(
        db,
        current_user.id,
        body.watchlist_id if body else None,
    )
    existing = (
        await db.execute(
            select(WatchlistItem).where(
                WatchlistItem.watchlist_id == watchlist.id,
                WatchlistItem.instrument_id == detection.instrument_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return RadarWatchlistActionOut(
            watchlist_id=watchlist.id,
            watchlist_name=watchlist.name,
            item_id=existing.id,
        )
    item = WatchlistItem(
        watchlist_id=watchlist.id,
        instrument_id=detection.instrument_id,
        notes=f"Radar: {detection.setup_type.value.replace('_', ' ')} @ {float(detection.entry_price or detection.key_level_price or 0):.2f}",
    )
    db.add(item)
    await db.flush()
    await db.commit()
    return RadarWatchlistActionOut(
        watchlist_id=watchlist.id,
        watchlist_name=watchlist.name,
        item_id=item.id,
    )


def _alert_condition_for_detection(detection: RadarDetection) -> AlertCondition:
    if detection.setup_type in LONG_BIASED_SETUPS:
        return AlertCondition.CROSSES_ABOVE
    if detection.setup_type in SHORT_BIASED_SETUPS:
        return AlertCondition.CROSSES_BELOW
    return AlertCondition.TOUCHES


def _price_alert_out(alert: PriceAlert) -> PriceAlertOut:
    return PriceAlertOut(
        id=alert.id,
        instrument_id=alert.instrument_id,
        instrument_currency=alert.instrument.currency if alert.instrument else None,
        instrument_symbol=alert.instrument.symbol if alert.instrument else "",
        condition=alert.condition,
        threshold_price=alert.threshold_price,
        reference_price=alert.reference_price,
        price_field=alert.price_field,
        within_percent=alert.within_percent,
        status=alert.status,
        repeat=alert.repeat,
        show_projection=alert.show_projection,
        notes=alert.notes,
        triggered_at=alert.triggered_at,
        trigger_count=alert.trigger_count,
        last_known_price=alert.last_known_price,
        created_at=alert.created_at,
        updated_at=alert.updated_at,
    )


@router.post("/detections/{detection_id}/actions/create-price-alert", response_model=PriceAlertOut)
async def create_radar_price_alert(
    detection_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    detection = await get_detection_with_instrument(db, detection_id)
    if detection is None:
        raise HTTPException(status_code=404, detail="Radar detection not found")
    threshold = detection.entry_price or detection.key_level_price
    if threshold is None:
        raise HTTPException(status_code=400, detail="Radar detection has no actionable price")
    note = (
        f"Radar {detection.setup_type.value.replace('_', ' ')} on "
        f"{detection.instrument.symbol if detection.instrument else detection.instrument_id}"
    )
    alert = PriceAlert(
        user_id=current_user.id,
        instrument_id=detection.instrument_id,
        condition=_alert_condition_for_detection(detection),
        threshold_price=Decimal(str(float(threshold))),
        reference_price=Decimal(str(float(threshold))),
        price_field="close",
        status=AlertStatus.ACTIVE,
        repeat=False,
        show_projection=True,
        notes=note,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert, attribute_names=["instrument"])
    await db.commit()
    return _price_alert_out(alert)
