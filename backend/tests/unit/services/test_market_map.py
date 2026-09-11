from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.schemas.market_map import MarketMapRequest
from app.services.market_map import (
    _as_utc,
    _cache_key,
    _condition_tree_matches_declared,
    _period_bounds,
    _profile_area_provenance,
    _profile_field_conflict,
    _return,
    _snapshot_classification,
)


def _snapshot(
    snapshot_id: int,
    source_id: int,
    provider: str,
    observed_at: datetime,
    value: float,
    fetched_at: datetime | None = None,
):
    return SimpleNamespace(
        id=snapshot_id,
        data_source_id=source_id,
        data_source=SimpleNamespace(name=provider),
        observed_at=observed_at,
        fetched_at=fetched_at or observed_at,
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


def test_market_map_provenance_serializes_snapshot_timestamps_on_utc_timeline():
    observed_at = datetime.fromisoformat("2024-01-02T00:00:00+02:00")
    fetched_at = datetime.fromisoformat("2024-01-02T01:00:00+02:00")
    snapshot = _snapshot(1, 10, "provider-a", observed_at, 100, fetched_at)
    snapshot.payload = {
        "market_cap": 100,
        "sector": "Information Technology",
        "industry": "Software",
    }

    classification = _snapshot_classification(snapshot)
    area = _profile_area_provenance(
        snapshot,
        "market_cap",
        0,
        {10: {"policy_evaluation_at": "2024-01-01T00:00:00+00:00"}},
    )

    assert classification["observed_at"] == "2024-01-01T22:00:00+00:00"
    assert classification["fetched_at"] == "2024-01-01T23:00:00+00:00"
    assert area["observed_at"] == "2024-01-01T22:00:00+00:00"
    assert area["fetched_at"] == "2024-01-01T23:00:00+00:00"


def test_market_map_cache_key_normalizes_watermark_offsets():
    request = MarketMapRequest(
        source_id="benchmark-family:us:cap_weight",
        period="CUSTOM",
        start=datetime(2024, 1, 1, 21, tzinfo=UTC),
        end=datetime(2024, 1, 1, 22, tzinfo=UTC),
    )
    common = {
        "membership_version": "v1",
        "member_ids": [1],
        "reference_membership_version": None,
        "reference_member_ids": [],
    }
    utc_key = _cache_key(
        request,
        **common,
        bar_watermark=datetime(2024, 1, 1, 22, tzinfo=UTC),
        reference_watermark=datetime(2024, 1, 1, 22, tzinfo=UTC),
        event_watermark=datetime(2024, 1, 1, 22, tzinfo=UTC),
        profile_snapshot_watermark=datetime(2024, 1, 1, 22, tzinfo=UTC),
    )
    offset_key = _cache_key(
        request,
        **common,
        bar_watermark=datetime.fromisoformat("2024-01-02T00:00:00+02:00"),
        reference_watermark=datetime.fromisoformat("2024-01-02T00:00:00+02:00"),
        event_watermark=datetime.fromisoformat("2024-01-02T00:00:00+02:00"),
        profile_snapshot_watermark=datetime.fromisoformat("2024-01-02T00:00:00+02:00"),
    )

    assert utc_key == offset_key


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


def test_market_map_timestamps_normalize_to_utc_for_ranges_and_returns():
    offset = datetime.fromisoformat("2024-01-02T00:00:00+02:00")
    assert _as_utc(offset) == datetime(2024, 1, 1, 22, tzinfo=UTC)
    assert _as_utc(datetime(2024, 1, 1, 22)) == datetime(2024, 1, 1, 22, tzinfo=UTC)

    request = MarketMapRequest(
        source_id="benchmark-family:us:cap_weight",
        period="CUSTOM",
        start=datetime.fromisoformat("2024-01-01T23:00:00+02:00"),
        end=offset,
    )
    period_start, period_end = _period_bounds(request, offset)
    assert period_start == datetime(2024, 1, 1, 21, tzinfo=UTC)
    assert period_end == datetime(2024, 1, 1, 22, tzinfo=UTC)

    value, observed, code, message = _return(
        [
            _bar(datetime(2024, 1, 1, 20, 30), 100),
            _bar(datetime(2024, 1, 1, 21, 30), 110),
        ],
        "CUSTOM",
        period_start,
        period_end,
    )
    assert value == pytest.approx(0.1)
    assert observed == datetime(2024, 1, 1, 21, 30, tzinfo=UTC)
    assert code is None
    assert message is None


def test_market_map_cache_key_collapses_equivalent_timestamp_offsets():
    request_utc = MarketMapRequest(
        source_id="benchmark-family:us:cap_weight",
        period="CUSTOM",
        start=datetime(2024, 1, 1, 21, tzinfo=UTC),
        end=datetime(2024, 1, 1, 22, tzinfo=UTC),
    )
    request_offset = request_utc.model_copy(
        update={
            "start": datetime.fromisoformat("2024-01-01T23:00:00+02:00"),
            "end": datetime.fromisoformat("2024-01-02T00:00:00+02:00"),
        }
    )
    kwargs = {
        "membership_version": "v1",
        "member_ids": [1, 2],
        "bar_watermark": datetime(2024, 1, 1, 22, tzinfo=UTC),
        "reference_watermark": None,
    }
    assert _cache_key(request_utc, **kwargs) == _cache_key(request_offset, **kwargs)


def test_python_breadth_tree_match_ignores_only_runner_metadata():
    requested = {
        "kind": "all",
        "params": {
            "conditions": [
                {
                    "kind": "python_series",
                    "params": {
                        "code_version_id": 11,
                        "scope": "cross_sectional",
                        "statistic": "median",
                        "operator": "gte",
                        "threshold": 0.1,
                    },
                },
                {
                    "kind": "comparison",
                    "params": {"field": "close", "operator": "gte", "threshold": 100},
                },
            ]
        },
    }
    resolved = {
        "kind": "all",
        "params": {
            "conditions": [
                {
                    "kind": "python_series",
                    "params": {
                        "code_version_id": 11,
                        "source": "output.series('score', market.close())",
                        "output_name": "score",
                        "scope": "cross_sectional",
                        "statistic": "median",
                        "operator": "gte",
                        "threshold": 0.1,
                        "parameters": {},
                    },
                },
                {
                    "kind": "comparison",
                    "target_scope": "member",
                    "params": {"field": "close", "operator": "gte", "threshold": 100},
                },
            ]
        },
    }

    assert _condition_tree_matches_declared(requested, resolved)

    changed = {
        **requested,
        "params": {
            "conditions": [
                requested["params"]["conditions"][0],
                {
                    "kind": "comparison",
                    "params": {"field": "close", "operator": "gte", "threshold": 101},
                },
            ]
        },
    }
    assert not _condition_tree_matches_declared(changed, resolved)
