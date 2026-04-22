from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import inspect, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.instrument_event import (
    InstrumentEvent,
    InstrumentEventFetchState,
    InstrumentEventType,
)
from app.providers import get_default_event_provider

logger = logging.getLogger(__name__)

EVENT_FETCH_VERSION = 2
_fetch_state_schema_checked = False


async def _ensure_fetch_state_schema(db: AsyncSession) -> None:
    global _fetch_state_schema_checked
    if _fetch_state_schema_checked:
        return

    conn = await db.connection()

    def _needs_fetch_version(sync_conn) -> bool:
        inspector = inspect(sync_conn)
        if "instrument_event_fetch_state" not in inspector.get_table_names():
            return False
        columns = {column["name"] for column in inspector.get_columns("instrument_event_fetch_state")}
        return "fetch_version" not in columns

    if await conn.run_sync(_needs_fetch_version):
        await db.execute(
            text(
                "ALTER TABLE instrument_event_fetch_state "
                "ADD COLUMN IF NOT EXISTS fetch_version INTEGER NOT NULL DEFAULT 1"
            )
        )
        await db.flush()

    _fetch_state_schema_checked = True


async def fetch_and_store_instrument_events(db: AsyncSession, instrument: Instrument) -> int:
    if instrument.is_synthetic:
        return 0
    await _ensure_fetch_state_schema(db)
    provider = get_default_event_provider()

    events = await asyncio.get_event_loop().run_in_executor(
        None,
        provider.fetch_instrument_events,
        instrument.symbol,
    )
    fetched_at = max((event.fetched_at for event in events), default=datetime.now(UTC))
    earnings_count = sum(
        1
        for event in events
        if event.event_type in {InstrumentEventType.EARNINGS, InstrumentEventType.EARNINGS_ESTIMATE}
    )

    inserted = 0
    for event in events:
        values = {
            "event_type": event.event_type,
            "event_time": event.event_time,
            "time_hint": event.time_hint,
            "title": event.title,
            "value": event.value,
            "actual": event.actual,
            "eps_estimate": event.eps_estimate,
            "eps_actual": event.eps_actual,
            "eps_surprise": event.eps_surprise,
            "eps_surprise_pct": event.eps_surprise_pct,
            "dividend_amount": event.dividend_amount,
            "split_ratio": event.split_ratio,
            "source_event_key": event.source_event_key,
            "raw_payload": event.raw_payload,
            "fetched_at": event.fetched_at,
            "instrument_id": instrument.id,
            "source": provider.name,
            "currency": instrument.currency,
        }
        stmt = (
            pg_insert(InstrumentEvent)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_instrument_event_source_key",
                set_={
                    "event_type": values["event_type"],
                    "event_time": values["event_time"],
                    "time_hint": values["time_hint"],
                    "title": values["title"],
                    "value": values.get("value"),
                    "actual": values.get("actual"),
                    "eps_estimate": values.get("eps_estimate"),
                    "eps_actual": values.get("eps_actual"),
                    "eps_surprise": values.get("eps_surprise"),
                    "eps_surprise_pct": values.get("eps_surprise_pct"),
                    "dividend_amount": values.get("dividend_amount"),
                    "split_ratio": values.get("split_ratio"),
                    "currency": values.get("currency"),
                    "raw_payload": values.get("raw_payload"),
                    "fetched_at": values["fetched_at"],
                },
            )
        )
        await db.execute(stmt)
        inserted += 1

    state_stmt = (
        pg_insert(InstrumentEventFetchState)
        .values(
            instrument_id=instrument.id,
            source=provider.name,
            fetched_at=fetched_at,
            event_count=len(events),
            earnings_count=earnings_count,
            fetch_version=EVENT_FETCH_VERSION,
        )
        .on_conflict_do_update(
            constraint="uq_instrument_event_fetch_state_source",
            set_={
                "fetched_at": fetched_at,
                "event_count": len(events),
                "earnings_count": earnings_count,
                "fetch_version": EVENT_FETCH_VERSION,
            },
        )
    )
    await db.execute(state_stmt)
    await db.flush()
    return inserted


async def ensure_instrument_events_loaded(
    db: AsyncSession,
    instrument: Instrument,
    *,
    refresh: bool = False,
) -> None:
    if instrument.is_synthetic:
        return
    await _ensure_fetch_state_schema(db)
    provider = get_default_event_provider()
    state = (
        await db.execute(
            select(InstrumentEventFetchState).where(
                InstrumentEventFetchState.instrument_id == instrument.id,
                InstrumentEventFetchState.source == provider.name,
            )
        )
    ).scalar_one_or_none()
    if refresh or state is None or state.fetch_version < EVENT_FETCH_VERSION:
        await fetch_and_store_instrument_events(db, instrument)


async def query_instrument_events(
    db: AsyncSession,
    instrument: Instrument,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[InstrumentEvent]:
    stmt = select(InstrumentEvent).where(InstrumentEvent.instrument_id == instrument.id)
    if start is not None:
        stmt = stmt.where(InstrumentEvent.event_time >= start)
    if end is not None:
        stmt = stmt.where(InstrumentEvent.event_time <= end)
    stmt = stmt.order_by(InstrumentEvent.event_time.desc(), InstrumentEvent.event_type)
    return (await db.execute(stmt)).scalars().all()
