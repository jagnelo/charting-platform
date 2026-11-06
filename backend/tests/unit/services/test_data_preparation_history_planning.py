from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models.ohlcv import Timeframe
from app.tasks import data_tasks


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

    monkeypatch.setattr(
        "app.services.provider_runtime.resolve_provider_chain", fake_resolve
    )
    monkeypatch.setattr(
        "app.services.provider_runtime.provider_history_bound_start", fake_bound
    )

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
    chunk_start, chunk_end, full_start, full_end, selected_provider, plan_reason = (
        await data_tasks._history_chunk_plan(
            object(), job, instrument, Timeframe.D1, preparation
        )
    )
    assert plan_reason is None
    assert selected_provider == "alpaca"
    assert preparation["source_provider"] == "alpaca"
    assert full_start == earliest
    assert full_end == end
    assert chunk_end == end
    assert chunk_start > full_start
    assert (chunk_end - chunk_start).days <= 2000


def test_older_automatic_chunks_yield_to_background_after_analysis_window():
    useful_start = datetime(2024, 1, 1, tzinfo=UTC)
    assert data_tasks._older_chunk_priority(
        current_priority=10,
        range_mode="deepest_admitted",
        useful_start=useful_start,
        older_chunk_end=datetime(2024, 6, 1, tzinfo=UTC),
    ) == 10
    assert data_tasks._older_chunk_priority(
        current_priority=10,
        range_mode="deepest_admitted",
        useful_start=useful_start,
        older_chunk_end=datetime(2023, 12, 31, tzinfo=UTC),
    ) == 100
    assert data_tasks._older_chunk_priority(
        current_priority=10,
        range_mode="deepest_admitted",
        useful_start=None,
        older_chunk_end=datetime(2026, 1, 1, tzinfo=UTC),
    ) == 100
    assert data_tasks._older_chunk_priority(
        current_priority=10,
        range_mode="bounded",
        useful_start=None,
        older_chunk_end=datetime(2010, 1, 1, tzinfo=UTC),
    ) == 10


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
    chunk_start, _chunk_end, full_start, _full_end, _provider, reason = (
        await data_tasks._history_chunk_plan(
            object(),
            SimpleNamespace(id=91, start_at=None, end_at=end),
            SimpleNamespace(id=42, symbol="TEST"),
            Timeframe.D1,
            preparation,
        )
    )
    assert reason is None
    assert full_start == admitted_start
    assert chunk_start == admitted_start
    assert preparation["analysis_requirement_unmet"] is True


async def _async_value(value):
    return value
