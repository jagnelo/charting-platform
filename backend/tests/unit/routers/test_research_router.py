from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.ohlcv import Timeframe
from app.routers.research import _dataset_manifest_fields, _dataset_options, _wire_timestamps


def test_research_dataset_as_of_clamps_future_bars_and_is_retained_as_metadata():
    options = _dataset_options(
        {"timeframe": "D1", "as_of": "2024-02-01T15:30:00Z"},
        {},
    )

    assert options["as_of"].tzinfo == UTC
    assert options["end"] == options["as_of"]


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
