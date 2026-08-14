from __future__ import annotations

import asyncio

from sqlalchemy import select

import app.services.workstation_bootstrap as bootstrap
from app.config import settings
from app.models.data_source import DataSource
from app.models.etf_holdings import ETFProfile
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.workstation import MarketGroup, MarketGroupMember
from app.services.workstation_bootstrap import (
    CORE_WORKSTATION_INSTRUMENTS,
    CORE_WORKSTATION_REGISTRY,
    ensure_core_workstation_identities,
)


class _AsyncSessionFacade:
    def __init__(self, session):
        self.session = session

    async def execute(self, statement):
        return self.session.execute(statement)

    async def get(self, *args, **kwargs):
        return self.session.get(*args, **kwargs)

    async def rollback(self):
        self.session.rollback()

    async def commit(self):
        self.session.commit()

    async def flush(self):
        self.session.flush()

    def add(self, value):
        self.session.add(value)


def test_core_workstation_identity_bootstrap_is_idempotent_and_not_fixture_data(db):
    facade = _AsyncSessionFacade(db)

    first = asyncio.run(ensure_core_workstation_identities(facade))
    second = asyncio.run(ensure_core_workstation_identities(facade))

    symbols = {row.symbol for row in db.execute(select(Instrument)).scalars()}
    expected = {symbol for symbol, _, _ in CORE_WORKSTATION_INSTRUMENTS}
    assert symbols == expected
    assert first["created"] == len(expected)
    assert second["created"] == 0
    assert first["data_status"] == "identity_only_until_provider_history_and_holdings_load"

    bindings = db.execute(select(InstrumentProviderSymbol)).scalars().all()
    assert len(bindings) == len(expected)
    assert {binding.extra_data["identity_bootstrap"] for binding in bindings} == {
        CORE_WORKSTATION_REGISTRY
    }
    assert {binding.extra_data["exchange_claim"] for binding in bindings} == {"not asserted"}

    profiles = db.execute(select(ETFProfile)).scalars().all()
    assert len(profiles) == len(expected) - 1  # NVDA is the only equity in the registry.
    assert all(
        profile.legal_metadata["holdings_membership_status"] == "not_loaded" for profile in profiles
    )

    groups = db.execute(select(MarketGroup)).scalars().all()
    members = db.execute(select(MarketGroupMember)).scalars().all()
    assert {group.stable_key for group in groups} == {"us-benchmarks", "sp500-sectors"}
    assert len(members) == 5 + 11


def test_core_workstation_bootstrap_tolerates_venue_distinct_provider_symbols(db):
    facade = _AsyncSessionFacade(db)
    ensure_core_workstation_identities_result = asyncio.run(
        ensure_core_workstation_identities(facade)
    )
    assert ensure_core_workstation_identities_result["created"] == len(CORE_WORKSTATION_INSTRUMENTS)

    spy = db.execute(select(Instrument).where(Instrument.symbol == "SPY")).scalar_one()
    nasdaq = db.execute(select(DataSource).where(DataSource.name == "nasdaq")).scalar_one()
    db.add(
        InstrumentProviderSymbol(
            instrument_id=spy.id,
            data_source_id=nasdaq.id,
            provider_symbol="SPY",
            provider_exchange_code="XNYS",
            is_primary=False,
            extra_data={"legacy_duplicate": True},
        )
    )
    db.flush()

    rerun = asyncio.run(ensure_core_workstation_identities(facade))
    assert rerun["created"] == 0
    rows = (
        db.execute(
            select(InstrumentProviderSymbol).where(
                InstrumentProviderSymbol.instrument_id == spy.id,
                InstrumentProviderSymbol.data_source_id == nasdaq.id,
                InstrumentProviderSymbol.provider_symbol == "SPY",
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2


def test_core_workstation_data_reloads_instrument_after_provider_rollback(db, monkeypatch):
    """A failed provider attempt must not leave an expired ORM identity for the next symbol."""
    facade = _AsyncSessionFacade(db)
    asyncio.run(ensure_core_workstation_identities(facade))
    monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", False)
    monkeypatch.setattr(settings, "CORE_WORKSTATION_BOOTSTRAP_TIMEOUT_SECONDS", 1)

    calls = []

    async def fail_first_fetch(session, instrument, timeframe, start):
        calls.append(instrument.symbol)
        if len(calls) == 1:
            raise RuntimeError("provider unavailable")
        return []

    monkeypatch.setattr(bootstrap, "fetch_ohlcv", fail_first_fetch)
    monkeypatch.setattr(
        bootstrap,
        "bootstrap_etf_holdings_profile",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("holdings unavailable")),
    )

    result = asyncio.run(bootstrap.bootstrap_core_workstation_data(facade))
    assert set(result["history"]) == {symbol for symbol, _, _ in CORE_WORKSTATION_INSTRUMENTS}
    assert calls == [CORE_WORKSTATION_INSTRUMENTS[0][0]], result
    assert result["history"][CORE_WORKSTATION_INSTRUMENTS[1][0]]["status"] in {
        "ready",
        "loaded",
        "unavailable",
        "error",
    }
    assert result["history"][calls[0]]["status"] == "error"
