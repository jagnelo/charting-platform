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
