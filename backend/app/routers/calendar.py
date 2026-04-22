"""
Persisted instrument economic events.

The read path is database-first. External data is fetched only when an
instrument has no stored event data yet, or when an explicit refresh is
requested by an operator/user action.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.instrument import Instrument
from app.models.instrument_event import InstrumentEvent
from app.models.user import User
from app.services.instrument_events import ensure_instrument_events_loaded, query_instrument_events

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarEvent(BaseModel):
    id: int
    date: str
    event_time: datetime
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
    refresh: bool = Query(False, description="Explicitly refresh source data before returning stored events"),
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
