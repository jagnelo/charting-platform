import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.provider_observation import (
    InstrumentIdentifierSnapshot,
    InstrumentSearchSnapshot,
    LatestPriceSnapshot,
    UniverseDiscoverySnapshot,
)
from app.providers.base import IdentifierRecord, ProviderSearchResult


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _payload_hash(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def store_identifier_snapshot(
    db: AsyncSession,
    *,
    instrument_id: int,
    data_source_id: int,
    provider_symbol: str | None,
    identifiers: list[IdentifierRecord],
    observed_at: datetime | None = None,
    fetched_at: datetime | None = None,
) -> InstrumentIdentifierSnapshot:
    observed_at = observed_at or _now_utc()
    fetched_at = fetched_at or observed_at
    payload = {
        "provider_symbol": provider_symbol,
        "identifiers": [
            {
                "identifier_type": item.identifier_type,
                "identifier_value": item.identifier_value,
                "is_primary": item.is_primary,
                "source": item.source,
                "extra_data": item.extra_data,
            }
            for item in identifiers
        ],
    }
    snapshot_hash = _payload_hash(payload)
    snapshot = (
        await db.execute(
            select(InstrumentIdentifierSnapshot).where(
                InstrumentIdentifierSnapshot.instrument_id == instrument_id,
                InstrumentIdentifierSnapshot.data_source_id == data_source_id,
                InstrumentIdentifierSnapshot.snapshot_hash == snapshot_hash,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = InstrumentIdentifierSnapshot(
            instrument_id=instrument_id,
            data_source_id=data_source_id,
            provider_symbol=provider_symbol,
            observed_at=observed_at,
            fetched_at=fetched_at,
            snapshot_hash=snapshot_hash,
            payload=payload,
        )
        db.add(snapshot)
        await db.flush()
        return snapshot

    snapshot.provider_symbol = provider_symbol
    snapshot.observed_at = observed_at
    snapshot.fetched_at = fetched_at
    snapshot.payload = payload
    return snapshot


async def store_latest_price_snapshot(
    db: AsyncSession,
    *,
    instrument_id: int,
    data_source_id: int,
    provider_symbol: str | None,
    price: float | Decimal,
    observed_at: datetime | None = None,
    fetched_at: datetime | None = None,
) -> LatestPriceSnapshot:
    observed_at = observed_at or _now_utc()
    fetched_at = fetched_at or observed_at
    decimal_price = price if isinstance(price, Decimal) else Decimal(str(price))
    snapshot = LatestPriceSnapshot(
        instrument_id=instrument_id,
        data_source_id=data_source_id,
        provider_symbol=provider_symbol,
        observed_at=observed_at,
        fetched_at=fetched_at,
        price=decimal_price,
        payload={"price": float(decimal_price)},
    )
    db.add(snapshot)
    await db.flush()
    return snapshot


async def store_search_snapshot(
    db: AsyncSession,
    *,
    data_source_id: int,
    query: str,
    results: list[ProviderSearchResult],
    observed_at: datetime | None = None,
    fetched_at: datetime | None = None,
) -> InstrumentSearchSnapshot:
    observed_at = observed_at or _now_utc()
    fetched_at = fetched_at or observed_at
    payload = {
        "query": query,
        "results": [
            {
                "symbol": item.symbol,
                "name": item.name,
                "exchange": item.exchange,
                "instrument_type": item.instrument_type,
            }
            for item in results
        ],
    }
    result_hash = _payload_hash(payload)
    snapshot = (
        await db.execute(
            select(InstrumentSearchSnapshot).where(
                InstrumentSearchSnapshot.data_source_id == data_source_id,
                InstrumentSearchSnapshot.query == query,
                InstrumentSearchSnapshot.result_hash == result_hash,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = InstrumentSearchSnapshot(
            data_source_id=data_source_id,
            query=query,
            observed_at=observed_at,
            fetched_at=fetched_at,
            result_hash=result_hash,
            payload=payload,
        )
        db.add(snapshot)
        await db.flush()
        return snapshot

    snapshot.observed_at = observed_at
    snapshot.fetched_at = fetched_at
    snapshot.payload = payload
    return snapshot


async def store_universe_discovery_snapshot(
    db: AsyncSession,
    *,
    data_source_id: int,
    quote_type: str,
    offset: int,
    page: dict[str, Any],
    observed_at: datetime | None = None,
    fetched_at: datetime | None = None,
) -> UniverseDiscoverySnapshot:
    observed_at = observed_at or _now_utc()
    fetched_at = fetched_at or observed_at
    payload = {
        "quote_type": quote_type,
        "offset": offset,
        "page": page,
    }
    snapshot_hash = _payload_hash(payload)
    snapshot = (
        await db.execute(
            select(UniverseDiscoverySnapshot).where(
                UniverseDiscoverySnapshot.data_source_id == data_source_id,
                UniverseDiscoverySnapshot.quote_type == quote_type,
                UniverseDiscoverySnapshot.offset == offset,
                UniverseDiscoverySnapshot.snapshot_hash == snapshot_hash,
            )
        )
    ).scalar_one_or_none()
    if snapshot is None:
        snapshot = UniverseDiscoverySnapshot(
            data_source_id=data_source_id,
            quote_type=quote_type,
            offset=offset,
            observed_at=observed_at,
            fetched_at=fetched_at,
            snapshot_hash=snapshot_hash,
            payload=payload,
        )
        db.add(snapshot)
        await db.flush()
        return snapshot

    snapshot.observed_at = observed_at
    snapshot.fetched_at = fetched_at
    snapshot.payload = payload
    return snapshot
