import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

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
        "identifiers": [],
    }
    for item in identifiers:
        serialized = {
            "identifier_type": item.identifier_type,
            "identifier_value": item.identifier_value,
            "is_primary": item.is_primary,
            "source": item.source,
            "extra_data": item.extra_data,
        }
        if item.raw_payload is not None:
            serialized["raw_payload"] = item.raw_payload
        payload["identifiers"].append(serialized)
    snapshot_hash = _payload_hash(payload)
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


async def store_latest_price_snapshot(
    db: AsyncSession,
    *,
    instrument_id: int,
    data_source_id: int,
    provider_symbol: str | None,
    price: float | Decimal,
    payload: dict[str, Any] | list[Any] | str | None = None,
    payloads: Sequence[Any] | None = None,
    observed_at: datetime | None = None,
    fetched_at: datetime | None = None,
) -> LatestPriceSnapshot:
    observed_at = observed_at or _now_utc()
    fetched_at = fetched_at or observed_at
    decimal_price = price if isinstance(price, Decimal) else Decimal(str(price))
    provider_payload: dict[str, Any] = {}
    if payloads:
        # A provider operation may issue more than one HTTP request. Keep the
        # complete ordered set so quota-limited responses are never silently
        # discarded; retain the historical singular key for one response.
        provider_payload["provider_responses"] = list(payloads)
        if len(payloads) == 1:
            provider_payload["provider_response"] = payloads[0]
    elif payload is not None:
        provider_payload["provider_response"] = payload

    snapshot = LatestPriceSnapshot(
        instrument_id=instrument_id,
        data_source_id=data_source_id,
        provider_symbol=provider_symbol,
        observed_at=observed_at,
        fetched_at=fetched_at,
        price=decimal_price,
        payload={
            "price": float(decimal_price),
            **provider_payload,
        },
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
    serialized_results = []
    for item in results:
        serialized = {
            "symbol": item.symbol,
            "name": item.name,
            "exchange": item.exchange,
            "instrument_type": item.instrument_type,
        }
        if item.raw_payload is not None:
            serialized["raw_payload"] = item.raw_payload
        serialized_results.append(serialized)
    payload = {
        "query": query,
        "results": serialized_results,
    }
    result_hash = _payload_hash(payload)
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
