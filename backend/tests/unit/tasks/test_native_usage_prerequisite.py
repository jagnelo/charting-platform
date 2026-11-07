from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.models.provider_runtime import ProviderCapability
from app.tasks import data_tasks


def _usage_policy():
    return SimpleNamespace(
        quota_scope="account",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 200,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "account",
                    "quota_group": "account",
                    "reset": "rolling",
                },
                {
                    "name": "usage_probe_concurrency",
                    "limit": 1,
                    "window_seconds": 1,
                    "unit": "concurrent_requests",
                    "scope": "deployment",
                    "quota_group": "usage_probe",
                    "reset": "rolling",
                    "applies_to_operations": ["fetch_account_usage"],
                },
            ],
            "account_usage_bootstrap": {
                "enabled": True,
                "source": "application_policy:provider_native_baseline_bootstrap",
                "reconciled_dimensions": ["requests_per_minute"],
            },
        },
    )


@pytest.mark.asyncio
async def test_on_demand_native_usage_job_is_allowlisted_and_window_deduplicated(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS", ["alpaca"])
    now = datetime(2026, 11, 7, 12, 0, 10, tzinfo=UTC)
    dimension = {
        "name": "requests_per_minute",
        "limit": 200,
        "window_seconds": 60,
        "unit": "requests",
        "scope": "account",
        "quota_group": "account",
        "reset": "rolling",
    }
    unknown_state = {
        "status": "unknown",
        "account_scope": "alpaca:account",
        "quota_group": "account",
        "unit": "requests",
        "limit_units": 200,
        "window_seconds": 60,
        "rolling": True,
        "window_started_at": "2026-11-07T12:00:10+00:00",
    }
    monkeypatch.setattr(
        data_tasks,
        "_native_operation_baseline_states",
        AsyncMock(return_value=((SimpleNamespace(), [(dimension, unknown_state)]), None)),
    )
    usage = SimpleNamespace(provider_name="alpaca", policy=_usage_policy())
    monkeypatch.setattr(
        "app.services.provider_runtime.resolve_provider_chain",
        AsyncMock(return_value=[usage]),
    )
    monkeypatch.setattr(
        "app.services.provider_runtime.policy_allows_account_usage_bootstrap",
        lambda *_args: True,
    )
    monkeypatch.setattr(
        "app.services.provider_runtime.account_usage_reconciled_dimensions",
        lambda *_args: {"requests_per_minute"},
    )
    monkeypatch.setattr(
        "app.services.provider_runtime.quota_dimensions",
        lambda policy: policy.quota_contract["dimensions"],
    )
    monkeypatch.setattr(
        "app.services.provider_quota_coordinator.provider_quota_baseline_status",
        lambda **_kwargs: dict(unknown_state),
    )
    enqueued = []

    async def fake_enqueue(_db, **kwargs):
        enqueued.append(kwargs)
        return SimpleNamespace(id=44, status="queued")

    monkeypatch.setattr(data_tasks, "enqueue_refresh_job", fake_enqueue)
    first = await data_tasks._native_usage_job_for_operation_baseline(
        object(),
        provider_name="alpaca",
        capability=ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv",
        priority=10,
        now=now,
    )
    second = await data_tasks._native_usage_job_for_operation_baseline(
        object(),
        provider_name="alpaca",
        capability=ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv",
        priority=50,
        now=now,
    )
    assert first == (first[0], None, True)
    assert second[0].id == 44
    assert enqueued[0]["request_key"] == enqueued[1]["request_key"]
    assert enqueued[0]["capability"] == ProviderCapability.ACCOUNT_USAGE.value
    assert enqueued[0]["priority"] == 10


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("profile_quota_group", "expected_reason"),
    [("account", None), ("unrelated-pool", "native_usage_dimension_contract_mismatch")],
)
async def test_metadata_profile_uses_exact_reviewed_alpaca_shared_pool_under_request_driven_only(
    monkeypatch, profile_quota_group, expected_reason
):
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS", ["alpaca"])
    contract = settings.PROVIDER_RATE_LIMIT_SEEDS["alpaca"]["quota_contract"]
    dimension = dict(
        next(
            item
            for item in contract["dimensions"]
            if item["name"] == "market_data_requests_per_minute"
        )
    )
    dimension["quota_group"] = profile_quota_group
    now = datetime(2026, 11, 7, 12, 0, 10, tzinfo=UTC)
    unknown_state = {
        "status": "unknown",
        "account_scope": "alpaca:account",
        "quota_group": "account",
        "unit": "requests",
        "limit_units": 200,
        "window_seconds": 60,
        "rolling": True,
        "window_started_at": "2026-11-07T12:00:10+00:00",
    }
    metadata_policy = SimpleNamespace(quota_contract=contract, quota_scope="account")
    monkeypatch.setattr(
        data_tasks,
        "_native_operation_baseline_states",
        AsyncMock(return_value=((metadata_policy, [(dimension, unknown_state)]), None)),
    )
    usage = SimpleNamespace(
        provider_name="alpaca",
        policy=SimpleNamespace(quota_contract=contract, quota_scope="account"),
    )
    resolve = AsyncMock(return_value=[usage])
    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", resolve)
    monkeypatch.setattr(
        "app.services.provider_quota_coordinator.provider_quota_baseline_status",
        lambda **_kwargs: dict(unknown_state),
    )
    enqueued = []

    async def fake_enqueue(_db, **kwargs):
        enqueued.append(kwargs)
        return SimpleNamespace(id=61, status="queued")

    monkeypatch.setattr(data_tasks, "enqueue_refresh_job", fake_enqueue)

    db = object()
    job, reason, needed = await data_tasks._native_usage_job_for_operation_baseline(
        db,
        provider_name="alpaca",
        capability=ProviderCapability.INSTRUMENT_METADATA,
        operation="get_instrument_profile",
        priority=10,
        now=now,
    )

    assert reason == expected_reason
    assert needed is True
    if expected_reason is None:
        assert job.id == 61
        assert (
            enqueued[0]["metadata_payload"]["provider_account_usage_refresh"]["trigger_capability"]
            == ProviderCapability.INSTRUMENT_METADATA.value
        )
        assert (
            enqueued[0]["metadata_payload"]["provider_account_usage_refresh"]["trigger_operation"]
            == "get_instrument_profile"
        )
        assert (
            enqueued[0]["metadata_payload"]["provider_account_usage_refresh"]["dimensions"][0][
                "name"
            ]
            == "market_data_requests_per_minute"
        )
    else:
        assert job is None
        assert enqueued == []
    resolve.assert_awaited_once_with(
        db, ProviderCapability.ACCOUNT_USAGE, operation="fetch_account_usage"
    )


@pytest.mark.asyncio
async def test_unknown_native_pool_stays_held_without_explicit_refresh_allowlist(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS", [])
    dimension = {"name": "requests_per_day", "window_seconds": 86_400}
    monkeypatch.setattr(
        data_tasks,
        "_native_operation_baseline_states",
        AsyncMock(
            return_value=(
                (SimpleNamespace(), [(dimension, {"status": "unknown"})]),
                None,
            )
        ),
    )
    enqueue = AsyncMock()
    monkeypatch.setattr(data_tasks, "enqueue_refresh_job", enqueue)

    job, reason, needed = await data_tasks._native_usage_job_for_operation_baseline(
        object(),
        provider_name="unsupported_provider",
        capability=ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv",
        priority=10,
        now=datetime(2026, 11, 7, tzinfo=UTC),
    )

    assert job is None
    assert reason == "native_usage_refresh_not_enabled_for_provider"
    assert needed is True
    enqueue.assert_not_awaited()


@pytest.mark.asyncio
async def test_durable_usage_job_calls_existing_refresh_and_requires_verified_window(
    monkeypatch,
):
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS", ["alpaca"])

    async def refresh_with_scoped_authority(db, *, provider_name):
        from app.services.provider_runtime import _EXPLICIT_ACQUISITION_CONTEXT

        scope = _EXPLICIT_ACQUISITION_CONTEXT.get()
        assert scope is not None
        assert scope.provider_names == frozenset({"alpaca"})
        assert (ProviderCapability.ACCOUNT_USAGE, "fetch_account_usage") in scope.operations
        assert provider_name == "alpaca"
        return {"status": "refreshed", "providers": ["alpaca"]}

    refresh = AsyncMock(side_effect=refresh_with_scoped_authority)
    monkeypatch.setattr(
        "app.services.provider_account_usage.refresh_provider_account_usage", refresh
    )
    dimension = {"name": "requests_per_minute"}
    states = AsyncMock(
        return_value=((SimpleNamespace(), [(dimension, {"status": "verified"})]), None)
    )
    monkeypatch.setattr(data_tasks, "_native_operation_baseline_states", states)

    result = await data_tasks._run_native_usage_refresh_job(
        object(),
        {
            "provider_name": "alpaca",
            "dimensions": [{"name": "requests_per_minute"}],
        },
    )

    assert result == {
        "preparation_status": "ready",
        "reason_code": None,
        "dimensions_verified": ["requests_per_minute"],
    }
    refresh.assert_awaited_once()
    assert refresh.await_args.kwargs["provider_name"] == "alpaca"


@pytest.mark.asyncio
async def test_normal_history_worker_defers_behind_deduplicated_native_usage_job(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS", ["alpaca"])
    instrument = SimpleNamespace(id=17, symbol="XLB")
    now = datetime(2026, 11, 7, 12, tzinfo=UTC)
    job = SimpleNamespace(
        id=90,
        capability=ProviderCapability.PRICE_HISTORY.value,
        instrument_id=instrument.id,
        timeframe="D1",
        start_at=now,
        end_at=now,
        status="leased",
        next_attempt_at=now,
        lease_token="worker-lease",
        priority=10,
        metadata_payload={
            "data_preparation_child": {
                "range_mode": "bounded",
                "adjusted": True,
                "wait_for_job_ids": [],
            }
        },
    )

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, _model, _instrument_id):
            return instrument

        async def refresh(self, _job):
            return None

        async def commit(self):
            return None

    usage_job = SimpleNamespace(id=101, status="queued")
    queued = AsyncMock(return_value=(usage_job, None, True))
    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", Session)
    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", AsyncMock(return_value=[job]))
    monkeypatch.setattr(
        data_tasks,
        "_history_chunk_plan",
        AsyncMock(return_value=(now, now, now, now, "alpaca", None)),
    )
    monkeypatch.setattr(data_tasks, "_native_usage_job_for_operation_baseline", queued)
    retry = AsyncMock()
    monkeypatch.setattr(data_tasks, "retry_refresh_job", retry)
    monkeypatch.setattr(data_tasks, "complete_refresh_job", AsyncMock())
    fetch = AsyncMock()
    monkeypatch.setattr(data_tasks, "fetch_ohlcv", fetch)

    result = await data_tasks.process_refresh_jobs({})

    assert result["claimed"] == 1
    assert result["retried"] == 1
    assert job.metadata_payload["data_preparation_child"]["wait_for_job_ids"] == [101]
    retry.assert_awaited_once()
    fetch.assert_not_awaited()


@pytest.mark.parametrize("profile_only", [False, True])
@pytest.mark.asyncio
async def test_cold_metadata_worker_defers_before_search_or_profile_transport(
    monkeypatch, profile_only
):
    now = datetime(2026, 11, 7, 12, tzinfo=UTC)
    owner = SimpleNamespace(id=33, is_active=True)
    instrument = SimpleNamespace(
        id=17,
        symbol="XLB",
        identity_status="resolved",
        domain_key="us-equity:XNAS:XLB",
        primary_identifier_type="composite_figi",
        primary_identifier_value="BBG000B9XRY4",
    )
    parent = SimpleNamespace(
        metadata_payload={
            "data_preparation": {
                "role": "owner_request_tracking",
                "owner_user_id": owner.id,
            }
        }
    )
    selected_id = instrument.id if profile_only else None
    job = SimpleNamespace(
        id=90,
        capability=ProviderCapability.INSTRUMENT_METADATA.value,
        instrument_id=selected_id,
        timeframe=None,
        status="leased",
        next_attempt_at=now,
        lease_token="metadata-lease",
        priority=10,
        metadata_payload={
            "data_preparation_child": {
                "kind": "identity_profile",
                "request_id": "request-profile-only" if profile_only else "request-search",
                "dependency_id": "dependency-profile" if profile_only else "dependency-identity",
                "symbol": "XLB",
                "instrument_id": selected_id,
                "refresh_profile": profile_only,
                "required_profile_fields": ["industry"] if profile_only else [],
                "parent_refs": [{"parent_job_id": 700, "owner_user_id": owner.id}],
            }
        },
    )

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, model, identifier):
            if model.__name__ == "MarketRefreshJob" and identifier == 700:
                return parent
            if model.__name__ == "User" and identifier == owner.id:
                return owner
            if model.__name__ == "Instrument" and identifier == instrument.id:
                return instrument
            return None

        async def refresh(self, _job):
            return None

        async def commit(self):
            return None

    usage_job = SimpleNamespace(id=101, status="queued", next_attempt_at=now)
    preflight = AsyncMock(return_value=(usage_job, None, True))
    retry = AsyncMock()
    profile_fetch = AsyncMock()
    acquire = AsyncMock()
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS", ["alpaca"])
    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", Session)
    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", AsyncMock(return_value=[job]))
    monkeypatch.setattr(data_tasks, "_native_usage_prerequisite_for_operation", preflight)
    monkeypatch.setattr(data_tasks, "retry_refresh_job", retry)
    monkeypatch.setattr(data_tasks, "complete_refresh_job", AsyncMock())
    monkeypatch.setattr("app.services.market_data.get_provider_profile_async", profile_fetch)
    monkeypatch.setattr("app.routers.instruments.acquire_instrument", acquire)

    result = await data_tasks.process_refresh_jobs({})

    expected_capability = (
        ProviderCapability.INSTRUMENT_METADATA
        if profile_only
        else ProviderCapability.INSTRUMENT_SEARCH
    )
    expected_operation = "get_instrument_profile" if profile_only else "search_instruments"
    assert result["claimed"] == 1
    assert result["retried"] == 1
    assert job.metadata_payload["data_preparation_child"]["wait_for_job_ids"] == [101]
    assert preflight.await_args.kwargs["capability"] == expected_capability
    assert preflight.await_args.kwargs["operation"] == expected_operation
    retry.assert_awaited_once()
    profile_fetch.assert_not_awaited()
    acquire.assert_not_awaited()
