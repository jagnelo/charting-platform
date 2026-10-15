"""Exercise the API/consumer boundary without importing unstaged providers."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.strategy_lab_v2.capabilities import CapabilityCell
from app.strategy_lab_v2.capability_preparation import CapabilityPreflightService
from app.strategy_lab_v2.execution_capabilities import ExecutionCapabilityBinding
from app.strategy_lab_v2.tests.test_api_router import _client
from app.strategy_lab_v2.tests.test_capability_preparation import _binding, _cell, _payload

_PATH = "/api/v1/strategy-lab/v2/capabilities/preflight"
_HEADERS = {"Idempotency-Key": "consumer-key", "X-Request-ID": "consumer-request"}


@pytest.mark.parametrize("unavailable", ["coverage", "engine"])
def test_resolver_outage_returns_retryable_api_error_without_success_fallback(
    unavailable: str,
) -> None:
    healthy = True
    calls: list[str] = []
    private_detail = "private resolver host and credential detail"

    async def cells(**kwargs: Any) -> tuple[CapabilityCell, ...]:
        assert kwargs["principal"] == "user-1"
        calls.append("coverage")
        if not healthy and unavailable == "coverage":
            raise TimeoutError(private_detail)
        return (_cell(),)

    async def binding(**kwargs: Any) -> ExecutionCapabilityBinding:
        assert kwargs["principal"] == "user-1"
        calls.append("engine")
        if not healthy and unavailable == "engine":
            raise TimeoutError(private_detail)
        return _binding()

    adapter = SimpleNamespace(
        preflight_capability=CapabilityPreflightService(
            capability_cells=cells, execution_binding=binding
        )
    )
    with _client(adapter) as client:
        accepted = client.post(_PATH, headers=_HEADERS, json=_payload())
        assert accepted.status_code == 200
        assert accepted.json()["data"]["attributes"]["can_publish_authoritative_results"]
        healthy = False
        calls.clear()
        failed = client.post(_PATH, headers=_HEADERS, json=_payload())

    assert failed.status_code == 500
    body = failed.json()
    assert "data" not in body
    error = body["errors"][0]
    assert error["code"] == "internal_error"
    assert error["retryable"] is True
    assert error["request_id"] == "consumer-request"
    assert private_detail not in failed.text
    assert calls == (["coverage"] if unavailable == "coverage" else ["coverage", "engine"])


def test_revoked_coverage_is_exposed_as_unsupported_through_real_preflight_service() -> None:
    available = True

    async def cells(**_kwargs: Any) -> tuple[CapabilityCell, ...]:
        return (_cell(),) if available else ()

    async def binding(**_kwargs: Any) -> ExecutionCapabilityBinding:
        return _binding()

    adapter = SimpleNamespace(
        preflight_capability=CapabilityPreflightService(
            capability_cells=cells, execution_binding=binding
        )
    )
    with _client(adapter) as client:
        accepted = client.post(_PATH, headers=_HEADERS, json=_payload())
        assert accepted.status_code == 200
        available = False
        rejected = client.post(_PATH, headers=_HEADERS, json=_payload())

    assert rejected.status_code == 200
    attributes = rejected.json()["data"]["attributes"]
    assert attributes["decision"] == "unsupported"
    assert attributes["data_gaps"] == ["US.AAPL:instrument_coverage"]
    assert attributes["executable"] is False
    assert attributes["ranking_eligible"] is False
    assert attributes["can_publish_authoritative_results"] is False
