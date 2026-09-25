from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.instrument import Instrument
from app.models.instrument_event import (
    InstrumentEvent,
    InstrumentEventFetchState,
    InstrumentEventPageSnapshot,
    InstrumentEventType,
)
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.models.provider_runtime import ProviderCapability
from app.providers import provider_symbol_for_instrument
from app.providers.base import InstrumentEventPage
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from app.services.instrument_mastering import ensure_external_identifier
from app.services.provider_runtime import (
    ProviderNoDataError,
    ProviderQuotaUnknownError,
    execute_provider_call,
)

logger = logging.getLogger(__name__)

EVENT_FETCH_VERSION = 3


def _event_query_fingerprint(
    provider_name: str,
    provider_symbol: str,
    start_date: str | None,
    end_date: str | None,
) -> str:
    """Identify one immutable provider query so pages are retained forever."""

    material = json.dumps(
        {
            "provider": provider_name,
            "symbol": provider_symbol,
            "start": start_date,
            "end": end_date,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _alpaca_event_dates(
    state: InstrumentEventFetchState | None,
) -> tuple[str, str]:
    """Keep a resumed Alpaca query's date window stable across jobs."""

    start_date = str(
        getattr(settings, "ALPACA_CORPORATE_ACTIONS_START_DATE", "1900-01-01")
        or "1900-01-01"
    )
    if state is not None and state.query_start_date:
        start_date = state.query_start_date
    end_date = (
        state.query_end_date
        if state is not None and state.query_end_date
        else (datetime.now(UTC) + timedelta(days=90)).strftime("%Y-%m-%d")
    )
    return start_date, end_date


def _page_from_legacy_result(result: list) -> InstrumentEventPage:
    """Adapt non-cursor providers without inventing a continuation token."""

    return InstrumentEventPage(events=result, next_page_token=None, raw_payload={})


def _event_page_invocation(
    provider: object,
    provider_symbol: str,
    page_token: str | None,
    *,
    start_date: str,
    end_date: str,
) -> InstrumentEventPage:
    page_method = getattr(provider, "fetch_instrument_events_page", None)
    if callable(page_method):
        # Alpaca accepts the stable query window as keyword arguments. Other
        # cursor providers may expose only the protocol's two positional
        # arguments, so do not force Alpaca-specific kwargs onto them.
        if getattr(provider, "name", "") == "alpaca":
            return page_method(
                provider_symbol,
                page_token,
                start_date=start_date,
                end_date=end_date,
            )
        return page_method(provider_symbol, page_token)
    if page_token:
        # Never switch to a legacy provider after a cursor has been issued:
        # doing so would make the stored continuation meaningless.
        raise ProviderResponseError(
            getattr(provider, "name", "provider"),
            "provider returned a continuation but has no resumable page adapter",
        )
    result = provider.fetch_instrument_events(provider_symbol)
    return _page_from_legacy_result(result)


async def fetch_and_store_instrument_events(db: AsyncSession, instrument: Instrument) -> int:
    if instrument.is_synthetic:
        return 0
    prior_state = (
        await db.execute(
            select(InstrumentEventFetchState)
            .execution_options(populate_existing=True)
            .where(InstrumentEventFetchState.instrument_id == instrument.id)
            .order_by(InstrumentEventFetchState.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    continuation_provider = (
        prior_state.source
        if prior_state is not None and prior_state.continuation_token and not prior_state.complete
        else None
    )
    page_token = (
        prior_state.continuation_token
        if continuation_provider is not None and prior_state is not None
        else None
    )
    if (
        page_token
        and prior_state is not None
        and prior_state.query_fingerprint
        and continuation_provider is not None
    ):
        repeated_page = (
            await db.execute(
                select(InstrumentEventPageSnapshot.id)
                .where(
                    InstrumentEventPageSnapshot.instrument_id == instrument.id,
                    InstrumentEventPageSnapshot.source == continuation_provider,
                    InstrumentEventPageSnapshot.query_fingerprint
                    == prior_state.query_fingerprint,
                    InstrumentEventPageSnapshot.request_page_token == page_token,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if repeated_page is not None:
            raise ProviderResponseError(
                continuation_provider,
                "provider returned a repeated event pagination token",
            )
    operation_cost_overrides: dict[str, int] = {}
    # One provider call produces one durable page. A fairness budget can stop
    # the worker between invocations, but it must never change the result set.
    operation_cost_overrides["alpaca"] = 1
    provider_name = continuation_provider

    def _invoke(provider, provider_symbol):
        start_date, end_date = _alpaca_event_dates(prior_state)
        return _event_page_invocation(
            provider,
            provider_symbol,
            page_token,
            start_date=start_date,
            end_date=end_date,
        )

    execution = await execute_provider_call(
        db,
        ProviderCapability.INSTRUMENT_EVENTS,
        "fetch_instrument_events",
        instrument_id=instrument.id,
        provider_name=provider_name,
        operation_cost_overrides=operation_cost_overrides or None,
        usage_identity=lambda provider_name: provider_symbol_for_instrument(
            instrument, provider_name
        ),
        invoke=_invoke,
        response_items=lambda result: len(result.events),
        treat_empty_as_failure=False,
    )

    page = execution.result
    events = page.events
    provider_symbol = provider_symbol_for_instrument(instrument, execution.provider_name)
    start_date, end_date = _alpaca_event_dates(prior_state)
    if execution.provider_name != "alpaca":
        start_date = None
        end_date = None
    query_fingerprint = _event_query_fingerprint(
        execution.provider_name, provider_symbol, start_date, end_date
    )
    same_query = (
        prior_state is not None
        and prior_state.source == execution.provider_name
        and prior_state.query_fingerprint == query_fingerprint
        and prior_state.continuation_token == page.request_page_token
    )
    page_number = (prior_state.page_count + 1) if same_query and prior_state else 1
    fetched_at = max((event.fetched_at for event in events), default=datetime.now(UTC))

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
                index_elements=["instrument_id", "source", "source_event_key"],
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

    # Persist every successful provider page, including an explicitly empty
    # JSON envelope. An empty response is still quota-consuming evidence and
    # must be available for replay/audit; truthiness would silently discard it.
    if page.raw_payload is not None:
        snapshot_stmt = (
            pg_insert(InstrumentEventPageSnapshot)
            .values(
                instrument_id=instrument.id,
                source=execution.provider_name,
                query_fingerprint=query_fingerprint,
                request_page_token=page.request_page_token,
                next_page_token=page.next_page_token,
                page_number=page_number,
                fetched_at=fetched_at,
                payload=page.raw_payload,
            )
        )
        # Raw provider responses are append-only.  The normalized event table
        # is an up-to-date projection, but a later response for the same query
        # and page may contain an amended event; deduplicating by page number
        # would silently discard that evidence.
        await db.execute(snapshot_stmt)

    event_types = (
        await db.execute(
            select(InstrumentEvent.event_type).where(
                InstrumentEvent.instrument_id == instrument.id,
                InstrumentEvent.source == execution.provider_name,
            )
        )
    ).scalars().all()
    event_count = len(event_types)
    earnings_count = sum(
        1
        for event_type in event_types
        if event_type in {InstrumentEventType.EARNINGS, InstrumentEventType.EARNINGS_ESTIMATE}
    )
    complete = page.complete
    state_stmt = (
        pg_insert(InstrumentEventFetchState)
        .values(
            instrument_id=instrument.id,
            source=execution.provider_name,
            fetched_at=fetched_at,
            event_count=event_count,
            earnings_count=earnings_count,
            fetch_version=EVENT_FETCH_VERSION,
            continuation_token=page.next_page_token,
            query_fingerprint=query_fingerprint,
            query_start_date=start_date,
            query_end_date=end_date,
            page_count=page_number,
            complete=complete,
        )
        .on_conflict_do_update(
            index_elements=["instrument_id", "source"],
            set_={
                "fetched_at": fetched_at,
                "event_count": event_count,
                "earnings_count": earnings_count,
                "fetch_version": EVENT_FETCH_VERSION,
                "continuation_token": page.next_page_token,
                "query_fingerprint": query_fingerprint,
                "query_start_date": start_date,
                "query_end_date": end_date,
                "page_count": page_number,
                "complete": complete,
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
    dataset_state.status = DatasetStatus.FRESH if complete else DatasetStatus.PENDING
    dataset_state.observed_at = fetched_at
    dataset_state.fetched_at = fetched_at
    dataset_state.stale_after = fetched_at + timedelta(days=1) if complete else None
    dataset_state.extra_data = {
        "provider": execution.provider_name,
        "event_count": event_count,
        "earnings_count": earnings_count,
        "page_count": page_number,
        "complete": complete,
        "query_fingerprint": query_fingerprint,
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
    state = (
        await db.execute(
            select(InstrumentEventFetchState)
            .execution_options(populate_existing=True)
            .where(InstrumentEventFetchState.instrument_id == instrument.id)
            .order_by(InstrumentEventFetchState.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    # A different provider may still have a fresh cache row while this
    # provider's cursor is incomplete. Never let that unrelated freshness
    # shortcut strand a durable continuation.
    continuation_pending = (
        state is not None
        and state.fetch_version >= EVENT_FETCH_VERSION
        and not state.complete
        and bool(state.continuation_token)
    )
    if fresh_dataset is not None and not refresh and not continuation_pending:
        return
    if (
        refresh
        or continuation_pending
        or state is None
        or state.fetch_version < EVENT_FETCH_VERSION
        or fresh_dataset is None
    ):
        try:
            await fetch_and_store_instrument_events(db, instrument)
        except ProviderNoDataError:
            logger.info(
                "No routable instrument-event provider for %s; serving stored events",
                instrument.symbol,
            )
        except (
            ProviderNotConfiguredError,
            ProviderRateLimitError,
            ProviderResponseError,
            ProviderQuotaUnknownError,
        ) as exc:
            logger.warning(
                "Instrument-event refresh unavailable for %s; serving stored events (%s)",
                instrument.symbol,
                exc.__class__.__name__,
            )


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
