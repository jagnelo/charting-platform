from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from app.models.market_data_foundation import AdjustmentBasis
from app.models.provider_observation import DatasetStatus
from app.strategy_lab_v2.capability_preparation import CapabilityPreflightService
from app.strategy_lab_v2.contracts import AdjustmentMode
from app.strategy_lab_v2.execution_capabilities import ExecutionCapabilityBinding
from app.strategy_lab_v2.provider_preflight import ProviderLocalCapabilityEvidenceReader
from app.strategy_lab_v2.tests.test_api_router import _client
from app.strategy_lab_v2.tests.test_capability_preparation import _binding, _payload

_PATH = "/api/v1/strategy-lab/v2/capabilities/preflight"
_HEADERS = {"Idempotency-Key": "provider-local-key", "X-Request-ID": "provider-local-request"}
_NOW = datetime(2026, 10, 20, 20, tzinfo=UTC)


class _Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def all(self):
        return self.value

    def scalars(self):
        return self

    def scalar_one_or_none(self):
        return self.value


class _Session:
    def __init__(self, results: list[_Result]) -> None:
        self.results = results
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def execute(self, _statement: object) -> _Result:
        result = self.results[self.calls]
        self.calls += 1
        return result


def _local_records(*, mic: str = "XNYS") -> list[_Result]:
    instrument = SimpleNamespace(
        id=7,
        domain_key="US.AAPL",
        identity_status="resolved",
        is_active=True,
        is_synthetic=False,
    )
    instrument_type = SimpleNamespace(name="Stock")
    asset_class = SimpleNamespace(name="Equity")
    series = SimpleNamespace(
        id=31,
        instrument_id=7,
        exchange_id=9,
        data_source_id=4,
        timeframe="D1",
        session_code="regular",
        feed_scope="consolidated",
        adjustment_basis=AdjustmentBasis.RAW,
        adjustment_version="v1",
        source_series_key="AAPL:D1:consolidated:regular:raw:v1",
        provenance={"provider": "local-provider"},
        is_active=True,
        is_canonical=True,
    )
    source = SimpleNamespace(id=4, is_active=True)
    exchange = SimpleNamespace(id=9, mic=mic)
    state = SimpleNamespace(
        instrument_id=7,
        data_source_id=4,
        dataset_type="ohlcv",
        dataset_key="D1:raw",
        status=DatasetStatus.FRESH,
        stale_after=_NOW + timedelta(days=1),
        fetched_at=_NOW,
        coverage_start=datetime(2024, 1, 2, tzinfo=UTC),
        coverage_end=datetime(2024, 1, 5, tzinfo=UTC),
    )
    bars = [
        SimpleNamespace(
            id=index,
            ts=datetime(2024, 1, day, tzinfo=UTC),
            open=100 + day,
            high=101 + day,
            low=99 + day,
            close=100 + day,
            volume=1000,
            vwap=None,
            adjustment_basis="raw",
            adjustment_version="v1",
            scope_key="provider:series-31",
        )
        for index, day in enumerate((2, 3, 4, 5), start=1)
    ]
    return [
        _Result([(instrument, instrument_type, asset_class)]),
        _Result([series]),
        _Result(source),
        _Result(exchange),
        _Result([state]),
        _Result(bars),
    ]


def _raw_payload() -> dict[str, Any]:
    payload = _payload()
    requirement = payload["requirements"][0]
    requirement.update(
        {
            "start": datetime(2024, 1, 2, tzinfo=UTC).isoformat(),
            "end": datetime(2024, 1, 6, tzinfo=UTC).isoformat(),
            "adjustment": "raw",
            "corporate_action_semantics": "raw_unadjusted",
        }
    )
    return payload


def test_persisted_provider_rows_flow_through_local_reader_and_real_preflight_api() -> None:
    session = _Session(_local_records())
    reader = ProviderLocalCapabilityEvidenceReader(
        lambda: session,
        execution_models=("bar-close",),
        account_models=("cash-equity",),
        clock=lambda: _NOW,
    )

    async def binding(**_kwargs: Any) -> ExecutionCapabilityBinding:
        return _binding()

    adapter = SimpleNamespace(
        preflight_capability=CapabilityPreflightService(
            capability_cells=reader,
            execution_binding=binding,
        )
    )
    with _client(adapter) as client:
        response = client.post(_PATH, headers=_HEADERS, json=_raw_payload())

    assert response.status_code == 200
    attributes = response.json()["data"]["attributes"]
    assert attributes["decision"] == "rigorous"
    assert attributes["executable"] is True
    assert attributes["ranking_eligible"] is True
    assert attributes["can_publish_authoritative_results"] is True
    assert session.calls == 6


@pytest.mark.asyncio
async def test_local_reader_rejects_exchange_without_a_proven_calendar() -> None:
    session = _Session(_local_records(mic="XNAS"))
    reader = ProviderLocalCapabilityEvidenceReader(
        lambda: session,
        execution_models=("bar-close",),
        account_models=("cash-equity",),
        clock=lambda: _NOW,
    )
    from dataclasses import replace

    from app.strategy_lab_v2.tests.test_capability_preparation import _requirement

    requirement = replace(
        _requirement(),
        start=datetime(2024, 1, 2, tzinfo=UTC),
        end=datetime(2024, 1, 6, tzinfo=UTC),
        adjustment=AdjustmentMode.RAW,
        corporate_action_semantics="raw_unadjusted",
    )

    evidence = await reader(
        principal="user-1",
        request_id="request-1",
        idempotency_key="key-1",
        requirements=(requirement,),
    )

    assert evidence == ()
    assert session.calls == 4
