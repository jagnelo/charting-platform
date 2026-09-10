from datetime import date

import pytest

from app.services.benchmark_family_coverage import (
    OBSERVED_CONTINUITY_MAX_INTERVAL_DAYS,
    assess_observed_holdings_cadence,
    assess_observed_holdings_continuity,
)


def test_observed_cadence_collapses_same_date_revisions_and_reports_statistics():
    result = assess_observed_holdings_cadence(
        [
            date(2026, 1, 31),
            date(2026, 2, 28),
            date(2026, 2, 28),
            date(2026, 3, 31),
            date(2026, 5, 31),
        ]
    )

    assert result.status == "observed_cadence"
    assert result.sample_count == 3
    assert result.median_interval_days == 31.0
    assert result.min_interval_days == 28
    assert result.max_interval_days == 61


@pytest.mark.parametrize(
    ("dates", "status"),
    [([], "no_snapshot"), ([date(2026, 6, 30)], "single_snapshot")],
)
def test_observed_cadence_distinguishes_missing_and_single_snapshot(dates, status):
    result = assess_observed_holdings_cadence(dates)

    assert result.status == status
    assert result.sample_count == 0
    assert result.median_interval_days is None
    assert result.min_interval_days is None
    assert result.max_interval_days is None


def test_observed_continuity_collapses_same_date_revisions():
    result = assess_observed_holdings_continuity(
        [
            date(2026, 1, 31),
            date(2026, 2, 28),
            date(2026, 2, 28),
            date(2026, 3, 31),
        ]
    )

    assert result.status == "observed_continuity"
    assert result.gaps == ()
    assert result.max_interval_days is None


def test_observed_continuity_reports_only_intervals_over_policy():
    result = assess_observed_holdings_continuity(
        [date(2026, 6, 30), date(2027, 6, 30), date(2027, 7, 31)]
    )

    assert result.status == "gapped"
    assert len(result.gaps) == 1
    assert result.gaps[0].from_date == date(2026, 6, 30)
    assert result.gaps[0].to_date == date(2027, 6, 30)
    assert result.gaps[0].interval_days == 365
    assert result.max_interval_days == 365


@pytest.mark.parametrize(
    ("dates", "status"),
    [([], "no_snapshot"), ([date(2026, 6, 30)], "single_snapshot")],
)
def test_observed_continuity_distinguishes_missing_and_single_snapshot(dates, status):
    assert assess_observed_holdings_continuity(dates).status == status


def test_observed_continuity_rejects_invalid_policy():
    with pytest.raises(ValueError, match="max_interval_days must be positive"):
        assess_observed_holdings_continuity(
            [date(2026, 1, 1), date(2026, 1, 2)],
            max_interval_days=0,
        )


def test_observed_continuity_policy_is_explicitly_bounded():
    assert OBSERVED_CONTINUITY_MAX_INTERVAL_DAYS == 45
