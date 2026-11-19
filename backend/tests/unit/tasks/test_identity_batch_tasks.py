from unittest.mock import AsyncMock

import pytest

from app.models.provider_runtime import ProviderCapability
from app.tasks import data_tasks
from app.tasks.identity_batch_tasks import ensure_openfigi_native_baseline


class _Session:
    async def commit(self):
        return None


def _states(*statuses: str):
    return (
        object(),
        [
            ({"name": f"dimension-{index}"}, {"status": status})
            for index, status in enumerate(statuses)
        ],
    )


@pytest.mark.asyncio
async def test_verified_openfigi_baseline_needs_no_probe(monkeypatch):
    refresh = AsyncMock()
    monkeypatch.setattr(
        data_tasks,
        "_native_operation_baseline_states",
        AsyncMock(return_value=(_states("verified"), None)),
    )
    monkeypatch.setattr(data_tasks, "_run_native_usage_refresh_job", refresh)

    assert await ensure_openfigi_native_baseline(_Session()) is None
    refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_openfigi_baseline_respects_the_operator_allowlist(monkeypatch):
    refresh = AsyncMock()
    monkeypatch.setattr(
        data_tasks,
        "_native_operation_baseline_states",
        AsyncMock(return_value=(_states("unknown"), None)),
    )
    monkeypatch.setattr(data_tasks, "_configured_native_usage_providers", lambda: ("alpaca",))
    monkeypatch.setattr(data_tasks, "_run_native_usage_refresh_job", refresh)

    assert (
        await ensure_openfigi_native_baseline(_Session())
        == "native_usage_refresh_not_enabled_for_provider"
    )
    refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_openfigi_baseline_is_probed_through_the_guarded_usage_path(monkeypatch):
    refresh = AsyncMock(return_value={"preparation_status": "ready"})
    monkeypatch.setattr(
        data_tasks,
        "_native_operation_baseline_states",
        AsyncMock(return_value=(_states("unknown"), None)),
    )
    monkeypatch.setattr(data_tasks, "_configured_native_usage_providers", lambda: ("openfigi",))
    monkeypatch.setattr(data_tasks, "_run_native_usage_refresh_job", refresh)

    assert await ensure_openfigi_native_baseline(_Session()) is None
    request = refresh.await_args.args[1]
    assert request["provider_name"] == "openfigi"
    assert request["trigger_capability"] == ProviderCapability.INSTRUMENT_IDENTIFIERS.value
    assert request["trigger_operation"] == "fetch_stable_identifiers"
    assert request["dimensions"] == [{"name": "dimension-0"}]


@pytest.mark.asyncio
async def test_unqualified_openfigi_probe_keeps_the_pass_held(monkeypatch):
    monkeypatch.setattr(
        data_tasks,
        "_native_operation_baseline_states",
        AsyncMock(return_value=(_states("unknown"), None)),
    )
    monkeypatch.setattr(data_tasks, "_configured_native_usage_providers", lambda: ("openfigi",))
    monkeypatch.setattr(
        data_tasks,
        "_run_native_usage_refresh_job",
        AsyncMock(return_value={"preparation_status": "held", "reason_code": "x_not_verified"}),
    )

    assert await ensure_openfigi_native_baseline(_Session()) == "x_not_verified"
