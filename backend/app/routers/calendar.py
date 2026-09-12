"""
Persisted instrument economic events.

The read path is database-first. External data is fetched only when an
instrument has no stored event data yet, or when an explicit refresh is
requested by an operator/user action.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.instrument_event import InstrumentEvent
from app.models.market_data_foundation import MarketEvent
from app.models.user import User
from app.services.instrument_events import ensure_instrument_events_loaded, query_instrument_events

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarEvent(BaseModel):
    id: int
    date: str
    event_time: datetime
    fetched_at: datetime
    event_type: str
    symbol: str
    title: str
    value: float | None = None
    actual: float | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    eps_surprise: float | None = None
    eps_surprise_pct: float | None = None
    dividend_amount: float | None = None
    split_ratio: float | None = None
    currency: str | None = None
    time_hint: str
    source: str
    is_estimate: bool = False


class MarketCalendarEvent(BaseModel):
    """A persisted market-wide event from one or more provider sources."""

    id: int
    event_type: str
    event_key: str
    event_time: datetime | None = None
    effective_date: date | None = None
    announced_at: datetime | None = None
    source: str
    source_version: str | None = None
    instrument_id: int | None = None
    issuer_id: int | None = None
    title: str | None = None
    is_provisional: bool = False
    payload: dict = Field(default_factory=dict)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _num(value) -> float | None:
    return float(value) if value is not None else None


def _event_out(event: InstrumentEvent, symbol: str) -> CalendarEvent:
    event_type = event.event_type.value
    return CalendarEvent(
        id=event.id,
        date=event.event_time.date().isoformat(),
        event_time=event.event_time,
        fetched_at=event.fetched_at,
        event_type=event_type,
        symbol=symbol,
        title=event.title,
        value=_num(event.value),
        actual=_num(event.actual),
        eps_estimate=_num(event.eps_estimate),
        eps_actual=_num(event.eps_actual),
        eps_surprise=_num(event.eps_surprise),
        eps_surprise_pct=_num(event.eps_surprise_pct),
        dividend_amount=_num(event.dividend_amount),
        split_ratio=_num(event.split_ratio),
        currency=event.currency,
        time_hint=event.time_hint.value,
        source=event.source,
        is_estimate=event_type.endswith("_estimate"),
    )


async def _load_instrument(db: AsyncSession, symbol: str) -> Instrument:
    instrument = (
        await db.execute(select(Instrument).where(Instrument.symbol == symbol.upper()))
    ).scalar_one_or_none()
    if instrument is None:
        from app.routers.instruments import _create_from_provider

        instrument = await _create_from_provider(symbol.upper(), db)
    if instrument is None:
        raise HTTPException(404, f"Instrument '{symbol}' not found")
    return instrument


@router.get("/instruments/{symbol}/calendar", response_model=list[CalendarEvent])
async def get_instrument_calendar(
    symbol: str,
    start: datetime | None = Query(None),
    end: datetime | None = Query(None),
    refresh: bool = Query(
        False, description="Explicitly refresh source data before returning stored events"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return stored economic/corporate events for a symbol.

    First access for an instrument bootstraps from the configured data source and
    persists the result. Later reads are served from the DB unless refresh=true.
    """
    instrument = await _load_instrument(db, symbol)
    await ensure_instrument_events_loaded(db, instrument, refresh=refresh)
    events = await query_instrument_events(
        db,
        instrument,
        start=_as_utc(start),
        end=_as_utc(end),
    )
    return [_event_out(event, instrument.symbol) for event in events]


@router.get("/market-events", response_model=list[MarketCalendarEvent])
async def get_market_events(
    start: date | None = Query(None, description="Inclusive event date lower bound"),
    end: date | None = Query(None, description="Inclusive event date upper bound"),
    event_type: str | None = Query(None, min_length=1, max_length=80),
    source: str | None = Query(None, min_length=1, max_length=80),
    instrument_id: int | None = Query(None, ge=1),
    issuer_id: int | None = Query(None, ge=1),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Return persisted market-wide events without performing provider I/O.

    Events are written by the opt-in market-event refresh worker.  This read
    path intentionally never refreshes an upstream provider, and applies date
    bounds to ``effective_date`` while retaining events that only carry an
    ``event_time`` timestamp.
    """

    if start is not None and end is not None and end < start:
        raise HTTPException(422, "end must be on or after start")

    filters = []
    if start is not None:
        start_at = datetime.combine(start, time.min, tzinfo=UTC)
        filters.append(
            or_(
                MarketEvent.effective_date >= start,
                and_(
                    MarketEvent.effective_date.is_(None),
                    MarketEvent.event_time >= start_at,
                ),
            )
        )
    if end is not None:
        end_at = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
        filters.append(
            or_(
                MarketEvent.effective_date <= end,
                and_(
                    MarketEvent.effective_date.is_(None),
                    MarketEvent.event_time < end_at,
                ),
            )
        )
    if event_type:
        filters.append(MarketEvent.event_type == event_type.strip().lower())
    if source:
        filters.append(MarketEvent.source == source.strip().lower())
    if instrument_id is not None:
        filters.append(MarketEvent.instrument_id == instrument_id)
    if issuer_id is not None:
        filters.append(MarketEvent.issuer_id == issuer_id)

    query = (
        select(MarketEvent)
        .order_by(
            MarketEvent.effective_date.desc().nullslast(),
            MarketEvent.event_time.desc().nullslast(),
            MarketEvent.id.desc(),
        )
        .limit(limit)
    )
    if filters:
        query = query.where(*filters)
    rows = (await db.execute(query)).scalars().all()
    return [
        MarketCalendarEvent(
            id=row.id,
            event_type=row.event_type,
            event_key=row.event_key,
            event_time=row.event_time,
            effective_date=row.effective_date,
            announced_at=row.announced_at,
            source=row.source,
            source_version=row.source_version,
            instrument_id=row.instrument_id,
            issuer_id=row.issuer_id,
            title=(row.payload or {}).get("name") or (row.payload or {}).get("title"),
            is_provisional=row.is_provisional,
            payload=row.payload or {},
        )
        for row in rows
    ]
