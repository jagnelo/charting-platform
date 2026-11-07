from datetime import UTC, datetime, timedelta
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
from app.providers.errors import ProviderRateLimitError
from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError
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
async def test_initial_job_resumed_after_native_usage_keeps_its_selected_provider(monkeypatch):
    end = datetime(2026, 11, 6, tzinfo=UTC)
    selected_start = datetime(2018, 1, 1, tzinfo=UTC)
    observed = {}

    async def selected_provider_bound(
        _db,
        _instrument,
        _timeframe,
        *,
        adjusted,
        end,
        request_id,
        priority,
        requested_start,
        preparation,
        excluded_provider_names,
        required_provider_name,
    ):
        observed["required_provider_name"] = required_provider_name
        observed["excluded_provider_names"] = excluded_provider_names
        assert adjusted is True
        return selected_start, "second-free", None

    monkeypatch.setattr(data_tasks, "_deepest_admitted_history_start", selected_provider_bound)
    preparation = {
        "range_mode": "deepest_admitted",
        "adjusted": True,
        # This is persisted when a native-usage prerequisite is queued.
        "source_provider": "second-free",
        "wait_for_job_ids": [801],
    }
    plan = await data_tasks._history_chunk_plan(
        object(),
        SimpleNamespace(id=802, start_at=None, end_at=end),
        SimpleNamespace(id=71, symbol="TEST"),
        Timeframe.D1,
        preparation,
    )

    assert plan[5] is None
    assert plan[4] == "second-free"
    assert plan[2] == selected_start
    assert preparation["source_provider"] == "second-free"
    assert observed == {
        "required_provider_name": "second-free",
        "excluded_provider_names": frozenset(),
    }


@pytest.mark.parametrize("unknown_provider", ["twelve_data", "fmp"])
@pytest.mark.asyncio
async def test_bounded_older_range_uses_source_without_advertised_floor(
    monkeypatch, unknown_provider
):
    end = datetime(2026, 11, 7, tzinfo=UTC)
    requested_start = datetime(2017, 1, 3, tzinfo=UTC)
    massive = SimpleNamespace(
        provider_name="massive",
        entitlement=SimpleNamespace(
            quota_policy={"history_constraints": {"max_lookback_years": 2}}
        ),
    )
    unknown = SimpleNamespace(
        provider_name=unknown_provider,
        entitlement=SimpleNamespace(quota_policy={}),
    )

    async def fake_resolve(_db, _capability, **_kwargs):
        return [massive, unknown]

    def fake_bound(constraints, *, now):
        return now.replace(year=now.year - constraints["max_lookback_years"]), None

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_resolve)
    monkeypatch.setattr("app.services.provider_runtime.provider_history_bound_start", fake_bound)
    preparation = {"range_mode": "bounded", "adjusted": False}
    start, provider_name, reason = await data_tasks._deepest_admitted_history_start(
        object(),
        SimpleNamespace(id=71, symbol="TEST"),
        Timeframe.D1,
        adjusted=False,
        end=end,
        request_id="bounded-unknown-depth",
        requested_start=requested_start,
        preparation=preparation,
    )

    assert (start, provider_name, reason) == (requested_start, unknown_provider, None)
    assert preparation["bounded_unknown_depth_provider"] == unknown_provider


@pytest.mark.asyncio
async def test_deepest_plan_uses_scoped_symbol_witness_for_unknown_source(monkeypatch):
    end = datetime(2026, 11, 7, tzinfo=UTC)
    source = SimpleNamespace(
        provider_name="twelve_data",
        entitlement=SimpleNamespace(quota_policy={}),
    )
    calls = {}

    async def fake_resolve(_db, _capability, **_kwargs):
        return [source]

    async def fake_witness(_db, _instrument, timeframe, _resolved, **kwargs):
        calls["timeframe"] = timeframe
        calls["preparation"] = kwargs["preparation"]
        return {
            "provider_name": "twelve_data",
            "timeframe": timeframe.value,
            "earliest_start": "2016-01-04T05:00:00+00:00",
            "listing_id": 52,
            "mic": "XNAS",
            "adjusted": False,
        }

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_resolve)
    monkeypatch.setattr(data_tasks, "_twelve_data_history_bound_witness", fake_witness)
    preparation = {"range_mode": "deepest_admitted", "adjusted": False}
    start, provider_name, reason = await data_tasks._deepest_admitted_history_start(
        object(),
        SimpleNamespace(id=72, symbol="TEST"),
        Timeframe.D1,
        adjusted=False,
        end=end,
        request_id="witnessed-deepest",
        preparation=preparation,
    )

    assert (start, provider_name, reason) == (
        datetime(2016, 1, 4, 5, tzinfo=UTC),
        "twelve_data",
        None,
    )
    assert preparation["history_bound_witness"]["listing_id"] == 52
    assert calls["timeframe"] is Timeframe.D1


def test_history_bound_witness_and_bounded_unknown_scopes_are_exact():
    from app.services.provider_runtime import (
        _bounded_unknown_history_admits,
        _dimension_applies_to_operation,
        _history_witness_admits,
        provider_history_entitlement_matches,
    )

    now = datetime(2026, 11, 7, tzinfo=UTC)
    requested_start = datetime(2018, 1, 2, tzinfo=UTC)
    source = SimpleNamespace(name="twelve_data", id=9)
    entitlement = SimpleNamespace(revision=3)
    witness = {
        "version": 1,
        "provider_name": "twelve_data",
        "data_source_id": 9,
        "instrument_id": 71,
        "domain_key": "issuer:test",
        "canonical_symbol": "TEST",
        "provider_symbol": "TEST.US",
        "listing_id": 12,
        "mic": "XNAS",
        "currency": "USD",
        "timeframe": "D1",
        "adjusted": False,
        "adjustment_basis": "raw",
        "feed_scope": "twelve_data:time_series",
        "session": "regular",
        "entitlement_revision": 3,
        "earliest_start": "2016-01-01T05:00:00+00:00",
        "observed_at": "2026-11-07T00:00:00+00:00",
        "stale_after": "2026-12-07T00:00:00+00:00",
    }
    kwargs = {
        "data_source": source,
        "entitlement": entitlement,
        "history_reason": "history_depth_unknown",
        "capability": ProviderCapability.PRICE_HISTORY,
        "instrument_id": 71,
        "provider_symbol": "TEST",
        "operation": "fetch_ohlcv:D1",
        "adjusted": False,
        "requested_start": requested_start,
        "now": now,
    }
    assert _history_witness_admits(witness, **kwargs)
    assert not _history_witness_admits(
        witness,
        **{**kwargs, "history_reason": "history_depth_exceeded"},
    )
    assert not _history_witness_admits(
        witness,
        **{**kwargs, "history_reason": "history_depth_invalid"},
    )
    known_floor_entitlement = SimpleNamespace(
        revision=3,
        quota_policy={"history_constraints": {"max_lookback_years": 2}},
    )
    history_allowed, known_floor_reason = provider_history_entitlement_matches(
        known_floor_entitlement, requested_start, now=now
    )
    assert not history_allowed and known_floor_reason == "history_depth_exceeded"
    assert not _history_witness_admits(
        witness,
        **{
            **kwargs,
            "entitlement": known_floor_entitlement,
            "history_reason": known_floor_reason,
        },
    )
    assert not _history_witness_admits({**witness, "data_source_id": 10}, **kwargs)
    assert not _history_witness_admits({**witness, "adjusted": True}, **kwargs)
    assert not _history_witness_admits({**witness, "entitlement_revision": 2}, **kwargs)

    bounded_scope = {
        "provider_name": "twelve_data",
        "instrument_id": 71,
        "canonical_symbol": "TEST",
        "timeframe": "D1",
        "adjusted": False,
        "start_at": requested_start.isoformat(),
        "end_at": "2018-02-01T00:00:00+00:00",
        "expires_at": "2026-11-07T00:10:00+00:00",
    }
    assert _bounded_unknown_history_admits(
        bounded_scope,
        provider_name="twelve_data",
        instrument_id=71,
        provider_symbol="TEST",
        operation="fetch_ohlcv:D1",
        adjusted=False,
        requested_start=requested_start,
        now=now,
    )
    assert not _bounded_unknown_history_admits(
        bounded_scope,
        provider_name="massive",
        instrument_id=71,
        provider_symbol="TEST",
        operation="fetch_ohlcv:D1",
        adjusted=False,
        requested_start=requested_start,
        now=now,
    )
    assert _dimension_applies_to_operation(
        {"applies_to_operations": ["fetch_ohlcv"]}, "get_earliest_timestamp"
    )


@pytest.mark.asyncio
async def test_twelve_data_witness_waits_for_native_usage_before_transport(monkeypatch):
    from app.tasks.data_tasks import _twelve_data_history_bound_witness

    async def baseline_denied(*_args, **_kwargs):
        return None, "native_usage_refresh_not_enabled_for_provider", True

    async def provider_call(*_args, **_kwargs):
        raise AssertionError("a held native baseline must prevent transport")

    monkeypatch.setattr(data_tasks, "_native_usage_job_for_operation_baseline", baseline_denied)
    monkeypatch.setattr("app.services.provider_runtime.execute_provider_call", provider_call)
    preparation = {}
    result = await _twelve_data_history_bound_witness(
        object(),
        SimpleNamespace(id=72, symbol="TEST"),
        Timeframe.D1,
        SimpleNamespace(provider_name="twelve_data"),
        end=datetime(2026, 11, 7, tzinfo=UTC),
        request_id="native-held-witness",
        priority=10,
        preparation=preparation,
    )
    assert result is None
    assert (
        preparation["history_bound_usage_hold"] == "native_usage_refresh_not_enabled_for_provider"
    )

    async def queued_baseline(*_args, **_kwargs):
        return SimpleNamespace(id=991), None, True

    monkeypatch.setattr(data_tasks, "_native_usage_job_for_operation_baseline", queued_baseline)
    queued_preparation = {}
    result = await _twelve_data_history_bound_witness(
        object(),
        SimpleNamespace(id=72, symbol="TEST"),
        Timeframe.D1,
        SimpleNamespace(provider_name="twelve_data"),
        end=datetime(2026, 11, 7, tzinfo=UTC),
        request_id="native-queued-witness",
        priority=10,
        preparation=queued_preparation,
    )
    assert result is None
    assert queued_preparation["history_bound_usage_job_id"] == 991


@pytest.mark.asyncio
async def test_twelve_data_witness_persists_exact_scope_and_reuses_fresh_value(monkeypatch):
    from app.tasks.data_tasks import _twelve_data_history_bound_witness

    class Result:
        def all(self):
            return [
                (
                    "TEST.US",
                    "XNAS",
                    datetime(1995, 1, 1, tzinfo=UTC),
                    52,
                    "USD",
                    datetime(2000, 1, 1, tzinfo=UTC),
                    "XNAS",
                    "America/New_York",
                    "issuer:test",
                    "USD",
                )
            ]

    class FakeDb:
        async def execute(self, _statement):
            return Result()

    async def admitted_baseline(*_args, **_kwargs):
        return None, None, False

    calls = []

    async def provider_call(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(result=datetime(1990, 1, 2, 5, tzinfo=UTC))

    monkeypatch.setattr(data_tasks, "_native_usage_job_for_operation_baseline", admitted_baseline)
    monkeypatch.setattr("app.services.provider_runtime.execute_provider_call", provider_call)
    preparation = {}
    resolved = SimpleNamespace(
        provider_name="twelve_data",
        data_source=SimpleNamespace(id=18),
        entitlement=SimpleNamespace(revision=4),
    )
    args = (
        FakeDb(),
        SimpleNamespace(id=72, symbol="TEST", domain_key="issuer:test", currency="USD"),
        Timeframe.D1,
        resolved,
    )
    kwargs = {
        "end": datetime(2026, 11, 7, tzinfo=UTC),
        "request_id": "persisted-symbol-witness",
        "priority": 30,
        "preparation": preparation,
    }
    first = await _twelve_data_history_bound_witness(*args, **kwargs)
    second = await _twelve_data_history_bound_witness(*args, **kwargs)

    assert first == second
    assert first["provider_symbol"] == "TEST.US"
    assert first["earliest_start"] == "2000-01-01T00:00:00+00:00"
    assert first["listing_id"] == 52
    assert first["mic"] == "XNAS"
    assert first["feed_scope"] == "twelve_data:time_series"
    assert first["adjustment_basis"] == "raw"
    assert first["entitlement_revision"] == 4
    assert first["source_operation"] == "get_earliest_timestamp"
    assert len(preparation["history_bound_witnesses"]) == 1
    assert len(calls) == 1
    assert calls[0][0][2] == "get_earliest_timestamp"
    assert calls[0][1]["operation_cost_overrides"] == {"twelve_data": 1}


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


@pytest.mark.asyncio
async def test_unpinned_chunk_falls_through_only_on_proven_pretransport_quota_denial(
    monkeypatch,
):
    end = datetime(2026, 11, 6, tzinfo=UTC)
    retry_at = datetime(2026, 11, 6, 12, 5, tzinfo=UTC)
    planner_calls = []
    fetch_candidates = []
    transports = []

    async def candidate_plan(
        _db,
        _job,
        _instrument,
        _timeframe,
        _preparation,
        *,
        priority,
        excluded_provider_names=frozenset(),
    ):
        assert priority == 10
        excluded = set(excluded_provider_names)
        planner_calls.append(excluded)
        for provider, earliest in (
            ("deep-free", datetime(2016, 1, 1, tzinfo=UTC)),
            ("second-free", datetime(2018, 1, 1, tzinfo=UTC)),
        ):
            if provider not in excluded:
                candidate = {
                    "range_mode": "deepest_admitted",
                    "adjusted": True,
                    "source_provider": provider,
                    "analysis_requirement_unmet": False,
                }
                return (
                    (end - timedelta(days=1), end, earliest, end, provider, None),
                    candidate,
                    None,
                    None,
                    None,
                )
        return (
            (None, None, None, None, None, "no_eligible_history_provider"),
            {},
            None,
            None,
            None,
        )

    async def candidate_fetch(_db, _instrument, _timeframe, _start, **kwargs):
        provider = kwargs["source_provider"]
        fetch_candidates.append(provider)
        if provider == "deep-free":
            # Mirrors execute_provider_call's typed final outcome: reservation
            # was denied before the adapter invoke/transport boundary.
            raise ProviderQuotaAdmissionError(
                "durable provider quota admission denied for price_history/fetch_ohlcv:D1: deep-free",
                retry_at=retry_at,
            )
        transports.append(provider)
        return ["persisted-from-second-free"]

    monkeypatch.setattr(data_tasks, "_history_chunk_plan_with_native_admission", candidate_plan)
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", candidate_fetch)
    result = await data_tasks._plan_and_fetch_history_chunk(
        object(),
        job=SimpleNamespace(id=50, end_at=end),
        instrument=SimpleNamespace(id=71, symbol="TEST"),
        timeframe=Timeframe.D1,
        preparation={"range_mode": "deepest_admitted", "adjusted": True},
        priority=10,
        redis=None,
    )

    assert result[0][4] == "second-free"
    assert result[1]["source_provider"] == "second-free"
    assert result[5] == ["persisted-from-second-free"]
    assert fetch_candidates == ["deep-free", "second-free"]
    assert transports == ["second-free"]
    assert planner_calls == [set(), {"deep-free"}]


@pytest.mark.asyncio
async def test_pinned_history_continuation_does_not_fallback_after_quota_denial(monkeypatch):
    end = datetime(2026, 11, 6, tzinfo=UTC)
    planner_calls = []

    async def candidate_plan(*_args, excluded_provider_names=frozenset(), **_kwargs):
        planner_calls.append(set(excluded_provider_names))
        preparation = {
            "range_mode": "deepest_admitted",
            "adjusted": True,
            "chunk": True,
            "source_provider": "deep-free",
        }
        return (
            (
                datetime(2020, 1, 1, tzinfo=UTC),
                end,
                datetime(2016, 1, 1, tzinfo=UTC),
                end,
                "deep-free",
                None,
            ),
            preparation,
            None,
            None,
            None,
        )

    async def denied_fetch(*_args, **_kwargs):
        raise ProviderQuotaAdmissionError(
            "durable provider quota admission denied for price_history/fetch_ohlcv:D1: deep-free",
            retry_at=end + timedelta(minutes=1),
        )

    monkeypatch.setattr(data_tasks, "_history_chunk_plan_with_native_admission", candidate_plan)
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", denied_fetch)
    with pytest.raises(
        ProviderQuotaAdmissionError, match="durable provider quota admission denied"
    ):
        await data_tasks._plan_and_fetch_history_chunk(
            object(),
            job=SimpleNamespace(id=51, end_at=end),
            instrument=SimpleNamespace(id=71, symbol="TEST"),
            timeframe=Timeframe.D1,
            preparation={
                "range_mode": "deepest_admitted",
                "adjusted": True,
                "chunk": True,
                "source_provider": "deep-free",
            },
            priority=100,
            redis=None,
        )
    assert planner_calls == [set()]


@pytest.mark.asyncio
async def test_quota_fallback_does_not_pin_a_provider_below_the_analysis_floor(monkeypatch):
    end = datetime(2026, 11, 6, tzinfo=UTC)
    retry_at = end + timedelta(minutes=5)
    fetch_candidates = []

    async def candidate_plan(
        _db,
        _job,
        _instrument,
        _timeframe,
        _preparation,
        *,
        priority,
        excluded_provider_names=frozenset(),
    ):
        del priority
        excluded = set(excluded_provider_names)
        provider = "deep-free" if "deep-free" not in excluded else "shallow-free"
        unmet = provider == "shallow-free"
        return (
            (end - timedelta(days=1), end, datetime(2024, 11, 6, tzinfo=UTC), end, provider, None),
            {
                "range_mode": "deepest_admitted",
                "adjusted": True,
                "source_provider": provider,
                "analysis_requirement_unmet": unmet,
            },
            None,
            None,
            None,
        )

    async def candidate_fetch(_db, _instrument, _timeframe, _start, **kwargs):
        provider = kwargs["source_provider"]
        fetch_candidates.append(provider)
        raise ProviderQuotaAdmissionError(
            "durable provider quota admission denied for price_history/fetch_ohlcv:MN: deep-free",
            retry_at=retry_at,
        )

    monkeypatch.setattr(data_tasks, "_history_chunk_plan_with_native_admission", candidate_plan)
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", candidate_fetch)
    with pytest.raises(ProviderQuotaAdmissionError) as raised:
        await data_tasks._plan_and_fetch_history_chunk(
            object(),
            job=SimpleNamespace(id=53, end_at=end),
            instrument=SimpleNamespace(id=71, symbol="TEST"),
            timeframe=Timeframe.MN,
            preparation={"range_mode": "deepest_admitted", "adjusted": True},
            priority=10,
            redis=None,
        )

    assert raised.value.retry_at == retry_at
    assert fetch_candidates == ["deep-free"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error, transport_started",
    [
        (ProviderRateLimitError("deep-free", "429 after request", status_code=429), True),
        (ProviderQuotaAdmissionError("quota state ambiguous after transport"), True),
    ],
)
async def test_post_or_ambiguous_transport_error_does_not_select_another_source(
    monkeypatch, error, transport_started
):
    planner_calls = []
    transport_attempts = []
    end = datetime(2026, 11, 6, tzinfo=UTC)

    async def candidate_plan(*_args, excluded_provider_names=frozenset(), **_kwargs):
        planner_calls.append(set(excluded_provider_names))
        preparation = {
            "range_mode": "deepest_admitted",
            "adjusted": True,
            "source_provider": "deep-free",
        }
        return (
            (
                end - timedelta(days=1),
                end,
                datetime(2016, 1, 1, tzinfo=UTC),
                end,
                "deep-free",
                None,
            ),
            preparation,
            None,
            None,
            None,
        )

    async def uncertain_fetch(*_args, **_kwargs):
        transport_attempts.append("deep-free")
        raise error

    monkeypatch.setattr(data_tasks, "_history_chunk_plan_with_native_admission", candidate_plan)
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", uncertain_fetch)
    with pytest.raises(type(error)):
        await data_tasks._plan_and_fetch_history_chunk(
            object(),
            job=SimpleNamespace(id=52, end_at=end),
            instrument=SimpleNamespace(id=71, symbol="TEST"),
            timeframe=Timeframe.D1,
            preparation={"range_mode": "deepest_admitted", "adjusted": True},
            priority=10,
            redis=None,
        )
    assert transport_attempts == (["deep-free"] if transport_started else [])
    assert planner_calls == [set()]


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
