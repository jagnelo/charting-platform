from datetime import UTC, datetime, timedelta, timezone

from app.lib.time_utils import wire_datetime


def test_wire_datetime_normalizes_aware_and_naive_values_to_utc_z():
    assert wire_datetime(datetime(2026, 9, 11, 12, 30, tzinfo=UTC)) == ("2026-09-11T12:30:00Z")
    assert wire_datetime(datetime(2026, 9, 11, 12, 30)) == "2026-09-11T12:30:00Z"
    assert wire_datetime(datetime(2026, 9, 11, 14, 30, tzinfo=timezone(timedelta(hours=2)))) == (
        "2026-09-11T12:30:00Z"
    )
    assert wire_datetime(None) is None
