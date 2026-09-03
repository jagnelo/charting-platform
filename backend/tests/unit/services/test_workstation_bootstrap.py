from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from sqlalchemy import select

import app.services.workstation_bootstrap as bootstrap
from app.config import settings
from app.models.data_source import DataSource
from app.models.etf_holdings import ETFHoldingsSnapshot, ETFProfile
from app.models.instrument import Instrument
from app.models.instrument_identity import InstrumentProviderSymbol
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.workstation import MarketGroup, MarketGroupMember
from app.services.top_down_taxonomy import (
    BENCHMARK_FAMILY_REGISTRY,
    benchmark_family_proxy_symbols,
)
from app.services.workstation_bootstrap import (
    CORE_WORKSTATION_INSTRUMENTS,
    CORE_WORKSTATION_REGISTRY,
    MIN_CORE_D1_BARS,
    ensure_core_workstation_identities,
    queue_core_family_member_history,
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
    profiles_by_symbol = {
        profile.instrument.symbol: profile
        for profile in profiles
        if profile.instrument is not None
    }
    assert profiles_by_symbol["SPY"].adapter_key == "spdr"
    assert profiles_by_symbol["RSP"].adapter_key == "invesco"
    assert profiles_by_symbol["QQQE"].adapter_key == "direxion"
    assert profiles_by_symbol["IWB"].adapter_key == "ishares"
    assert profiles_by_symbol["SPY"].provider_aliases["holdings_adapter"] == "spdr"

    groups = db.execute(select(MarketGroup)).scalars().all()
    members = db.execute(select(MarketGroupMember)).scalars().all()
    assert {group.stable_key for group in groups} == {
        "us-benchmarks",
        "sp500-sectors",
        *(family["logical_key"] for family in BENCHMARK_FAMILY_REGISTRY),
    }
    expected_proxy_members = sum(
        sum(
            1
            for role in ("cap_weight", "equal_weight", "value", "growth")
            if family[role]["symbol"]
        )
        for family in BENCHMARK_FAMILY_REGISTRY
    )
    assert len(members) == 5 + 11 + expected_proxy_members


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


def test_core_bootstrap_retries_when_history_exists_but_is_below_technical_readiness(
    db, monkeypatch
):
    """A partial local history must not suppress the provider backfill retry."""

    facade = _AsyncSessionFacade(db)
    asyncio.run(ensure_core_workstation_identities(facade))
    monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", False)
    monkeypatch.setattr(settings, "CORE_WORKSTATION_BOOTSTRAP_TIMEOUT_SECONDS", 1)

    spy = db.execute(select(Instrument).where(Instrument.symbol == "SPY")).scalar_one()
    db.add(
        OHLCVBar(
            instrument_id=spy.id,
            timeframe=Timeframe.D1,
            ts=datetime(2026, 1, 2, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100"),
            is_adjusted=True,
        )
    )
    db.flush()
    calls: list[str] = []

    async def fake_fetch(_session, instrument, _timeframe, _start):
        calls.append(instrument.symbol)
        return []

    monkeypatch.setattr(bootstrap, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(
        bootstrap,
        "bootstrap_etf_holdings_profile",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("holdings unavailable")),
    )

    result = asyncio.run(bootstrap.bootstrap_core_workstation_data(facade))

    assert calls[0] == "SPY"
    assert result["history"]["SPY"]["status"] == "unavailable"
    assert MIN_CORE_D1_BARS == 252


def test_core_bootstrap_retries_partial_holdings_snapshot(db, monkeypatch):
    """Unknown/partial holdings are coverage evidence, not a successful retry gate."""

    facade = _AsyncSessionFacade(db)
    asyncio.run(ensure_core_workstation_identities(facade))
    monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", False)
    monkeypatch.setattr(settings, "CORE_WORKSTATION_BOOTSTRAP_TIMEOUT_SECONDS", 1)

    spy = db.execute(select(Instrument).where(Instrument.symbol == "SPY")).scalar_one()
    profile = db.execute(select(ETFProfile).where(ETFProfile.instrument_id == spy.id)).scalar_one()
    db.add(
        ETFHoldingsSnapshot(
            etf_profile_id=profile.id,
            composition_date=datetime(2026, 1, 2, tzinfo=UTC).date(),
            known_at=datetime(2026, 1, 3, tzinfo=UTC),
            provenance="issuer_public",
            source_provider="test-provider",
            source_quality="issuer",
            completeness_status="partial",
            row_count=1,
            resolved_count=1,
            unresolved_count=0,
            snapshot_hash="partial-spy-snapshot",
        )
    )
    db.flush()
    holdings_calls: list[str] = []

    async def fake_fetch(_session, _instrument, _timeframe, _start):
        return []

    async def fake_holdings(_session, *, symbol, name):
        holdings_calls.append(symbol)
        raise RuntimeError("holdings unavailable")

    monkeypatch.setattr(bootstrap, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(bootstrap, "bootstrap_etf_holdings_profile", fake_holdings)

    result = asyncio.run(bootstrap.bootstrap_core_workstation_data(facade))

    assert "SPY" in holdings_calls
    assert result["holdings"]["SPY"]["status"] == "error"


def test_core_bootstrap_attempts_every_configured_family_proxy_role(db, monkeypatch):
    """The provider bootstrap must not omit a configured family leg."""

    facade = _AsyncSessionFacade(db)
    asyncio.run(ensure_core_workstation_identities(facade))
    monkeypatch.setattr(settings, "E2E_SEED_MARKET_DATA", False)
    monkeypatch.setattr(settings, "CORE_WORKSTATION_BOOTSTRAP_TIMEOUT_SECONDS", 1)

    history_calls: list[str] = []
    holdings_calls: list[str] = []

    async def fake_fetch(_session, instrument, _timeframe, _start):
        history_calls.append(instrument.symbol)
        return []

    async def fake_holdings(_session, *, symbol, name):
        holdings_calls.append(symbol)
        return SimpleNamespace(
            refresh_succeeded=False,
            refresh_attempted=True,
            message="controlled provider test",
        )

    monkeypatch.setattr(bootstrap, "fetch_ohlcv", fake_fetch)
    monkeypatch.setattr(bootstrap, "bootstrap_etf_holdings_profile", fake_holdings)

    result = asyncio.run(bootstrap.bootstrap_core_workstation_data(facade))

    family_symbols = set(benchmark_family_proxy_symbols())
    assert family_symbols <= set(holdings_calls)
    assert family_symbols <= set(result["holdings"])
    assert set(history_calls) == {symbol for symbol, _, _ in CORE_WORKSTATION_INSTRUMENTS}


def test_core_bootstrap_queues_deduplicated_family_member_history(monkeypatch):
    plan = {
        "instrument_ids": [10, 20],
        "timeframes": ["MN", "W1", "D1"],
        "available_instrument_count": 2,
        "selected_instrument_count": 2,
        "limited": False,
        "legs": [{"source_id": "benchmark-family:sp500:cap_weight", "status": "ready"}],
    }

    async def fake_plan(*_args, **_kwargs):
        return plan

    monkeypatch.setattr(
        "app.services.benchmark_family_history.plan_benchmark_family_history_refresh",
        fake_plan,
    )

    class FakeRedis:
        def __init__(self):
            self.calls = []

        async def enqueue_job(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return object()

    redis = FakeRedis()
    result = asyncio.run(queue_core_family_member_history(object(), redis))

    assert result["status"] == "queued"
    assert result["queued"] == 2
    assert result["already_queued"] == 0
    assert len(redis.calls) == 2
    assert redis.calls[0][0] == ("task_bulk_fetch_instrument", 10, ["MN", "W1", "D1"])
    assert redis.calls[0][1]["_job_id"] == "watchlist-source-history:10:MN,W1,D1"
