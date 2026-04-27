from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.instrument import Instrument
from app.models.instrument_event import (
    InstrumentEvent,
    InstrumentEventFetchState,
    InstrumentEventType,
)
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.models.provider_runtime import ProviderCapability
from app.providers import provider_symbol_for_instrument
from app.services.instrument_mastering import ensure_external_identifier
from app.services.provider_runtime import execute_provider_call

logger = logging.getLogger(__name__)

EVENT_FETCH_VERSION = 2


async def fetch_and_store_instrument_events(db: AsyncSession, instrument: Instrument) -> int:
    if instrument.is_synthetic:
        return 0
    execution = await execute_provider_call(
        db,
        ProviderCapability.INSTRUMENT_EVENTS,
        "fetch_instrument_events",
        instrument_id=instrument.id,
        invoke=lambda provider, _provider_symbol: provider.fetch_instrument_events(
            provider_symbol_for_instrument(instrument, provider.name)
        ),
        response_items=lambda result: len(result),
        treat_empty_as_failure=False,
    )

    events = execution.result
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
            "source": execution.provider_name,
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
            source=execution.provider_name,
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

    dataset_state = (
        await db.execute(
            select(InstrumentDatasetState).where(
                InstrumentDatasetState.instrument_id == instrument.id,
                InstrumentDatasetState.data_source_id == execution.data_source.id,
                InstrumentDatasetState.dataset_type == "events",
                InstrumentDatasetState.dataset_key == "calendar",
            )
        )
    ).scalar_one_or_none()
    if dataset_state is None:
        dataset_state = InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=execution.data_source.id,
            dataset_type="events",
            dataset_key="calendar",
        )
        db.add(dataset_state)
    dataset_state.status = DatasetStatus.FRESH if events else DatasetStatus.PENDING
    dataset_state.observed_at = fetched_at
    dataset_state.fetched_at = fetched_at
    dataset_state.stale_after = fetched_at + timedelta(days=1)
    dataset_state.extra_data = {
        "provider": execution.provider_name,
        "event_count": len(events),
        "earnings_count": earnings_count,
    }
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
    await ensure_external_identifier(db, instrument)

    fresh_dataset = (
        await db.execute(
            select(InstrumentDatasetState).where(
                InstrumentDatasetState.instrument_id == instrument.id,
                InstrumentDatasetState.dataset_type == "events",
                InstrumentDatasetState.dataset_key == "calendar",
                InstrumentDatasetState.status == DatasetStatus.FRESH,
                InstrumentDatasetState.stale_after.is_not(None),
                InstrumentDatasetState.stale_after > datetime.now(UTC),
            )
        )
    ).scalar_one_or_none()
    if fresh_dataset is not None and not refresh:
        return

    state = (
        await db.execute(
            select(InstrumentEventFetchState).where(
                InstrumentEventFetchState.instrument_id == instrument.id
            )
        )
    ).scalar_one_or_none()
    if refresh or state is None or state.fetch_version < EVENT_FETCH_VERSION or fresh_dataset is None:
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
