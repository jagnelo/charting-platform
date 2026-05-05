from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentIdentifier
from app.models.provider_observation import (
    InstrumentIdentifierSnapshot,
    InstrumentProfileSnapshot,
    InstrumentSearchSnapshot,
    LatestPriceSnapshot,
    UniverseDiscoverySnapshot,
)
from app.models.provider_runtime import ProviderCapability, ProviderHealthState, ProviderPolicy
from app.providers.base import IdentifierRecord, InstrumentProfile, ProviderSearchResult
from app.services import instrument_mastering, instrument_sync, market_data
from app.services.provider_runtime import ProviderExecutionResult, ResolvedProvider
from tests.unit.conftest import AsyncSessionAdapter


def _resolved_provider(
    db,
    *,
    provider_name: str,
    capability: ProviderCapability,
    freshness_seconds: int = 300,
    provider: object | None = None,
) -> ResolvedProvider:
    data_source = DataSource(name=provider_name, is_active=True)
    db.add(data_source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=data_source.id,
        capability=capability,
        freshness_seconds=freshness_seconds,
        base_priority=10,
        tokens_per_minute=60,
        burst_capacity=15,
        max_concurrency=2,
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("90"),
    )
    health = ProviderHealthState(
        data_source_id=data_source.id,
        capability=capability,
        observed_score=Decimal("90"),
    )
    return ResolvedProvider(
        provider_name=provider_name,
        provider=provider,
        data_source=data_source,
        policy=policy,
        health=health,
    )


@pytest.mark.asyncio
async def test_latest_price_fetch_persists_and_then_reuses_cache(db, instrument, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    resolved = _resolved_provider(
        db, provider_name="yfinance", capability=ProviderCapability.LATEST_PRICE
    )
    execute_calls = 0

    async def _fake_resolve(*args, **kwargs):
        return [resolved]

    async def _fake_execute(*args, **kwargs):
        nonlocal execute_calls
        execute_calls += 1
        return ProviderExecutionResult(
            provider_name="yfinance",
            data_source=resolved.data_source,
            policy=resolved.policy,
            health=resolved.health,
            result=123.45,
        )

    monkeypatch.setattr(market_data, "resolve_provider_chain", _fake_resolve)
    monkeypatch.setattr(market_data, "execute_provider_call", _fake_execute)

    first = await market_data.get_current_price_async(async_db, instrument)
    second = await market_data.get_current_price_async(async_db, instrument)

    snapshots = db.execute(select(LatestPriceSnapshot)).scalars().all()
    assert first == pytest.approx(123.45)
    assert second == pytest.approx(123.45)
    assert execute_calls == 1
    assert len(snapshots) == 1
    assert float(snapshots[0].price) == pytest.approx(123.45)


@pytest.mark.asyncio
async def test_search_fetch_persists_and_then_reuses_cache(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    yfinance = _resolved_provider(
        db, provider_name="yfinance", capability=ProviderCapability.INSTRUMENT_SEARCH
    )
    coingecko = _resolved_provider(
        db, provider_name="coingecko", capability=ProviderCapability.INSTRUMENT_SEARCH
    )
    execute_calls: list[str] = []

    async def _fake_resolve(*args, **kwargs):
        return [yfinance, coingecko]

    async def _fake_execute(*args, provider_name=None, **kwargs):
        execute_calls.append(provider_name)
        if provider_name == "yfinance":
            results = [
                ProviderSearchResult(
                    symbol="NVDA", name="NVIDIA", exchange="NASDAQ", instrument_type="Stock"
                )
            ]
            resolved = yfinance
        else:
            results = [
                ProviderSearchResult(
                    symbol="NVDA-USD",
                    name="NVIDIA Tokenized",
                    exchange="CoinGecko",
                    instrument_type="CRYPTOCURRENCY",
                )
            ]
            resolved = coingecko
        return ProviderExecutionResult(
            provider_name=resolved.provider_name,
            data_source=resolved.data_source,
            policy=resolved.policy,
            health=resolved.health,
            result=results,
        )

    monkeypatch.setattr(market_data, "resolve_provider_chain", _fake_resolve)
    monkeypatch.setattr(market_data, "execute_provider_call", _fake_execute)

    first = await market_data.search_provider_instruments_async(async_db, "nvda")
    second = await market_data.search_provider_instruments_async(async_db, "nvda")

    snapshots = db.execute(select(InstrumentSearchSnapshot)).scalars().all()
    assert execute_calls == ["yfinance", "coingecko"]
    assert (
        first
        == second
        == [
            {
                "symbol": "NVDA",
                "name": "NVIDIA",
                "exchange": "NASDAQ",
                "type": "Stock",
                "provider": "yfinance",
            },
            {
                "symbol": "NVDA-USD",
                "name": "NVIDIA Tokenized",
                "exchange": "CoinGecko",
                "type": "CRYPTOCURRENCY",
                "provider": "coingecko",
            },
        ]
    )
    assert len(snapshots) == 2
    assert {snapshot.query for snapshot in snapshots} == {"nvda"}


@pytest.mark.asyncio
async def test_profile_fetch_persists_snapshot_and_then_reuses_cache(db, instrument, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    resolved = _resolved_provider(
        db, provider_name="yfinance", capability=ProviderCapability.INSTRUMENT_METADATA
    )
    execute_calls = 0

    async def _fake_resolve(*args, **kwargs):
        return [resolved]

    async def _fake_execute(*args, **kwargs):
        nonlocal execute_calls
        execute_calls += 1
        return ProviderExecutionResult(
            provider_name="yfinance",
            data_source=resolved.data_source,
            policy=resolved.policy,
            health=resolved.health,
            result=InstrumentProfile(
                provider="yfinance",
                symbol="AAPL",
                canonical_symbol="AAPL",
                name="Apple Updated",
                description="Updated profile",
                currency="USD",
                quote_type="EQUITY",
                exchange="NASDAQ",
                raw_payload={"longName": "Apple Updated", "currency": "USD", "quoteType": "EQUITY"},
            ),
        )

    monkeypatch.setattr(market_data, "resolve_provider_chain", _fake_resolve)
    monkeypatch.setattr(market_data, "execute_provider_call", _fake_execute)

    first = await market_data.get_provider_profile_async(
        async_db, "AAPL", instrument_id=instrument.id
    )
    second = await market_data.get_provider_profile_async(
        async_db, "AAPL", instrument_id=instrument.id
    )

    instrument_row = db.execute(
        select(Instrument).where(Instrument.id == instrument.id)
    ).scalar_one()
    snapshots = db.execute(select(InstrumentProfileSnapshot)).scalars().all()
    assert execute_calls == 1
    assert first is not None and second is not None
    assert first.name == "Apple Updated"
    assert second.name == "Apple Updated"
    assert instrument_row.name == "Apple Updated"
    assert len(snapshots) == 1


@pytest.mark.asyncio
async def test_profile_fetch_without_existing_instrument_persists_by_creating_one(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    resolved = _resolved_provider(
        db, provider_name="yfinance", capability=ProviderCapability.INSTRUMENT_METADATA
    )

    async def _fake_resolve(*args, **kwargs):
        return [resolved]

    async def _fake_execute(*args, **kwargs):
        return ProviderExecutionResult(
            provider_name="yfinance",
            data_source=resolved.data_source,
            policy=resolved.policy,
            health=resolved.health,
            result=InstrumentProfile(
                provider="yfinance",
                symbol="TSLA",
                canonical_symbol="TSLA",
                name="Tesla",
                description="Tesla profile",
                currency="USD",
                quote_type="EQUITY",
                exchange="NASDAQ",
                raw_payload={"longName": "Tesla", "currency": "USD", "quoteType": "EQUITY"},
            ),
        )

    monkeypatch.setattr(market_data, "resolve_provider_chain", _fake_resolve)
    monkeypatch.setattr(market_data, "execute_provider_call", _fake_execute)

    profile = await market_data.get_provider_profile_async(async_db, "TSLA")

    instrument_row = db.execute(select(Instrument).where(Instrument.symbol == "TSLA")).scalar_one()
    snapshots = db.execute(select(InstrumentProfileSnapshot)).scalars().all()
    assert profile is not None
    assert instrument_row.name == "Tesla"
    assert len(snapshots) == 1


@pytest.mark.asyncio
async def test_identifier_fetch_persists_snapshot_and_identifier(db, instrument, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    data_source = DataSource(name="openfigi", is_active=True)
    db.add(data_source)
    db.flush()

    async def _fake_execute(*args, **kwargs):
        return ProviderExecutionResult(
            provider_name="openfigi",
            data_source=data_source,
            policy=ProviderPolicy(
                data_source_id=data_source.id,
                capability=ProviderCapability.INSTRUMENT_IDENTIFIERS,
                base_priority=10,
                score_floor=Decimal("0"),
                score_ceiling=Decimal("100"),
                learned_weight=Decimal("0"),
                effective_score=Decimal("90"),
            ),
            health=ProviderHealthState(
                data_source_id=data_source.id,
                capability=ProviderCapability.INSTRUMENT_IDENTIFIERS,
                observed_score=Decimal("90"),
            ),
            result=[
                IdentifierRecord(
                    identifier_type="isin",
                    identifier_value="US0378331005",
                    is_primary=True,
                    source="openfigi",
                )
            ],
        )

    monkeypatch.setattr(instrument_mastering, "execute_provider_call", _fake_execute)

    changed = await instrument_mastering.ensure_external_identifier(async_db, instrument)

    identifier = db.execute(select(InstrumentIdentifier)).scalar_one()
    snapshot = db.execute(select(InstrumentIdentifierSnapshot)).scalar_one()
    assert changed is True
    assert identifier.identifier_value == "US0378331005"
    assert snapshot.provider_symbol == "AAPL"


@pytest.mark.asyncio
async def test_seed_universe_persists_discovery_snapshots(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)

    class _DiscoveryProvider:
        def __init__(self, quote_types):
            self._quote_types = quote_types

        def supported_discovery_types(self):
            return list(self._quote_types)

    yfinance = _resolved_provider(
        db,
        provider_name="yfinance",
        capability=ProviderCapability.UNIVERSE_DISCOVERY,
        provider=_DiscoveryProvider(["EQUITY"]),
    )
    coingecko = _resolved_provider(
        db,
        provider_name="coingecko",
        capability=ProviderCapability.UNIVERSE_DISCOVERY,
        provider=_DiscoveryProvider(["CRYPTOCURRENCY"]),
    )

    async def _fake_resolve(*args, **kwargs):
        return [yfinance, coingecko]

    async def _fake_execute(*args, provider_name=None, operation=None, **kwargs):
        if provider_name == "yfinance":
            resolved = yfinance
            symbol = "MSFT"
            quote_type = "EQUITY"
            name = "Microsoft"
        else:
            resolved = coingecko
            symbol = "BTC-USD"
            quote_type = "CRYPTOCURRENCY"
            name = "Bitcoin"
        return ProviderExecutionResult(
            provider_name=resolved.provider_name,
            data_source=resolved.data_source,
            policy=resolved.policy,
            health=resolved.health,
            result={
                "total": 1,
                "quotes": [
                    {
                        "symbol": symbol,
                        "longName": name,
                        "currency": "USD",
                        "exchange": "NASDAQ" if quote_type == "EQUITY" else "CoinGecko",
                    }
                ],
            },
        )

    monkeypatch.setattr(instrument_sync, "resolve_provider_chain", _fake_resolve)
    monkeypatch.setattr(instrument_sync, "execute_provider_call", _fake_execute)
    monkeypatch.setattr(instrument_sync.settings, "INSTRUMENT_DISCOVERY_PAGE_DELAY_SECONDS", 0)

    result = await instrument_sync.seed_universe(async_db)

    snapshots = db.execute(select(UniverseDiscoverySnapshot)).scalars().all()
    assert result["created"] == 2
    assert (
        db.execute(select(Instrument).where(Instrument.symbol == "MSFT")).scalar_one().name
        == "Microsoft"
    )
    assert (
        db.execute(select(Instrument).where(Instrument.symbol == "BTC-USD")).scalar_one().name
        == "Bitcoin"
    )
    assert len(snapshots) == 2
