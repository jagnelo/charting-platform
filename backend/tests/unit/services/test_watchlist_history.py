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
