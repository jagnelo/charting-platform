from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.ohlcv import Timeframe
from app.schemas.data_preparation import (
    AnalysisPreparation,
    DataEnsureRequest,
    InstrumentPreparationTarget,
    PreparationDataset,
    PreparationDependencyResponse,
)
from app.services.data_preparation_contracts import (
    DatasetPreparationContext,
    DatasetPreparationResult,
)


def test_ensure_request_accepts_every_existing_chart_timeframe() -> None:
    for timeframe in Timeframe:
        request = DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": 12},
                "timeframe": timeframe.value,
                "datasets": ["history"],
            }
        )
        assert request.timeframe is timeframe
        assert request.target == InstrumentPreparationTarget(
            kind="instrument", instrument_id=12
        )


def test_analysis_contract_uses_existing_names_and_derives_rrg_warmup() -> None:
    analysis = AnalysisPreparation.model_validate(
        {
            "kind": "rrg",
            "lookback": 20,
            "sampling": 3,
            "tail_length": 12,
            "history_length": 80,
        }
    )
    assert analysis.required_raw_bars == (20 * 2 + 12 + 80) * 3
    assert analysis.model_dump().keys() >= {
        "lookback",
        "sampling",
        "tail_length",
        "history_length",
    }
    assert "warmup_bars" not in analysis.model_dump()

    defaults = AnalysisPreparation(kind="rrg")
    assert (defaults.lookback, defaults.sampling, defaults.tail_length, defaults.history_length) == (
        20,
        1,
        10,
        0,
    )
    assert defaults.required_raw_bars == 50


def test_analysis_rejects_competing_or_client_authoritative_warmup_fields() -> None:
    for extra in ({"lookback_bars": 20}, {"warmup_bars": 123}, {"sampling_interval": 3}):
        with pytest.raises(ValidationError):
            AnalysisPreparation.model_validate({"kind": "rrg", **extra})


def test_ratio_requires_two_explicit_legs() -> None:
    with pytest.raises(ValidationError):
        AnalysisPreparation.model_validate({"kind": "ratio"})

    ratio = AnalysisPreparation.model_validate(
        {
            "kind": "ratio",
            "legs": [
                {"instrument_id": 1},
                {"symbol": "spy"},
            ],
        }
    )
    assert ratio.legs is not None
    assert ratio.legs[1].symbol == "SPY"


def test_request_normalizes_symbol_and_rejects_duplicate_datasets() -> None:
    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "symbol": " nvda "},
            "datasets": ["history", "profile"],
            "timeframe": "M15",
        }
    )
    assert request.target.symbol == "NVDA"
    assert request.datasets == [PreparationDataset.HISTORY, PreparationDataset.PROFILE]

    with pytest.raises(ValidationError):
        DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": 1},
                "datasets": ["history", "history"],
            }
        )


def test_request_requires_timezone_and_normalizes_offsets_to_utc() -> None:
    request = DataEnsureRequest.model_validate(
        {
            "target": {"kind": "instrument", "instrument_id": 1},
            "start_at": "2026-11-06T12:00:00+02:00",
            "end_at": "2026-11-06T11:00:00Z",
        }
    )
    assert request.start_at == datetime(2026, 11, 6, 10, tzinfo=UTC)
    assert request.end_at == datetime(2026, 11, 6, 11, tzinfo=UTC)

    with pytest.raises(ValidationError):
        DataEnsureRequest.model_validate(
            {
                "target": {"kind": "instrument", "instrument_id": 1},
                "start_at": "2026-11-06T12:00:00",
            }
        )


def test_dependency_wire_accepts_partial_without_treating_it_as_ready() -> None:
    dependency = PreparationDependencyResponse(
        dependency_id="dep-1",
        dataset=PreparationDataset.HISTORY,
        status="partial",
        updated_at=datetime(2026, 11, 6, tzinfo=UTC),
    )
    assert dependency.status == "partial"


def test_etf_hook_context_and_result_are_constructible_shared_types() -> None:
    context = DatasetPreparationContext(
        request_id="request-1",
        dependency_id="dependency-1",
        dataset=PreparationDataset.HOLDINGS,
        timeframe=Timeframe.D1,
        adjusted=True,
        requested_start=datetime(2025, 1, 1, tzinfo=UTC),
        requested_end=None,
        priority="visible",
        deadline=datetime(2026, 11, 6, tzinfo=UTC),
    )
    result = DatasetPreparationResult(status="waiting", reason_code="quota_window")
    assert context.dataset is PreparationDataset.HOLDINGS
    assert result.retry_at is None

