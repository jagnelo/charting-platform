from datetime import UTC

import pytest
from fastapi import HTTPException

from app.routers.research import _dataset_options


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
