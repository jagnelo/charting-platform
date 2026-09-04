"""Persistence helpers for normalized provider observations."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.market_data_foundation import FundamentalFact, MarketEvent, ShortInterestObservation
from app.providers.base import FundamentalFactRecord, ShortInterestRecord


async def persist_fundamental_facts(
    db: AsyncSession,
    records: Iterable[FundamentalFactRecord],
    *,
    source: str,
    issuer_id: int | None = None,
    instrument_id: int | None = None,
) -> int:
    inserted = 0
    for record in records:
        query = select(FundamentalFact).where(
            FundamentalFact.source == source,
            FundamentalFact.issuer_id == issuer_id,
            FundamentalFact.instrument_id == instrument_id,
            FundamentalFact.fact_namespace == record.namespace,
            FundamentalFact.fact_key == record.key,
            FundamentalFact.unit == record.unit,
            FundamentalFact.period_start == record.period_start,
            FundamentalFact.period_end == record.period_end,
            FundamentalFact.filed_at == record.filed_at,
        )
        existing = (await db.execute(query)).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            FundamentalFact(
                issuer_id=issuer_id,
                instrument_id=instrument_id,
                fact_namespace=record.namespace,
                fact_key=record.key,
                unit=record.unit,
                value_numeric=record.value_numeric,
                value_text=record.value_text,
                period_start=record.period_start,
                period_end=record.period_end,
                filed_at=record.filed_at,
                accepted_at=record.accepted_at,
                source=source,
                source_identifier=record.source_identifier,
                payload=record.raw_payload,
            )
        )
        inserted += 1
    if inserted:
        await db.flush()
    return inserted


async def persist_short_interest(
    db: AsyncSession,
    instrument_id: int,
    records: Iterable[ShortInterestRecord],
    *,
    source: str,
) -> int:
    inserted = 0
    for record in records:
        existing = (
            await db.execute(
                select(ShortInterestObservation).where(
                    ShortInterestObservation.instrument_id == instrument_id,
                    ShortInterestObservation.settlement_date == record.settlement_date,
                    ShortInterestObservation.source == source,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue
        db.add(
            ShortInterestObservation(
                instrument_id=instrument_id,
                settlement_date=record.settlement_date,
                publication_date=record.publication_date,
                short_position=record.short_position,
                short_percent_float=record.short_percent_float,
                days_to_cover=record.days_to_cover,
                source=source,
                source_identifier=record.source_identifier,
                payload=record.raw_payload,
            )
        )
        inserted += 1
    if inserted:
        await db.flush()
    return inserted


async def persist_market_event(
    db: AsyncSession,
    *,
    event_key: str,
    event_type: str,
    source: str,
    instrument_id: int | None = None,
    issuer_id: int | None = None,
    event_time=None,
    effective_date=None,
    announced_at=None,
    source_version: str | None = None,
    payload: dict | None = None,
    is_provisional: bool = False,
) -> MarketEvent:
    existing = (
        await db.execute(
            select(MarketEvent).where(
                MarketEvent.event_key == event_key,
                MarketEvent.source == source,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.payload = {**(existing.payload or {}), **(payload or {})}
        existing.is_provisional = is_provisional
        return existing
    event = MarketEvent(
        event_key=event_key,
        event_type=event_type,
        source=source,
        instrument_id=instrument_id,
        issuer_id=issuer_id,
        event_time=event_time,
        effective_date=effective_date,
        announced_at=announced_at,
        source_version=source_version,
        payload=payload or {},
        is_provisional=is_provisional,
    )
    db.add(event)
    await db.flush()
    return event
