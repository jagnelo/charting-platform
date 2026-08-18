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

