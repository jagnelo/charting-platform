from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import HTTPException

from app.models.instrument import Instrument
from app.models.ohlcv import Timeframe
from app.routers.research import (
    _dataset_manifest_fields,
    _dataset_options,
    _parse_dataset_bound,
    _research_coverage_calendars,
    _wire_timestamps,
)


def test_research_dataset_as_of_clamps_future_bars_and_is_retained_as_metadata():
    options = _dataset_options(
        {"timeframe": "D1", "as_of": "2024-02-01T15:30:00Z"},
        {},
    )

    assert options["as_of"].tzinfo == UTC
    assert options["end"] == options["as_of"]


def test_date_only_research_bounds_cover_the_full_utc_dates_inclusively():
    options = _dataset_options(
        {"timeframe": "D1", "start_date": "2024-11-22", "end_date": "2026-10-22"},
        {},
    )

    assert options["start"] == datetime(2024, 11, 22, tzinfo=UTC)
    assert options["end"] == datetime(2026, 10, 22, 23, 59, 59, 999999, tzinfo=UTC)
    assert options["date_only_bounds"] == {"start": True, "end": True}

    with pytest.raises(HTTPException) as error:
        _parse_dataset_bound("2024-02-30", end=True)
    assert error.value.status_code == 422
    assert error.value.detail["code"] == "invalid_dataset_date"


def test_explicit_research_timestamps_keep_their_instants_and_do_not_become_date_bounds():
    options = _dataset_options(
        {
            "timeframe": "D1",
            "start_date": "2024-11-22T05:00:00Z",
            "end_date": "2024-11-22T21:00:00Z",
        },
        {},
    )

    assert options["start"] == datetime(2024, 11, 22, 5, tzinfo=UTC)
    assert options["end"] == datetime(2024, 11, 22, 21, tzinfo=UTC)
    assert options["date_only_bounds"] == {"start": False, "end": False}

    mixed = _dataset_options(
        {
            "timeframe": "D1",
            "start_date": "2024-11-22T05:00:00Z",
            "end_date": "2024-11-25",
        },
        {},
    )
    assert mixed["start"] == datetime(2024, 11, 22, 5, tzinfo=UTC)
    assert mixed["end"] == datetime(2024, 11, 25, 23, 59, 59, 999999, tzinfo=UTC)
    assert mixed["date_only_bounds"] == {"start": False, "end": True}
    assert (
        _research_coverage_calendars(
            {"timeframe": mixed["timeframe"], "date_only_bounds": mixed["date_only_bounds"]},
            [],
        )
        is None
    )

    reverse_mixed = _dataset_options(
        {
            "timeframe": "D1",
            "start_date": "2024-11-22",
            "end_date": "2024-11-25T21:00:00Z",
        },
        {},
    )
    assert reverse_mixed["start"] == datetime(2024, 11, 22, tzinfo=UTC)
    assert reverse_mixed["end"] == datetime(2024, 11, 25, 21, tzinfo=UTC)
    assert reverse_mixed["date_only_bounds"] == {"start": True, "end": False}
    assert (
        _research_coverage_calendars(
            {
                "timeframe": reverse_mixed["timeframe"],
                "date_only_bounds": reverse_mixed["date_only_bounds"],
            },
            [
                cast(
                    Instrument,
                    SimpleNamespace(id=1, listings=[]),
                )
            ],
        )
        is None
    )

    date_range_with_exact_as_of = _dataset_options(
        {
            "timeframe": "D1",
            "start_date": "2024-11-22",
            "end_date": "2024-11-25",
            "as_of": "2024-11-25T15:00:00Z",
        },
        {},
    )
    assert date_range_with_exact_as_of["end"] == datetime(2024, 11, 25, 15, tzinfo=UTC)
    assert date_range_with_exact_as_of["date_only_bounds"] == {"start": True, "end": False}


def test_date_granular_daily_coverage_uses_only_the_exact_supported_instrument_venue():
    options = {
        "timeframe": Timeframe.D1,
        "date_only_bounds": {"start": True, "end": True},
    }

    def instrument_with_listings(instrument_id: int, *listings: SimpleNamespace) -> Instrument:
        return cast(Instrument, SimpleNamespace(id=instrument_id, listings=list(listings)))

    def primary_listing(mic: str, *, active: bool = True) -> SimpleNamespace:
        return SimpleNamespace(
            is_primary=True,
            is_active=active,
            exchange=SimpleNamespace(mic=mic),
        )

    xnys_equity = instrument_with_listings(1, primary_listing("XNYS"))
    other_us_equity = instrument_with_listings(2, primary_listing("ARCX"))
    unknown_venue = instrument_with_listings(3, primary_listing("UNLISTED"))
    no_primary_listing = instrument_with_listings(
        4,
        SimpleNamespace(
            is_primary=False,
            is_active=True,
            exchange=SimpleNamespace(mic="XNYS"),
        ),
    )
    ambiguous_primary_listings = instrument_with_listings(
        5, primary_listing("XNYS"), primary_listing("XNYS")
    )
    inactive_xnys = instrument_with_listings(6, primary_listing("XNYS", active=False))
    detail_only_xnys = cast(
        Instrument,
        SimpleNamespace(
            id=7,
            listings=[],
            equity_detail=SimpleNamespace(exchange_mic="XNYS"),
        ),
    )

    assert _research_coverage_calendars(options, [xnys_equity]) == {1: "XNYS"}
    assert _research_coverage_calendars(options, [other_us_equity]) == {2: None}
    assert _research_coverage_calendars(options, [unknown_venue]) == {3: None}
    assert _research_coverage_calendars(options, [no_primary_listing]) == {4: None}
    assert _research_coverage_calendars(options, [ambiguous_primary_listings]) == {5: None}
    assert _research_coverage_calendars(options, [inactive_xnys]) == {6: None}
    assert _research_coverage_calendars(options, [detail_only_xnys]) == {7: None}
    assert (
        _research_coverage_calendars({**options, "timeframe": Timeframe.H1}, [xnys_equity]) is None
    )
    assert (
        _research_coverage_calendars(
            {**options, "date_only_bounds": {"start": True, "end": False}}, [xnys_equity]
        )
        is None
    )
    assert (
        _research_coverage_calendars(
            {**options, "date_only_bounds": {"start": False, "end": True}}, [xnys_equity]
        )
        is None
    )


def test_research_dataset_rejects_as_of_before_requested_start():
    with pytest.raises(HTTPException) as error:
        _dataset_options(
            {"timeframe": "D1", "start_date": "2024-03-01", "as_of": "2024-02-01"},
            {},
        )

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "dataset_as_of_before_start"


def test_research_dataset_payload_timestamps_use_canonical_utc_z():
    offset = datetime(2024, 2, 1, 15, 30, tzinfo=timezone(timedelta(hours=2)))

    assert _wire_timestamps([offset, datetime(2024, 2, 1, 14, 30)]) == [
        "2024-02-01T13:30:00Z",
        "2024-02-01T14:30:00Z",
    ]
    fields = _dataset_manifest_fields(
        {"name": "canonical"},
        {
            "timeframe": Timeframe.D1,
            "adjustment": "split_adjusted",
            "session": "regular",
            "start": None,
            "end": None,
            "as_of": offset,
            "benchmark": None,
        },
    )
    assert fields["as_of"] == "2024-02-01T13:30:00Z"
