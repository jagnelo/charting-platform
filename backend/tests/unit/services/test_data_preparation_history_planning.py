from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import MarketSeries, MarketSeriesDefault
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderPolicy,
    ProviderRequestLog,
)
from app.services.provider_runtime import seed_provider_runtime
from app.tasks import data_tasks
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_history_planner_pins_deepest_admitted_provider_for_all_chunks(monkeypatch):
    end = datetime(2026, 11, 6, tzinfo=UTC)
    massive = SimpleNamespace(
        provider_name="massive",
        entitlement=SimpleNamespace(
            quota_policy={"history_constraints": {"max_lookback_years": 2}}
        ),
    )
    alpaca = SimpleNamespace(
        provider_name="alpaca",
        entitlement=SimpleNamespace(
            quota_policy={"history_constraints": {"max_lookback_years": 10}}
        ),
    )
    calls = {}

    async def fake_resolve(_db, capability, **kwargs):
        calls.update(kwargs)
        assert capability.value == "price_history"
        return [massive, alpaca]

    def fake_bound(constraints, *, now):
        return now.replace(year=now.year - constraints["max_lookback_years"]), None

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_resolve)
    monkeypatch.setattr("app.services.provider_runtime.provider_history_bound_start", fake_bound)

    instrument = SimpleNamespace(id=41, symbol="TEST")
    earliest, provider_name, reason = await data_tasks._deepest_admitted_history_start(
        object(),
        instrument,
        Timeframe.D1,
        adjusted=True,
        end=end,
        request_id="unit-history-plan",
    )

    assert reason is None
    assert provider_name == "alpaca"
    assert earliest == end.replace(year=2016)
    assert calls["provider_symbol"] == "TEST"
    assert calls["read_only"] is True
    assert calls["operation"] == "fetch_ohlcv:D1"

    # The first request is still recent-first and bounded, while its durable
    # continuation must retain the same deeper provider identity.
    preparation = {"range_mode": "deepest_admitted", "adjusted": True}
    monkeypatch.setattr(
        data_tasks,
        "_deepest_admitted_history_start",
        lambda *_args, **_kwargs: _async_value((earliest, "alpaca", None)),
    )
    job = SimpleNamespace(id=90, start_at=None, end_at=end)
    (
        chunk_start,
        chunk_end,
        full_start,
        full_end,
        selected_provider,
        plan_reason,
    ) = await data_tasks._history_chunk_plan(object(), job, instrument, Timeframe.D1, preparation)
    assert plan_reason is None
    assert selected_provider == "alpaca"
    assert preparation["source_provider"] == "alpaca"
    assert full_start == earliest
    assert full_end == end
    assert chunk_end == end
    assert chunk_start > full_start
    assert (chunk_end - chunk_start).days <= 2000


@pytest.mark.asyncio
async def test_history_planner_uses_deeper_real_admission_chain_over_recent_massive_cache(
    db, instrument, monkeypatch
):
    """Recent Massive bars do not hide a deeper currently admitted provider."""
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "MASSIVE_API_KEY", "test-massive-key")
    monkeypatch.setattr(settings, "ALPACA_API_KEY", "test-alpaca-key")
    monkeypatch.setattr(settings, "ALPACA_SECRET_KEY", "test-alpaca-secret")
    monkeypatch.setattr(settings, "ALPACA_DATA_FEED", "iex")

    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)

    exchange = Exchange(
        mic="XNAS",
        name="Nasdaq",
        country_code="US",
        timezone="America/New_York",
        currency="USD",
    )
    db.add(exchange)
    db.flush()
    db.add(
        InstrumentListing(
            instrument_id=instrument.id,
            exchange_id=exchange.id,
            ticker=instrument.symbol,
            currency="USD",
            is_primary=True,
            is_active=True,
            source="unit-test-reviewed-listing",
            provenance={"test_fixture": True},
        )
    )
    db.flush()

    providers = {"massive", "alpaca"}
    sources = {
        row.name: row for row in db.execute(select(DataSource)).scalars() if row.name in providers
    }
    assert set(sources) == providers
    policy_rows = db.execute(
        select(ProviderPolicy, DataSource)
        .join(DataSource, DataSource.id == ProviderPolicy.data_source_id)
        .where(ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY)
    ).all()
    for policy, source in policy_rows:
        policy.is_enabled = source.name in providers

    start_bounds = {"massive": {"max_lookback_years": 2}, "alpaca": {"earliest_date": "2016-01-01"}}
    for provider_name, source in sources.items():
        entitlement = db.execute(
            select(ProviderEntitlement).where(
                ProviderEntitlement.data_source_id == source.id,
                ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
            )
        ).scalar_one()
        entitlement.is_free = True
        entitlement.authentication_required = True
        entitlement.configured_plan = "reviewed-free-test"
        entitlement.live_probe_status = "passed"
        entitlement.enabled_environments = [settings.APP_ENV]
        entitlement.effective_at = datetime(2026, 1, 1, tzinfo=UTC)
        entitlement.review_due_at = datetime(2027, 1, 1, tzinfo=UTC)
        entitlement.quota_policy = {
            **(entitlement.quota_policy or {}),
            "history_constraints": start_bounds[provider_name],
        }

    # Model the normal visible read having already cached recent data in the
    # Massive series. The planner must still inspect the real eligible route
    # and bind the deeper request to one coherent alternate series.
    massive_series = MarketSeries(
        instrument_id=instrument.id,
        data_source_id=sources["massive"].id,
        feed_scope="consolidated",
        session_code="regular",
        timeframe=Timeframe.D1.value,
        adjustment_basis="split_adjusted",
        adjustment_version="massive-split-adjusted",
        is_canonical=True,
        is_active=True,
    )
    db.add(massive_series)
    db.flush()
    db.add(
        MarketSeriesDefault(
            instrument_id=instrument.id,
            timeframe=Timeframe.D1.value,
            is_adjusted=True,
            market_series_id=massive_series.id,
            selection_reason="first_canonical",
        )
    )
    db.add(
        OHLCVBar(
            instrument_id=instrument.id,
            data_source_id=sources["massive"].id,
            market_series_id=massive_series.id,
            timeframe=Timeframe.D1,
            ts=datetime(2026, 11, 5, 20, tzinfo=UTC),
            open=100,
            high=102,
            low=99,
            close=101,
            volume=1000,
            is_adjusted=True,
            adjustment_basis="split_adjusted",
            adjustment_version="massive-split-adjusted",
            session="regular",
            scope_key=f"series:{massive_series.id}:regular",
        )
    )
    db.flush()

    end = datetime(2026, 11, 6, tzinfo=UTC)
    (
        chunk_start,
        chunk_end,
        earliest,
        _full_end,
        provider_name,
        reason,
    ) = await data_tasks._history_chunk_plan(
        async_db,
        SimpleNamespace(id=300, start_at=None, end_at=end),
        instrument,
        Timeframe.D1,
        {"range_mode": "deepest_admitted", "adjusted": True},
    )

    assert reason is None
    assert provider_name == "alpaca"
    assert earliest == datetime(2016, 1, 1, tzinfo=UTC)
    assert chunk_start is not None and chunk_end == end
    assert (chunk_end - chunk_start).days <= settings.PROVIDER_ON_DEMAND_MAX_REQUESTED_BARS
    assert (
        db.execute(select(MarketSeriesDefault)).scalar_one().market_series_id == massive_series.id
    )
    assert len(db.execute(select(OHLCVBar)).scalars().all()) == 1
    assert db.execute(select(ProviderRequestLog)).scalars().all() == []

    # A deeper provider with an unknown native baseline is not usable merely
    # because its policy/entitlement resolver row exists. If its normal
    # account-usage bootstrap is unavailable, the first unpinned chunk should
    # use a shallower provider whose exact native baseline is already known.
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED", False)
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS", [])

    async def baseline_states(_db, provider_name, **_kwargs):
        status = "unknown" if provider_name == "alpaca" else "verified"
        return (None, [({"name": "requests_per_minute"}, {"status": status})]), None

    monkeypatch.setattr(data_tasks, "_native_operation_baseline_states", baseline_states)
    (
        fallback_plan,
        fallback_preparation,
        usage_job,
        usage_hold,
        terminal_native_hold,
    ) = await data_tasks._history_chunk_plan_with_native_admission(
        async_db,
        SimpleNamespace(id=301, start_at=None, end_at=end),
        instrument,
        Timeframe.D1,
        {"range_mode": "deepest_admitted", "adjusted": True},
        priority=10,
    )
    assert fallback_plan[5] is None
    assert fallback_plan[4] == "massive"
    assert fallback_plan[2] == datetime(2024, 11, 6, tzinfo=UTC)
    assert fallback_preparation["source_provider"] == "massive"
    assert usage_job is None
    assert usage_hold is None
    assert terminal_native_hold is None
    assert db.execute(select(ProviderRequestLog)).scalars().all() == []

    # Once a chunk has pinned a source, keep its native hold rather than
    # switching the continuation into a different feed/series lineage.
    (
        pinned_plan,
        _pinned_preparation,
        pinned_usage_job,
        pinned_usage_hold,
        pinned_terminal_hold,
    ) = await data_tasks._history_chunk_plan_with_native_admission(
        async_db,
        SimpleNamespace(
            id=302,
            start_at=datetime(2016, 1, 1, tzinfo=UTC),
            end_at=end,
        ),
        instrument,
        Timeframe.D1,
        {
            "range_mode": "deepest_admitted",
            "adjusted": True,
            "chunk": True,
            "range_start": datetime(2016, 1, 1, tzinfo=UTC).isoformat(),
            "range_end": end.isoformat(),
            "source_provider": "alpaca",
        },
        priority=10,
    )
    assert pinned_plan[4] == "alpaca"
    assert pinned_plan[5] is None
    assert pinned_usage_job is None
    assert pinned_usage_hold == "native_usage_refresh_not_enabled_for_provider"
    assert pinned_terminal_hold is None

    # If no shallower resolver candidate exists, preserve the genuine native
    # hold instead of replacing it with a generic no-provider result.
    for policy, source in policy_rows:
        if source.name == "massive":
            policy.is_enabled = False
    db.flush()
    (
        _empty_plan,
        _empty_preparation,
        empty_usage_job,
        empty_usage_hold,
        terminal_native_hold,
    ) = await data_tasks._history_chunk_plan_with_native_admission(
        async_db,
        SimpleNamespace(id=303, start_at=None, end_at=end),
        instrument,
        Timeframe.D1,
        {"range_mode": "deepest_admitted", "adjusted": True},
        priority=10,
    )
    assert empty_usage_job is None
    assert empty_usage_hold is None
    assert terminal_native_hold == "native_usage_refresh_not_enabled_for_provider"
    assert db.execute(select(ProviderRequestLog)).scalars().all() == []


def test_older_automatic_chunks_yield_to_background_after_analysis_window():
    useful_start = datetime(2024, 1, 1, tzinfo=UTC)
    assert (
        data_tasks._older_chunk_priority(
            current_priority=10,
            range_mode="deepest_admitted",
            useful_start=useful_start,
            older_chunk_end=datetime(2024, 6, 1, tzinfo=UTC),
        )
        == 10
    )
    assert (
        data_tasks._older_chunk_priority(
            current_priority=10,
            range_mode="deepest_admitted",
            useful_start=useful_start,
            older_chunk_end=datetime(2023, 12, 31, tzinfo=UTC),
        )
        == 100
    )
    assert (
        data_tasks._older_chunk_priority(
            current_priority=10,
            range_mode="deepest_admitted",
            useful_start=None,
            older_chunk_end=datetime(2026, 1, 1, tzinfo=UTC),
        )
        == 100
    )
    assert (
        data_tasks._older_chunk_priority(
            current_priority=10,
            range_mode="bounded",
            useful_start=None,
            older_chunk_end=datetime(2010, 1, 1, tzinfo=UTC),
        )
        == 10
    )


@pytest.mark.asyncio
async def test_history_plan_reports_analysis_window_beyond_admitted_depth(monkeypatch):
    end = datetime(2026, 11, 6, tzinfo=UTC)
    admitted_start = datetime(2024, 11, 6, tzinfo=UTC)
    preparation = {
        "range_mode": "deepest_admitted",
        "adjusted": True,
        "analysis_required_start": datetime(2022, 9, 1, tzinfo=UTC).isoformat(),
    }
    monkeypatch.setattr(
        data_tasks,
        "_deepest_admitted_history_start",
        lambda *_args, **_kwargs: _async_value((admitted_start, "massive", None)),
    )
    (
        chunk_start,
        _chunk_end,
        full_start,
        _full_end,
        _provider,
        reason,
    ) = await data_tasks._history_chunk_plan(
        object(),
        SimpleNamespace(id=91, start_at=None, end_at=end),
        SimpleNamespace(id=42, symbol="TEST"),
        Timeframe.D1,
        preparation,
    )
    assert reason is None
    assert full_start == admitted_start
    assert chunk_start == admitted_start
    assert preparation["analysis_requirement_unmet"] is True


async def _async_value(value):
    return value
