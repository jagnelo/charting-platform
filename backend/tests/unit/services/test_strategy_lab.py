from datetime import UTC, date, datetime, timedelta, timezone

from app.services.strategy_lab import DynamicUniverseSnapshot, _dynamic_snapshot_fields


def test_dynamic_snapshot_fields_canonicalize_known_at_to_utc():
    snapshot = DynamicUniverseSnapshot(
        id=17,
        composition_date=date(2024, 1, 1),
        known_at=datetime(2024, 1, 1, 2, 0, tzinfo=timezone(timedelta(hours=2))),
        member_ids=frozenset({23}),
        source_type="etf_holdings",
    )

    assert _dynamic_snapshot_fields(snapshot) == {
        "universe_snapshot_id": 17,
        "universe_snapshot_composition_date": "2024-01-01",
        "universe_snapshot_known_at": "2024-01-01T00:00:00Z",
        "universe_snapshot_source_type": "etf_holdings",
    }


def test_dynamic_snapshot_fields_treat_naive_known_at_as_utc():
    snapshot = DynamicUniverseSnapshot(
        id=18,
        composition_date=date(2024, 3, 1),
        known_at=datetime(2024, 3, 1, tzinfo=UTC).replace(tzinfo=None),
        member_ids=frozenset(),
        source_type="basket",
    )

    assert _dynamic_snapshot_fields(snapshot)["universe_snapshot_known_at"] == (
        "2024-03-01T00:00:00Z"
    )
