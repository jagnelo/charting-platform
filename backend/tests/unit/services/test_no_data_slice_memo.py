"""A provider's stable "no usable data" answer is not re-requested on every read.

Production re-asked Alpaca for the same pre-listing slice every ~12 seconds,
burning quota until real requests were denied. Historical no-data slices are
remembered for a bounded time; recent slices, quota denials and other failures
are never remembered.
"""

from datetime import UTC, datetime

import pytest

from app.models.ohlcv import Timeframe
from app.services import market_data
from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError
from app.services.provider_runtime import ProviderNoDataError
from tests.unit.conftest import AsyncSessionAdapter

HISTORICAL_START = datetime(2023, 6, 1, tzinfo=UTC)
CACHED_END = datetime(2024, 5, 29, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clear_memo():
    market_data._no_data_slices.clear()
    yield
    market_data._no_data_slices.clear()


def _fake_provider(monkeypatch, error: Exception) -> list[tuple[datetime, datetime]]:
    calls: list[tuple[datetime, datetime]] = []

    async def fetch(_db, _instrument, _timeframe, start, end, _adjusted, **_kwargs):
        calls.append((start, end))
        raise error

    monkeypatch.setattr(market_data, "_fetch_provider", fetch)
    return calls


async def _read(db, instrument, start):
    return await market_data._fetch_ohlcv_impl(
        AsyncSessionAdapter(db), instrument, Timeframe.D1, start, end=CACHED_END, adjusted=True
    )


@pytest.mark.asyncio
async def test_historical_no_data_slice_is_requested_once(db, instrument, ohlcv_bars, monkeypatch):
    calls = _fake_provider(
        monkeypatch, ProviderNoDataError("alpaca returned no usable data for fetch_ohlcv:D1")
    )

    first = await _read(db, instrument, HISTORICAL_START)
    second = await _read(db, instrument, HISTORICAL_START)

    assert len(calls) == 1
    assert calls[0][0] == HISTORICAL_START
    assert len(first) == len(second) == len(ohlcv_bars)


@pytest.mark.asyncio
async def test_quota_denial_is_never_remembered(db, instrument, ohlcv_bars, monkeypatch):
    calls = _fake_provider(
        monkeypatch,
        ProviderQuotaAdmissionError(
            "durable provider quota admission denied for price_history/fetch_ohlcv:D1: alpaca",
            retry_at=None,
        ),
    )

    for _ in range(2):
        with pytest.raises(ProviderQuotaAdmissionError):
            await _read(db, instrument, HISTORICAL_START)

    assert len(calls) == 2


@pytest.mark.asyncio
async def test_recent_no_data_slice_is_asked_again(db, instrument, ohlcv_bars, monkeypatch):
    calls = _fake_provider(
        monkeypatch, ProviderNoDataError("alpaca returned no usable data for fetch_ohlcv:D1")
    )
    now = datetime.now(UTC)
    monkeypatch.setattr(market_data, "_NO_DATA_SLICE_MIN_AGE", now - HISTORICAL_START)

    await _read(db, instrument, HISTORICAL_START)
    await _read(db, instrument, HISTORICAL_START)

    assert len(calls) == 2


def _punch_gaps(db, ohlcv_bars, *ranges: range) -> list[tuple[datetime, datetime]]:
    """Delete daily bars by index; return each hole's first and last missing day."""

    holes = []
    for indexes in ranges:
        for index in indexes:
            db.delete(ohlcv_bars[index])
        holes.append((ohlcv_bars[indexes.start].ts, ohlcv_bars[indexes.stop - 1].ts))
    db.flush()
    return holes


def _bar(instrument, ts: datetime):
    from decimal import Decimal

    from app.models.ohlcv import OHLCVBar

    return OHLCVBar(
        instrument_id=instrument.id,
        timeframe=Timeframe.D1,
        ts=ts,
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10"),
        volume=Decimal("1000"),
        is_adjusted=True,
    )


CACHED_START = datetime(2024, 1, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_neighbouring_gaps_share_one_request_and_stay_remembered(
    db, instrument, ohlcv_bars, monkeypatch
):
    """A thin feed's untraded sessions cost one request, not one per gap."""

    holes = _punch_gaps(db, ohlcv_bars, range(20, 30), range(60, 70), range(100, 110))
    calls = _fake_provider(
        monkeypatch, ProviderNoDataError("alpaca returned no usable data for fetch_ohlcv:D1")
    )

    await _read(db, instrument, CACHED_START)
    await _read(db, instrument, CACHED_START)

    assert len(calls) == 1
    assert calls[0][0] <= holes[0][0] and calls[0][1] >= holes[-1][1]


@pytest.mark.asyncio
async def test_gaps_the_answer_left_empty_are_remembered_and_filled_ones_are_not(
    db, instrument, ohlcv_bars, monkeypatch
):
    holes = _punch_gaps(db, ohlcv_bars, range(20, 30), range(60, 70), range(100, 110))
    filled_day = ohlcv_bars[65].ts
    calls: list[tuple[datetime, datetime]] = []

    async def fetch(_db, _instrument, _timeframe, start, end, _adjusted, **_kwargs):
        calls.append((start, end))
        if start <= filled_day <= end:
            return [_bar(instrument, filled_day)]
        raise ProviderNoDataError("alpaca returned no usable data for fetch_ohlcv:D1")

    monkeypatch.setattr(market_data, "_fetch_provider", fetch)

    await _read(db, instrument, CACHED_START)
    calls.clear()
    await _read(db, instrument, CACHED_START)

    # Only what is left of the partly filled middle hole is asked again.
    assert calls
    for start, end in calls:
        assert holes[1][0] <= start and end <= holes[1][1]


@pytest.mark.asyncio
async def test_gaps_further_apart_than_one_bounded_request_are_asked_separately(
    db, instrument, ohlcv_bars, monkeypatch
):
    _punch_gaps(db, ohlcv_bars, range(20, 30), range(60, 70), range(100, 110))
    monkeypatch.setattr(market_data, "_REPAIR_GROUP_MAX_BARS", 30)
    calls = _fake_provider(
        monkeypatch, ProviderNoDataError("alpaca returned no usable data for fetch_ohlcv:D1")
    )

    await _read(db, instrument, CACHED_START)

    assert len(calls) == 3
    assert all(end - start <= market_data.timedelta(days=30) for start, end in calls)
