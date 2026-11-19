"""An unpinned history request moves past a provider that has no bars for it."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.models.ohlcv import Timeframe
from app.services.provider_runtime import ProviderNoDataError
from app.tasks import data_tasks

END = datetime(2026, 11, 18, tzinfo=UTC)
CANDIDATES = ("first-free", "second-free")


def _install(monkeypatch, answers):
    planner_calls: list[set[str]] = []
    fetched: list[str] = []

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
        excluded = set(excluded_provider_names)
        planner_calls.append(excluded)
        for provider in CANDIDATES:
            if provider not in excluded:
                return (
                    (
                        END - timedelta(days=30),
                        END,
                        END - timedelta(days=3650),
                        END,
                        provider,
                        None,
                    ),
                    {
                        "range_mode": "deepest_admitted",
                        "adjusted": True,
                        "source_provider": provider,
                    },
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

    async def fetch(_db, _instrument, _timeframe, _start, **kwargs):
        provider = kwargs["source_provider"]
        fetched.append(provider)
        answer = answers[provider]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(data_tasks, "_history_chunk_plan_with_native_admission", candidate_plan)
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", fetch)
    return planner_calls, fetched


async def _run(preparation):
    return await data_tasks._plan_and_fetch_history_chunk(
        object(),
        job=SimpleNamespace(id=90, end_at=END),
        instrument=SimpleNamespace(id=7, symbol="SMALL"),
        timeframe=Timeframe.D1,
        preparation=preparation,
        priority=50,
        redis=None,
    )


def _empty(provider):
    return ProviderNoDataError(f"{provider} returned no usable data for fetch_ohlcv:D1")


@pytest.mark.asyncio
async def test_first_provider_without_bars_falls_through_to_the_next(monkeypatch):
    planner_calls, fetched = _install(
        monkeypatch, {"first-free": _empty("first-free"), "second-free": ["bar"]}
    )

    result = await _run({"range_mode": "deepest_admitted", "adjusted": True})

    assert fetched == ["first-free", "second-free"]
    assert planner_calls == [set(), {"first-free"}]
    assert result[1]["source_provider"] == "second-free"
    assert result[5] == ["bar"]


@pytest.mark.asyncio
async def test_every_provider_without_bars_ends_empty_with_a_reason(monkeypatch):
    _planner_calls, fetched = _install(
        monkeypatch, {"first-free": _empty("first-free"), "second-free": _empty("second-free")}
    )

    result = await _run({"range_mode": "deepest_admitted", "adjusted": True})

    assert fetched == ["first-free", "second-free"]
    assert result[5] == []
    assert result[1]["provider_no_data_reason"]


@pytest.mark.asyncio
async def test_a_pinned_series_never_mixes_in_another_provider(monkeypatch):
    _planner_calls, fetched = _install(
        monkeypatch, {"first-free": _empty("first-free"), "second-free": ["bar"]}
    )

    result = await _run(
        {"range_mode": "deepest_admitted", "adjusted": True, "source_provider": "first-free"}
    )

    assert fetched == ["first-free"]
    assert result[5] == []


@pytest.mark.asyncio
async def test_no_eligible_source_is_not_treated_as_a_definitive_empty_answer(monkeypatch):
    _planner_calls, fetched = _install(
        monkeypatch,
        {
            "first-free": ProviderNoDataError(
                "No currently-supported providers available for price_history/fetch_ohlcv:D1"
            ),
            "second-free": ["bar"],
        },
    )

    result = await _run({"range_mode": "deepest_admitted", "adjusted": True})

    assert fetched == ["first-free"]
    assert result[5] == []
