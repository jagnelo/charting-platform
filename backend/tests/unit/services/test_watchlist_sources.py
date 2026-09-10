from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

from app.services import watchlist_sources as sources


def test_watchlist_membership_cutoffs_normalize_persisted_timestamps_to_utc():
    item = SimpleNamespace(
        instrument_id=17,
        added_at=datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
        left_screener_at=datetime(2024, 2, 1, 0, 0, tzinfo=UTC),
    )

    assert sources._watchlist_item_active_at(item, datetime(2024, 1, 15))
    assert sources._watchlist_item_active_at(
        item,
        datetime(2024, 2, 1, 1, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    assert not sources._watchlist_item_active_at(
        item,
        datetime(2024, 2, 1, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    )
    assert sources._watchlist_item_as_of_exclusion(
        item,
        datetime(2024, 2, 1, 2, 0, tzinfo=timezone(timedelta(hours=2))),
    ) == {
        "instrument_id": 17,
        "reason": "membership_not_active_at_as_of",
        "left_screener_at": "2024-02-01T00:00:00+00:00",
    }


def test_saved_explicit_source_known_at_cutoff_normalizes_to_utc():
    item = SimpleNamespace(
        updated_at=datetime(2024, 1, 1, 0, 0, tzinfo=UTC),
        created_at=None,
    )

    before_known_at = datetime(2024, 1, 1, 1, 0, tzinfo=timezone(timedelta(hours=2)))
    at_known_at = datetime(2024, 1, 1, 2, 0, tzinfo=timezone(timedelta(hours=2)))

    assert sources._saved_explicit_known_at_exclusions(item, [17, 23], before_known_at) == (
        {
            "instrument_id": 17,
            "reason": "membership_not_known_at_as_of",
            "known_at": "2024-01-01T00:00:00+00:00",
        },
        {
            "instrument_id": 23,
            "reason": "membership_not_known_at_as_of",
            "known_at": "2024-01-01T00:00:00+00:00",
        },
    )
    assert sources._saved_explicit_known_at_exclusions(item, [17, 23], at_known_at) == ()
