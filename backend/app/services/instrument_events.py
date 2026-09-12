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
from app.models.ohlcv import OHLCVBar
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.models.provider_runtime import ProviderCapability
from app.providers import provider_symbol_for_instrument
from app.providers.base import InstrumentEventRecord
from app.services.adjustment_factors import (
    materialize_local_provider_adjusted_view,
    persist_adjustment_factor_observations,
)
from app.services.instrument_mastering import ensure_external_identifier
from app.services.provider_runtime import execute_provider_call

logger = logging.getLogger(__name__)

# Bump when the persisted provider-event shape gains fields that require a
# refresh of previously fetched rows (currently, explicit adjustment factors).
EVENT_FETCH_VERSION = 3


async def _materialize_provider_adjusted_views(
    db: AsyncSession,
    instrument: Instrument,
    events: list[InstrumentEventRecord],
) -> None:
    """Apply explicit provider factors to raw bars already in the cache.

    Event and price-history refreshes are independent workflows, so either can
    arrive first. When event data includes an explicit provider factor,
    materialize every raw timeframe already present for this instrument. The
    materializer remains fail-closed for missing, mixed, or incomplete
    evidence; split-only and amount-only events do not enter this path.
    """

    if not any(
        event.event_type in {InstrumentEventType.SPLIT, InstrumentEventType.DIVIDEND}
        and event.adjustment_factor is not None
        for event in events
    ):
        return

    raw_timeframes = (
        (
            await db.execute(
                select(OHLCVBar.timeframe)
                .where(
                    OHLCVBar.instrument_id == instrument.id,
                    OHLCVBar.is_adjusted.is_(False),
                    OHLCVBar.is_derived.is_(False),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    for timeframe in raw_timeframes:
        result = await materialize_local_provider_adjusted_view(
            db,
            instrument_id=instrument.id,
            timeframe=timeframe,
        )
        if result.status not in {"applied", "not_observed"}:
            logger.info(
                "Provider-factor materialization for %s %s remained %s: %s",
                instrument.symbol,
                timeframe.value,
                result.status,
                result.reason,
            )


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
            "adjustment_factor": event.adjustment_factor,
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
                    "adjustment_factor": values.get("adjustment_factor"),
                    "currency": values.get("currency"),
                    "raw_payload": values.get("raw_payload"),
                    "fetched_at": values["fetched_at"],
                },
            )
        )
        await db.execute(stmt)
        inserted += 1

    await persist_adjustment_factor_observations(
        db,
        instrument_id=instrument.id,
        data_source_id=execution.data_source.id,
        provider_symbol=provider_symbol_for_instrument(instrument, execution.provider_name),
        events=events,
    )
    await _materialize_provider_adjusted_views(db, instrument, events)

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
            select(InstrumentDatasetState)
            .where(
                InstrumentDatasetState.instrument_id == instrument.id,
                InstrumentDatasetState.dataset_type == "events",
                InstrumentDatasetState.dataset_key == "calendar",
                InstrumentDatasetState.status == DatasetStatus.FRESH,
                InstrumentDatasetState.stale_after.is_not(None),
                InstrumentDatasetState.stale_after > datetime.now(UTC),
            )
            .order_by(InstrumentDatasetState.stale_after.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if fresh_dataset is not None and not refresh:
        return

    state = (
        await db.execute(
            select(InstrumentEventFetchState)
            .where(InstrumentEventFetchState.instrument_id == instrument.id)
            .order_by(InstrumentEventFetchState.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if (
        refresh
        or state is None
        or state.fetch_version < EVENT_FETCH_VERSION
        or fresh_dataset is None
    ):
        await fetch_and_store_instrument_events(db, instrument)


async def query_instrument_events(
    db: AsyncSession,
    instrument: Instrument,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[InstrumentEvent]:
    if start is not None:
        start = start.replace(tzinfo=UTC) if start.tzinfo is None else start.astimezone(UTC)
    if end is not None:
        end = end.replace(tzinfo=UTC) if end.tzinfo is None else end.astimezone(UTC)
    stmt = select(InstrumentEvent).where(InstrumentEvent.instrument_id == instrument.id)
    if start is not None:
        stmt = stmt.where(InstrumentEvent.event_time >= start)
    if end is not None:
        stmt = stmt.where(InstrumentEvent.event_time <= end)
    stmt = stmt.order_by(InstrumentEvent.event_time.desc(), InstrumentEvent.event_type)
    return (await db.execute(stmt)).scalars().all()
