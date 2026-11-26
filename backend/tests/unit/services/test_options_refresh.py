from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.asset_class import InstrumentType
from app.models.data_source import DataSource
from app.models.instrument import Instrument, OptionDetail, OptionRight, OptionStyle
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.providers.errors import ProviderRateLimitError
from app.services import options_refresh
from app.services.options_refresh import (
    deactivate_expired_option_contracts,
    refresh_options_data,
    select_active_option_contracts,
    select_option_underlyings,
)
from tests.unit.conftest import AsyncSessionAdapter

NOW = datetime(2026, 11, 26, 15, 0, tzinfo=UTC)
TODAY = NOW.date()


@pytest.fixture()
def option_type(db, asset_class):
    row = InstrumentType(name="Option", asset_class_id=asset_class.id)
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def source(db):
    row = DataSource(name="marketdata_app", is_active=True)
    db.add(row)
    db.flush()
    return row


def _underlying(db, instrument_type, symbol):
    row = Instrument(
        symbol=symbol,
        name=symbol,
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(row)
    db.flush()
    return row


def _contract(db, option_type, underlying, expiry: date, strike: int, active=True):
    inst = Instrument(
        symbol=f"{underlying.symbol}{expiry:%y%m%d}C{strike}",
        name="opt",
        currency="USD",
        instrument_type_id=option_type.id,
        is_active=active,
    )
    db.add(inst)
    db.flush()
    db.add(
        OptionDetail(
            instrument_id=inst.id,
            underlying_instrument_id=underlying.id,
            right=OptionRight.CALL,
            style=OptionStyle.AMERICAN,
            contract_key=f"{inst.symbol}-key",
            strike=Decimal(strike),
            expiry_date=expiry,
            contract_size=Decimal("100"),
        )
    )
    db.flush()
    return inst


def _state(db, source, inst, dataset_type, fetched_at, key="all"):
    db.add(
        InstrumentDatasetState(
            instrument_id=inst.id,
            data_source_id=source.id,
            dataset_type=dataset_type,
            dataset_key=key,
            status=DatasetStatus.FRESH,
            observed_at=fetched_at,
            fetched_at=fetched_at,
            stale_after=fetched_at + timedelta(hours=1),
        )
    )
    db.flush()


@pytest.mark.asyncio
async def test_contract_selection_excludes_expired_and_beyond_horizon(db, instrument, option_type):
    a = _contract(db, option_type, instrument, TODAY + timedelta(days=5), 100)
    _contract(db, option_type, instrument, TODAY - timedelta(days=1), 100)
    _contract(db, option_type, instrument, TODAY + timedelta(days=200), 100)
    _contract(db, option_type, instrument, TODAY + timedelta(days=3), 100, active=False)
    today_exp = _contract(db, option_type, instrument, TODAY, 101)
    got = await select_active_option_contracts(
        AsyncSessionAdapter(db), limit=50, now=NOW, horizon_days=45
    )
    assert {c.id for c in got} == {a.id, today_exp.id}


@pytest.mark.asyncio
async def test_contract_selection_is_bounded_stalest_first_and_skips_done_today(
    db, instrument, option_type, source
):
    c = [
        _contract(db, option_type, instrument, TODAY + timedelta(days=5), 100 + i) for i in range(4)
    ]
    _state(db, source, c[0], "option_quote_history", NOW - timedelta(hours=1), "default")
    _state(db, source, c[1], "option_quote_history", NOW - timedelta(days=3), "default")
    got = await select_active_option_contracts(
        AsyncSessionAdapter(db), limit=2, now=NOW, horizon_days=45
    )
    assert len(got) == 2
    assert {g.id for g in got} == {c[2].id, c[3].id}  # never-fetched first
    got = await select_active_option_contracts(
        AsyncSessionAdapter(db), limit=10, now=NOW, horizon_days=45
    )
    assert c[0].id not in {g.id for g in got}
    assert got[-1].id == c[1].id
    assert (
        await select_active_option_contracts(
            AsyncSessionAdapter(db), limit=0, now=NOW, horizon_days=45
        )
        == []
    )


@pytest.mark.asyncio
async def test_underlying_selection_scope_and_rotation(db, instrument_type, option_type, source):
    core = _underlying(db, instrument_type, "SPY")
    known = _underlying(db, instrument_type, "AAPL")
    _contract(db, option_type, known, TODAY + timedelta(days=5), 100)
    _underlying(db, instrument_type, "ZZZZ")  # not core, not watched, no contracts
    done = _underlying(db, instrument_type, "QQQ")
    _state(db, source, done, "option_expirations", NOW - timedelta(hours=2))
    got = await select_option_underlyings(
        AsyncSessionAdapter(db), limit=10, now=NOW, core_symbols={"SPY", "QQQ"}
    )
    assert [g.id for g in got] == sorted([core.id, known.id])
    got = await select_option_underlyings(
        AsyncSessionAdapter(db), limit=1, now=NOW, core_symbols={"SPY", "QQQ"}
    )
    assert len(got) == 1


@pytest.mark.asyncio
async def test_expired_contracts_are_deactivated(db, instrument, option_type):
    old = _contract(db, option_type, instrument, TODAY - timedelta(days=1), 100)
    live = _contract(db, option_type, instrument, TODAY, 100)
    n = await deactivate_expired_option_contracts(AsyncSessionAdapter(db), today=TODAY)
    db.expire_all()
    assert n == 1
    assert db.get(Instrument, old.id).is_active is False
    assert db.get(Instrument, live.id).is_active is True


def _patch(monkeypatch, calls):
    async def exps(_db, u, refresh=False):
        calls["exp"].append(u.symbol)
        return [
            TODAY - timedelta(days=2),
            TODAY + timedelta(days=7),
            TODAY + timedelta(days=14),
            TODAY + timedelta(days=400),
        ]

    async def chain(_db, u, *, expiration, refresh=False):
        calls["chain"].append((u.symbol, expiration))
        return object()

    async def hist(_db, c, *, start, end, refresh=False):
        calls["hist"].append(c.id)

    monkeypatch.setattr(options_refresh, "list_option_expirations", exps)
    monkeypatch.setattr(options_refresh, "sync_option_chain_snapshot", chain)
    monkeypatch.setattr(options_refresh, "sync_option_quote_history", hist)


@pytest.mark.asyncio
async def test_run_respects_volume_caps_and_active_window(
    db, instrument_type, option_type, monkeypatch
):
    calls = {"exp": [], "chain": [], "hist": []}
    _patch(monkeypatch, calls)
    for s in ("SPY", "QQQ", "IWM", "DIA"):
        _underlying(db, instrument_type, s)
    base = _underlying(db, instrument_type, "AAPL")
    for i in range(6):
        _contract(db, option_type, base, TODAY + timedelta(days=5), 100 + i)
    result = await refresh_options_data(
        AsyncSessionAdapter(db),
        now=NOW,
        max_underlyings=2,
        expirations_per_underlying=1,
        max_contracts=3,
        core_symbols={"SPY", "QQQ", "IWM", "DIA"},
    )
    assert len(calls["exp"]) == 2
    assert len(calls["chain"]) == 2
    assert all(e == TODAY + timedelta(days=7) for _s, e in calls["chain"])
    assert len(calls["hist"]) == 3
    assert result["underlyings_refreshed"] == 2 and result["contracts_refreshed"] == 3


@pytest.mark.asyncio
async def test_rerun_same_day_does_not_multiply_provider_calls(
    db, instrument_type, option_type, source, monkeypatch
):
    """Provider helpers record dataset state; a second run in the day is a no-op."""
    calls = {"exp": [], "chain": [], "hist": []}
    _patch(monkeypatch, calls)
    u = _underlying(db, instrument_type, "SPY")
    c = _contract(db, option_type, u, TODAY + timedelta(days=5), 100)

    async def exps(_db, under, refresh=False):
        calls["exp"].append(under.symbol)
        _state(db, source, under, "option_expirations", datetime.now(UTC) if False else NOW)
        return []

    async def hist(_db, contract, *, start, end, refresh=False):
        calls["hist"].append(contract.id)
        _state(db, source, contract, "option_quote_history", NOW, "default")

    monkeypatch.setattr(options_refresh, "list_option_expirations", exps)
    monkeypatch.setattr(options_refresh, "sync_option_quote_history", hist)
    kwargs = dict(now=NOW, max_underlyings=5, max_contracts=5, core_symbols={"SPY"})
    await refresh_options_data(AsyncSessionAdapter(db), **kwargs)
    await refresh_options_data(AsyncSessionAdapter(db), **kwargs)
    assert calls["exp"] == ["SPY"]
    assert calls["hist"] == [c.id]


@pytest.mark.asyncio
async def test_daily_cap_counts_work_already_done_today(db, instrument_type, source, monkeypatch):
    calls = {"exp": [], "chain": [], "hist": []}
    _patch(monkeypatch, calls)
    done = _underlying(db, instrument_type, "SPY")
    _underlying(db, instrument_type, "QQQ")
    _state(db, source, done, "option_expirations", NOW - timedelta(hours=1))
    result = await refresh_options_data(
        AsyncSessionAdapter(db),
        now=NOW,
        max_underlyings=1,
        max_contracts=0,
        core_symbols={"SPY", "QQQ"},
    )
    assert calls["exp"] == [] and result["underlyings_selected"] == 0


@pytest.mark.asyncio
async def test_quota_signal_stops_the_run(db, instrument_type, option_type, monkeypatch):
    calls = {"exp": [], "chain": [], "hist": []}
    _patch(monkeypatch, calls)

    async def exhausted(_db, u, refresh=False):
        calls["exp"].append(u.symbol)
        raise ProviderRateLimitError("marketdata_app", "daily credits exhausted")

    monkeypatch.setattr(options_refresh, "list_option_expirations", exhausted)
    for s in ("SPY", "QQQ"):
        u = _underlying(db, instrument_type, s)
    _contract(db, option_type, u, TODAY + timedelta(days=5), 100)
    result = await refresh_options_data(
        AsyncSessionAdapter(db),
        now=NOW,
        max_underlyings=5,
        max_contracts=5,
        core_symbols={"SPY", "QQQ"},
    )
    assert len(calls["exp"]) == 1
    assert result["stopped"] == "quota" and calls["hist"] == []
