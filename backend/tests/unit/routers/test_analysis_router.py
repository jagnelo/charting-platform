from datetime import UTC, datetime
from decimal import Decimal

from app.models.ohlcv import OHLCVBar, Timeframe
from app.routers.analysis import _calendar_year_cells, _performance_cells


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
