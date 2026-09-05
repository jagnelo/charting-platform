from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.services import watchlist_history as history


def test_watchlist_history_normalizers_dedupe_sources_and_timeframes():
    assert history.normalize_source_ids(["watchlist:1", " market-group:sp500 ", "watchlist:1"]) == [
        "watchlist:1",
        "market-group:sp500",
    ]
    assert history.normalize_history_timeframes(["d1", "W1", "D1"]) == ["D1", "W1"]

    with pytest.raises(ValueError, match="At least one watchlist source"):
        history.normalize_source_ids([])
    with pytest.raises(ValueError, match="Unsupported history timeframe"):
        history.normalize_history_timeframes(["TICK"])


@pytest.mark.asyncio
async def test_watchlist_history_plan_uses_user_scope_and_deduplicates_members(monkeypatch):
    calls = []

    async def fake_resolve(_db, user_id, source_id, *, as_of):
        calls.append((user_id, source_id, as_of))
        if source_id == "watchlist:private":
            return SimpleNamespace(
                descriptor=SimpleNamespace(
                    source_id=source_id,
                    source_kind="personal",
                    name="Private",
                    locked=False,
                    membership_version="private-v1",
                ),
                members=(SimpleNamespace(instrument_id=10), SimpleNamespace(instrument_id=20)),
                exclusions=(),
            )
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                source_id=source_id,
                source_kind="index_membership",
                name="Managed",
                locked=True,
                membership_version="managed-v1",
            ),
            members=(SimpleNamespace(instrument_id=20), SimpleNamespace(instrument_id=30)),
            exclusions=({"reason": "unresolved_holding"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    as_of = SimpleNamespace()
    plan = await history.plan_watchlist_source_history_refresh(
        object(),
        42,
        source_ids=["watchlist:private", "market-group:managed"],
        as_of=as_of,
        max_instruments=2,
        timeframes=["D1", "D1"],
    )

    assert calls == [(42, "watchlist:private", as_of), (42, "market-group:managed", as_of)]
    assert plan["instrument_ids"] == [10, 20]
    assert plan["available_instrument_count"] == 3
    assert plan["selected_instrument_count"] == 2
    assert plan["limited"] is True
    assert plan["sources"][0]["selected_count"] == 2
    assert plan["sources"][1]["deduplicated_count"] == 1
    assert plan["sources"][1]["locked"] is True


@pytest.mark.asyncio
async def test_watchlist_history_plan_retains_unavailable_source(monkeypatch):
    async def fake_resolve(_db, _user_id, source_id, *, as_of):
        raise LookupError(f"{source_id} is not visible")

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_watchlist_source_history_refresh(
        object(),
        7,
        source_ids=["watchlist:missing"],
    )

    assert plan["instrument_ids"] == []
    assert plan["sources"] == [
        {
            "source_id": "watchlist:missing",
            "source_kind": None,
            "name": "watchlist:missing",
            "locked": False,
            "status": "unavailable",
            "member_count": 0,
            "selected_count": 0,
            "deduplicated_count": 0,
            "excluded_count": 0,
            "membership_version": None,
            "message": "watchlist:missing is not visible",
        }
    ]


@pytest.mark.asyncio
async def test_watchlist_history_plan_and_status_preserve_pending_locked_source(monkeypatch):
    async def fake_resolve(_db, _user_id, source_id, *, as_of):
        return SimpleNamespace(
            descriptor=SimpleNamespace(
                source_id=source_id,
                source_kind="etf_holdings",
                name="Unhydrated ETF holdings",
                locked=True,
                membership_version="etf-v1",
                provenance={"availability": "profile_not_loaded"},
            ),
            members=(),
            exclusions=({"reason": "etf_profile_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_watchlist_source_history_refresh(
        object(),
        7,
        source_ids=["etf-holdings:UNHYDRATED"],
        timeframes=["D1"],
    )

    assert plan["sources"][0]["status"] == "pending"
    assert plan["sources"][0]["message"] == "etf_profile_not_loaded"

    class FakeDB:
        async def execute(self, _statement):
            raise AssertionError("pending source with no members must not query bars")

    status = await history.build_watchlist_source_history_status(
        FakeDB(),
        7,
        source_id="etf-holdings:UNHYDRATED",
        timeframes=["D1"],
    )
    assert status["overall_status"] == "pending"
    assert status["selected_instrument_count"] == 0


@pytest.mark.asyncio
async def test_watchlist_history_status_uses_local_coverage_and_worker_progress(monkeypatch):
    async def fake_plan(*_args, **_kwargs):
        return {
            "source_ids": ["benchmark-family:sp500:cap_weight"],
            "timeframes": ["D1"],
            "as_of": None,
            "max_instruments": 5000,
            "instrument_ids": [10, 20],
            "available_instrument_count": 2,
            "selected_instrument_count": 2,
            "limited": False,
            "sources": [
                {
                    "source_id": "benchmark-family:sp500:cap_weight",
                    "source_kind": "index_membership",
                    "name": "S&P 500 — Cap weight",
                    "locked": True,
                    "excluded_count": 1,
                    "membership_version": "sp500-v1",
                    "message": None,
                }
            ],
        }

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1

            class FakeResult:
                def all(self_inner):
                    if self.calls == 1:
                        return [
                            SimpleNamespace(
                                timeframe=SimpleNamespace(value="D1"),
                                covered_count=1,
                                bar_count=250,
                                oldest=datetime(2024, 1, 2, tzinfo=UTC),
                                newest=datetime(2025, 1, 2, tzinfo=UTC),
                            )
                        ]
                    return [(10, SimpleNamespace(value="D1"), 250)]

            return FakeResult()

    monkeypatch.setattr(history, "plan_watchlist_source_history_refresh", fake_plan)
    status = await history.build_watchlist_source_history_status(
        FakeDB(),
        42,
        source_id="benchmark-family:sp500:cap_weight",
        progress_by_instrument={20: {"status": "in_progress", "results": {}}},
    )

    assert status["locked"] is True
    assert status["overall_status"] == "fetching"
    assert status["analysis_ready"] is False
    assert status["analysis_ready_status"] == "pending"
    assert status["selected_instrument_count"] == 2
    assert status["excluded_count"] == 1
    assert status["timeframes"] == [
        {
            "timeframe": "D1",
            "member_count": 2,
            "covered_member_count": 1,
            "coverage_percent": 50.0,
            "analysis_ready_member_count": 0,
            "analysis_ready_percent": 0.0,
            "required_bar_count": 252,
            "bar_count": 250,
            "oldest": datetime(2024, 1, 2, tzinfo=UTC),
            "newest": datetime(2025, 1, 2, tzinfo=UTC),
            "in_progress_count": 1,
            "complete_count": 0,
            "failed_count": 0,
            "pending_count": 0,
        }
    ]


@pytest.mark.asyncio
async def test_watchlist_history_status_separates_covered_from_analysis_ready(monkeypatch):
    async def fake_plan(*_args, **_kwargs):
        return {
            "source_ids": ["market-group:sp500"],
            "timeframes": ["D1", "W1"],
            "as_of": None,
            "max_instruments": 5000,
            "instrument_ids": [10],
            "available_instrument_count": 1,
            "selected_instrument_count": 1,
            "limited": False,
            "sources": [
                {
                    "source_id": "market-group:sp500",
                    "source_kind": "index_membership",
                    "name": "S&P 500",
                    "locked": True,
                    "status": "ready",
                    "excluded_count": 0,
                    "membership_version": "v1",
                    "message": None,
                }
            ],
        }

    class FakeDB:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1

            class FakeResult:
                def __init__(self, call_number):
                    self.call_number = call_number

                def all(self_inner):
                    if self_inner.call_number == 1:
                        return [
                            SimpleNamespace(
                                timeframe=SimpleNamespace(value="D1"),
                                covered_count=1,
                                bar_count=252,
                                oldest=None,
                                newest=None,
                            ),
                            SimpleNamespace(
                                timeframe=SimpleNamespace(value="W1"),
                                covered_count=1,
                                bar_count=10,
                                oldest=None,
                                newest=None,
                            ),
                        ]
                    return [
                        (10, SimpleNamespace(value="D1"), 252),
                        (10, SimpleNamespace(value="W1"), 10),
                    ]

            return FakeResult(self.calls)

    monkeypatch.setattr(history, "plan_watchlist_source_history_refresh", fake_plan)
    status = await history.build_watchlist_source_history_status(
        FakeDB(), 42, source_id="market-group:sp500", timeframes=["D1", "W1"]
    )

    assert status["overall_status"] == "ready"
    assert status["analysis_ready"] is False
    assert status["analysis_ready_status"] == "partial"
