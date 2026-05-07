from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.radar import RadarDetection, RadarRun, RadarSetupThread, RadarSetupType
from app.models.user import User
from app.schemas.radar import (
    RadarDetectionDetailOut,
    RadarDetectionSummaryOut,
    RadarEvidenceOut,
    RadarRunOut,
    RadarSetupThreadOut,
    RadarThreadEventOut,
)
from app.services.radar_engine import get_detection_with_instrument, latest_run, run_radar_scan

router = APIRouter(prefix="/radar", tags=["radar"])


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
        fresh_until=detection.fresh_until,
        thread_id=detection.thread_id,
        thread_event_index=detection.thread_event_index,
        key_level_price=float(detection.key_level_price)
        if detection.key_level_price is not None
        else None,
        summary=detection.summary,
        invalidation_hint=detection.invalidation_hint,
        score_factors=detection.score_factors or {},
    )


def _to_thread_event(detection: RadarDetection) -> RadarThreadEventOut:
    return RadarThreadEventOut(
        id=detection.id,
        setup_type=detection.setup_type,
        score=float(detection.score),
        observed_at=detection.observed_at,
        signal_at=detection.signal_at,
        context_at=detection.context_at,
        thread_event_index=detection.thread_event_index,
        key_level_price=float(detection.key_level_price)
        if detection.key_level_price is not None
        else None,
        summary=detection.summary,
        invalidation_hint=detection.invalidation_hint,
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
            metrics=(detection.evidence_json or {}).get("metrics", {}),
            structures=(detection.evidence_json or {}).get("structures", []),
        ),
        thread=thread_out,
        thread_history=thread_history,
    )


@router.get("/runs", response_model=list[RadarRunOut])
async def list_radar_runs(
    limit: int = Query(5, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        (
            await db.execute(
                select(RadarRun)
                .order_by(RadarRun.started_at.desc(), RadarRun.id.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return rows


@router.post("/run", response_model=RadarRunOut)
async def trigger_radar_run(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await run_radar_scan(db)
    return run


@router.get("/detections", response_model=list[RadarDetectionSummaryOut])
async def list_radar_detections(
    setup_type: RadarSetupType | None = Query(None),
    min_score: float = Query(0.0, ge=0.0, le=1.0),
    symbol: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    fresh_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await latest_run(db)
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
    if fresh_only:
        stmt = stmt.where(RadarDetection.fresh_until >= datetime.now(UTC))

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
    detection_id: int | None = Query(None),
    fresh_only: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await latest_run(db)
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
    if fresh_only:
        stmt = stmt.where(RadarDetection.fresh_until >= datetime.now(UTC))
    rows = list((await db.execute(stmt)).scalars().all())
    return [_to_detail(row) for row in rows]
