from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.ohlcv import Timeframe
from app.providers.registry import list_provider_capabilities
from app.tasks import data_tasks

CHUNK_START = datetime(2021, 6, 3, tzinfo=UTC)
PREVIOUS_END = CHUNK_START - timedelta(microseconds=1)


def _skip(**overrides):
    kwargs = {
        "timeframe": Timeframe.D1,
        "chunk_start": CHUNK_START,
        "previous_end": PREVIOUS_END,
        "listing_floor": None,
        "earliest_bar": None,
    }
    kwargs.update(overrides)
    return data_tasks._older_history_chunk_is_pre_listing(**kwargs)


def test_unknown_listing_and_no_bar_evidence_keeps_existing_backfill():
    assert _skip() is None


def test_older_chunk_before_listing_floor_is_skipped():
    floor = datetime(2023, 2, 2, tzinfo=UTC)
    assert _skip(listing_floor=floor) == "pre_listing_history_slice"


def test_older_chunk_after_listing_floor_is_kept():
    floor = datetime(2019, 1, 2, tzinfo=UTC)
    assert _skip(listing_floor=floor) is None


def test_listing_floor_margin_keeps_chunk_ending_just_before_floor():
    floor = PREVIOUS_END + timedelta(days=3)
    assert _skip(listing_floor=floor) is None


def test_daily_series_starting_far_inside_chunk_skips_older_chunk():
    earliest = CHUNK_START + timedelta(days=600)
    assert _skip(earliest_bar=earliest) == "series_starts_inside_chunk"


def test_daily_series_starting_at_chunk_start_keeps_older_chunk():
    assert _skip(earliest_bar=CHUNK_START + timedelta(days=4)) is None


def test_intraday_gap_does_not_stop_backfill():
    earliest = CHUNK_START + timedelta(days=600)
    assert _skip(timeframe=Timeframe.M15, earliest_bar=earliest) is None


class _Result:
    def __init__(self, scalars=None, scalar=None):
        self._scalars = scalars or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._scalars

    def scalar_one_or_none(self):
        return self._scalar


class _Db:
    def __init__(self, listings, ipo):
        self._results = [_Result(scalars=listings), _Result(scalar=ipo)]

    async def execute(self, _statement):
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_listing_floor_is_earliest_of_listing_and_ipo_evidence():
    instrument = type("I", (), {"id": 1})()
    db = _Db([datetime(2023, 2, 2, tzinfo=UTC)], date(2022, 12, 1))
    floor = await data_tasks._known_listing_floor(db, instrument)
    assert floor == datetime(2022, 12, 1, tzinfo=UTC)


@pytest.mark.asyncio
async def test_listing_floor_is_none_without_evidence():
    instrument = type("I", (), {"id": 1})()
    assert await data_tasks._known_listing_floor(_Db([], None), instrument) is None


def test_alpaca_is_not_a_routable_instrument_metadata_provider():
    assert "instrument_metadata" not in list_provider_capabilities("alpaca")
    assert "instrument_metadata" in list_provider_capabilities("edgar")
