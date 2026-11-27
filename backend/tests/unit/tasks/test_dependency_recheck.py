from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.tasks.data_tasks import (
    DEPENDENCY_RECHECK_MAX,
    DEPENDENCY_RECHECK_MIN,
    dependency_recheck_at,
)

NOW = datetime(2026, 11, 15, 18, 0, tzinfo=UTC)


def _job(status, next_attempt_at=None):
    return SimpleNamespace(status=status, next_attempt_at=next_attempt_at)


def test_prerequisite_deferred_until_next_month_does_not_spin_the_child_every_20_seconds():
    """Production: 1,380 history children rechecked every 20s for 16 days."""
    prerequisite = _job("deferred", NOW + timedelta(days=16))

    retry_at = dependency_recheck_at([prerequisite], expected=1, now=NOW)

    assert retry_at == NOW + DEPENDENCY_RECHECK_MAX


def test_child_waits_for_the_earliest_waiting_prerequisite():
    prerequisites = [
        _job("deferred", NOW + timedelta(minutes=7)),
        _job("retry", NOW + timedelta(minutes=3)),
        _job("completed", NOW - timedelta(days=1)),
    ]

    assert dependency_recheck_at(prerequisites, expected=3, now=NOW) == NOW + timedelta(minutes=3)


def test_child_never_rechecks_sooner_than_the_minimum():
    prerequisite = _job("deferred", NOW - timedelta(minutes=1))

    assert (
        dependency_recheck_at([prerequisite], expected=1, now=NOW) == NOW + DEPENDENCY_RECHECK_MIN
    )


def test_runnable_or_missing_prerequisites_keep_the_short_recheck():
    for prerequisites, expected in (
        ([_job("queued", NOW + timedelta(days=1))], 1),
        ([_job("leased", NOW + timedelta(days=1))], 1),
        ([_job("deferred", None)], 1),
        ([_job("deferred", NOW + timedelta(days=1))], 2),
    ):
        assert (
            dependency_recheck_at(prerequisites, expected=expected, now=NOW)
            == NOW + DEPENDENCY_RECHECK_MIN
        )


def test_naive_next_attempt_is_read_as_utc():
    naive = (NOW + timedelta(minutes=5)).replace(tzinfo=None)

    assert dependency_recheck_at([_job("deferred", naive)], expected=1, now=NOW) == NOW + timedelta(
        minutes=5
    )


def test_coalesced_waiter_parks_until_the_survivor_wakes_it():
    from app.tasks.data_tasks import DEPENDENCY_PARK_MAX

    for survivor in (_job("queued", NOW), _job("leased", NOW), _job("deferred", NOW)):
        assert (
            dependency_recheck_at([survivor], expected=1, now=NOW, parked=True)
            == NOW + DEPENDENCY_PARK_MAX
        )


def test_parked_waiter_with_a_missing_survivor_rechecks_soon():
    assert (
        dependency_recheck_at([], expected=1, now=NOW, parked=True) == NOW + DEPENDENCY_RECHECK_MIN
    )
