from types import SimpleNamespace

import pytest

from app.services import benchmark_family_history as history


def test_family_history_normalizers_reject_unknown_values_and_dedupe_timeframes():
    assert history.normalize_family_roles(["growth", "cap_weight", "growth"]) == [
        "cap_weight",
        "growth",
    ]
    assert history.normalize_history_timeframes(["d1", "W1", "D1"]) == ["D1", "W1"]

    with pytest.raises(ValueError, match="Unknown benchmark family"):
        history.normalize_family_keys(["not-a-family"])
    with pytest.raises(ValueError, match="Unsupported benchmark family role"):
        history.normalize_family_roles(["momentum"])
    with pytest.raises(ValueError, match="Unsupported history timeframe"):
        history.normalize_history_timeframes(["TICK"])


@pytest.mark.asyncio
async def test_family_history_plan_deduplicates_members_and_reports_unavailable_legs(monkeypatch):
    async def fake_resolve(_db, _user_id, source_id, *, as_of):
        assert _user_id == 0
        assert as_of is None
        if source_id.endswith(":cap_weight"):
            return SimpleNamespace(
                descriptor=SimpleNamespace(membership_version="cap-v1"),
                members=(
                    SimpleNamespace(instrument_id=10),
                    SimpleNamespace(instrument_id=20),
                ),
                exclusions=({"reason": "unresolved_holding"},),
            )
        return SimpleNamespace(
            descriptor=SimpleNamespace(membership_version="empty-v1"),
            members=(),
            exclusions=({"reason": "holdings_snapshot_not_loaded"},),
        )

    monkeypatch.setattr(history, "resolve_watchlist_source", fake_resolve)
    plan = await history.plan_benchmark_family_history_refresh(
        object(),
        family_keys=[history.normalize_family_keys(None)[0]],
        roles=["cap_weight", "equal_weight"],
        max_instruments=1,
        timeframes=["D1", "D1"],
    )

    assert plan["instrument_ids"] == [10]
    assert plan["available_instrument_count"] == 2
    assert plan["selected_instrument_count"] == 1
    assert plan["limited"] is True
    assert plan["timeframes"] == ["D1"]
    assert plan["legs"][0]["selected_count"] == 2
    assert plan["legs"][1]["status"] == "unavailable"
    assert plan["legs"][1]["message"] == "holdings_snapshot_not_loaded"


@pytest.mark.asyncio
async def test_queue_snapshot_member_history_deduplicates_canonical_members_and_reports_queue_state():
    class Result:
        def all(self):
            return [
                (101, 10, "security", "equity", True),
                (101, 20, "security", "equity", True),
                (102, 20, "security", "equity", True),
                (102, 30, "security", "equity", True),
            ]

    class Session:
        async def execute(self, _statement):
            return Result()

    class Redis:
        def __init__(self):
            self.calls = []

        async def enqueue_job(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return object()

    redis = Redis()
    result = await history.queue_snapshot_member_history(
        Session(),
        redis,
        [102, 101, 102],
        timeframes=["D1", "W1", "D1"],
        max_instruments=2,
    )

    assert result == {
        "status": "queued",
        "snapshot_ids": [102, 101],
        "available_instrument_count": 3,
        "selected_instrument_count": 2,
        "limited": True,
        "queued": 2,
        "already_queued": 0,
        "unresolved_count": 0,
        "timeframes": ["D1", "W1"],
    }
    assert redis.calls == [
        (
            ("task_bulk_fetch_instrument", 10, ["D1", "W1"]),
            {"_job_id": "watchlist-source-history:10:D1,W1"},
        ),
        (
            ("task_bulk_fetch_instrument", 20, ["D1", "W1"]),
            {"_job_id": "watchlist-source-history:20:D1,W1"},
        ),
    ]
