from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.etf_holdings import ETFHoldingsSnapshot
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.workstation import MarketGroup, MarketGroupMember
from app.routers.analysis import (
    _calendar_year_cells,
    _group_members_at,
    _group_provenance,
    _is_known_at,
    _mean,
    _performance_cells,
    _rotation_state,
    _sample_aligned_points,
    _truncate_bars_at,
    _wire_datetime,
)
from app.routers.market_groups import _holdings_snapshot_at


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
    assert _group_provenance(group, as_of)["membership_as_of"] == "2024-03-10T00:00:00Z"


def test_group_members_reject_a_group_unknown_at_the_requested_time():
    group = MarketGroup(
        stable_key="future",
        group_type="test",
        name="Future",
        effective_at=datetime(2024, 4, 1, tzinfo=UTC),
    )
    with pytest.raises(Exception, match="market_group_not_known_at"):
        _group_members_at(group, datetime(2024, 3, 10, tzinfo=UTC))


def test_industry_snapshot_cutoff_requires_known_at_provenance():
    statement = _holdings_snapshot_at(
        select(ETFHoldingsSnapshot), datetime(2024, 3, 10, tzinfo=UTC)
    )
    sql = str(statement.compile(compile_kwargs={"literal_binds": True}))
    assert "known_at IS NOT NULL" in sql
    assert "composition_date <= '2024-03-10'" in sql


def test_relative_rotation_sampling_retains_latest_aligned_observation():
    aligned = [(datetime(2024, 1, day, tzinfo=UTC), float(day)) for day in range(1, 8)]
    assert _sample_aligned_points(aligned, 1) == aligned
    sampled = _sample_aligned_points(aligned, 3)
    assert [timestamp.day for timestamp, _ in sampled] == [1, 4, 7]


def test_relative_rotation_states_cover_all_quadrants_and_mean_is_explicit():
    assert _rotation_state(1.0, 1.0) == "leading"
    assert _rotation_state(1.0, -1.0) == "weakening"
    assert _rotation_state(-1.0, 1.0) == "improving"
    assert _rotation_state(-1.0, -1.0) == "lagging"
    assert _mean([1.0, 2.0, 4.0]) == pytest.approx(7 / 3)


def test_analysis_helpers_preserve_utc_wire_format_and_empty_data_warnings():
    timestamp = datetime(2024, 1, 2, 3, 4, tzinfo=UTC)
    assert _wire_datetime(timestamp) == "2024-01-02T03:04:00Z"
    assert _wire_datetime(None) is None
    assert _truncate_bars_at({7: [_bar(7, 2024, 1, "100")]}, None)[7]
    assert _sample_aligned_points([], 3) == []

    cells = _performance_cells([], instrument_id=7)
    assert set(cells) == {"1D", "1W", "1M", "3M", "6M", "YTD", "1Y"}
    assert all(cell.warning and cell.warning.code == "no_bars" for cell in cells.values())


def test_calendar_year_cells_require_two_nonzero_observations():
    cells = _calendar_year_cells([_bar(7, 2026, 1, "100")], instrument_id=7, years=[2026])
    assert cells["2026"].value is None
    assert cells["2026"].warning is not None
    assert cells["2026"].warning.code == "insufficient_calendar_year_history"
