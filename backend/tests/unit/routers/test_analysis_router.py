from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.workstation import MarketGroup, MarketGroupMember
from app.routers.analysis import (
    _calendar_year_cells,
    _group_members_at,
    _group_provenance,
    _is_known_at,
    _performance_cells,
    _sample_aligned_points,
    _truncate_bars_at,
)


def _bar(instrument_id: int, year: int, month: int, close: str) -> OHLCVBar:
    price = Decimal(close)
    return OHLCVBar(
        instrument_id=instrument_id,
        timeframe=Timeframe.D1,
        ts=datetime(year, month, 2, tzinfo=UTC),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal("100"),
        is_adjusted=True,
    )


def test_calendar_year_cells_are_non_forward_filled_and_observed_at_year_end():
    cells = _calendar_year_cells(
        [
            _bar(7, 2024, 1, "100"),
            _bar(7, 2024, 12, "120"),
            _bar(7, 2026, 1, "200"),
            _bar(7, 2026, 2, "220"),
        ],
        instrument_id=7,
        years=[2024, 2025, 2026],
    )

    assert cells["2024"].value == 0.2
    assert cells["2024"].observation_time == datetime(2024, 12, 2, tzinfo=UTC)
    assert cells["2025"].value is None
    assert cells["2025"].warning is not None
    assert cells["2025"].warning.code == "no_calendar_year_bars"
    assert cells["2026"].value == 0.1


def test_ytd_uses_current_calendar_year_start_not_252_bar_offset():
    bars = [
        _bar(7, 2025, 12, "100"),
        _bar(7, 2026, 1, "200"),
        _bar(7, 2026, 2, "220"),
    ]

    cells = _performance_cells(bars, instrument_id=7)

    assert cells["YTD"].value == 0.1
    assert cells["YTD"].observation_time == datetime(2026, 2, 2, tzinfo=UTC)


def test_period_return_reports_zero_base_price_instead_of_dividing():
    cells = _performance_cells(
        [_bar(7, 2026, 1, "0"), _bar(7, 2026, 2, "10")], instrument_id=7
    )

    assert cells["1D"].value is None
    assert cells["1D"].warning is not None
    assert cells["1D"].warning.code == "zero_base_price"


def test_point_in_time_membership_accepts_unknown_or_prior_versions_only():
    as_of = datetime(2024, 3, 10, tzinfo=UTC)
    assert _is_known_at(None, as_of)
    assert _is_known_at(datetime(2024, 3, 10, tzinfo=UTC), as_of)
    assert not _is_known_at(datetime(2024, 3, 11, tzinfo=UTC), as_of)


def test_point_in_time_membership_normalises_legacy_naive_timestamps():
    as_of = datetime(2024, 3, 10, tzinfo=UTC)
    assert _is_known_at(datetime(2024, 3, 9), as_of)
    assert not _is_known_at(datetime(2024, 3, 11), as_of)


def test_group_members_and_bars_are_cut_at_the_requested_time():
    as_of = datetime(2024, 3, 10, tzinfo=UTC)
    group = MarketGroup(stable_key="test", group_type="test", name="Test")
    group.members = [
        MarketGroupMember(
            instrument_id=7,
            effective_at=datetime(2024, 3, 1, tzinfo=UTC),
            known_at=datetime(2024, 3, 2, tzinfo=UTC),
        ),
        MarketGroupMember(
            instrument_id=8,
            effective_at=datetime(2024, 3, 11, tzinfo=UTC),
            known_at=datetime(2024, 3, 11, tzinfo=UTC),
        ),
    ]
    assert [member.instrument_id for member in _group_members_at(group, as_of)] == [7]
    bars = {7: [_bar(7, 2024, 1, "100"), _bar(7, 2024, 12, "120")]}
    assert [bar.close for bar in _truncate_bars_at(bars, as_of)[7]] == [Decimal("100")]
    assert _group_provenance(group, as_of)["membership_as_of"] == as_of.isoformat()


def test_group_members_reject_a_group_unknown_at_the_requested_time():
    group = MarketGroup(
        stable_key="future",
        group_type="test",
        name="Future",
        effective_at=datetime(2024, 4, 1, tzinfo=UTC),
    )
    with pytest.raises(Exception, match="market_group_not_known_at"):
        _group_members_at(group, datetime(2024, 3, 10, tzinfo=UTC))


def test_relative_rotation_sampling_retains_latest_aligned_observation():
    aligned = [(datetime(2024, 1, day, tzinfo=UTC), float(day)) for day in range(1, 8)]
    assert _sample_aligned_points(aligned, 1) == aligned
    sampled = _sample_aligned_points(aligned, 3)
    assert [timestamp.day for timestamp, _ in sampled] == [1, 4, 7]
