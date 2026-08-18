from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.market_map import _profile_field_conflict, _return


def _snapshot(snapshot_id: int, source_id: int, provider: str, observed_at: datetime, value: float):
    return SimpleNamespace(
        id=snapshot_id,
        data_source_id=source_id,
        data_source=SimpleNamespace(name=provider),
        observed_at=observed_at,
        payload={"market_cap": value},
    )


def test_profile_field_conflict_uses_latest_observation_per_provider_and_tolerance():
    observed = datetime(2024, 1, 1, tzinfo=UTC)
    candidates = [
        _snapshot(1, 10, "provider-a", observed, 200),
        _snapshot(2, 10, "provider-a", observed + timedelta(days=1), 100),
        _snapshot(3, 20, "provider-b", observed + timedelta(days=1), 100.5),
    ]

    assert _profile_field_conflict(candidates, "market_cap") is None


def test_profile_field_conflict_preserves_provider_candidates():
    observed = datetime(2024, 1, 1, tzinfo=UTC)
    conflict = _profile_field_conflict(
        [
            _snapshot(1, 10, "provider-a", observed, 100),
            _snapshot(2, 20, "provider-b", observed, 120),
        ],
        "market_cap",
    )

    assert conflict is not None
    assert conflict["resolution"] == "provider_precedence"
    assert conflict["candidate_count"] == 2
    assert {item["provider_name"] for item in conflict["candidates"]} == {
        "provider-a",
        "provider-b",
    }


def _bar(ts: datetime, close: float):
    return SimpleNamespace(ts=ts, close=close)


def test_market_map_mtd_uses_last_session_before_month_boundary():
    bars = [
        _bar(datetime(2023, 12, 29, tzinfo=UTC), 100),
        _bar(datetime(2024, 1, 2, tzinfo=UTC), 105),
        _bar(datetime(2024, 1, 3, tzinfo=UTC), 110),
    ]

    value, observed, code, message = _return(
        bars,
        "MTD",
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 1, 3, tzinfo=UTC),
    )

    assert value == pytest.approx(0.1)
    assert observed == datetime(2024, 1, 3, tzinfo=UTC)
    assert code is None
    assert message is None


def test_market_map_ytd_requires_a_prior_year_end_session():
    bars = [
        _bar(datetime(2023, 12, 29, tzinfo=UTC), 100),
        _bar(datetime(2024, 1, 2, tzinfo=UTC), 110),
    ]

    value, observed, code, message = _return(
        bars,
        "YTD",
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 1, 2, tzinfo=UTC),
    )

    assert value == pytest.approx(0.1)
    assert observed == datetime(2024, 1, 2, tzinfo=UTC)
    assert code is None
    assert message is None


def test_market_map_mtd_does_not_fall_back_to_first_in_window_bar():
    bars = [_bar(datetime(2024, 1, 2, tzinfo=UTC), 105)]

    value, observed, code, message = _return(
        bars,
        "MTD",
        datetime(2024, 1, 1, tzinfo=UTC),
        datetime(2024, 1, 2, tzinfo=UTC),
    )

    assert value is None
    assert observed == datetime(2024, 1, 2, tzinfo=UTC)
    assert code == "insufficient_history"
    assert message == "MTD requires more aligned history."
