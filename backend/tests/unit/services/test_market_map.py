from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.market_map import _profile_field_conflict


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
