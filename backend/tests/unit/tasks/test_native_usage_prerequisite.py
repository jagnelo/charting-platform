from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.config import settings
from app.models.market_data_foundation import MarketRefreshJob
from app.models.provider_runtime import ProviderCapability
from app.tasks import data_tasks
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.parametrize(
    ("result", "provider_name", "expected"),
    [
        ({"status": "refreshed", "providers": ["fmp"]}, "fmp", True),
        ({"status": "refreshed", "providers": ["fmp", "fmp"]}, "fmp", True),
        ({"status": "refreshed", "providers": ["fmp", "eodhd"]}, "fmp", False),
        ({"status": "failed", "providers": ["fmp"]}, "fmp", False),
    ],
)
def test_native_usage_refresh_success_requires_exact_provider_set(result, provider_name, expected):
    assert (
        data_tasks._native_usage_refresh_succeeded_for_provider(result, provider_name) is expected
    )


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


@pytest.mark.parametrize(
    ("capability", "operation", "instrument_id"),
    [
        (ProviderCapability.INSTRUMENT_SEARCH, "search_instruments", None),
        (ProviderCapability.INSTRUMENT_METADATA, "get_instrument_profile", 29),
    ],
)
@pytest.mark.asyncio
async def test_unbootstrappable_provider_does_not_block_later_verified_metadata_fallback(
    monkeypatch, capability, operation, instrument_id
):
    """A held first candidate cannot mask an exact-chain candidate with a usable pool."""

    from app.services.provider_runtime import _EXPLICIT_ACQUISITION_CONTEXT

    candidates = [
        SimpleNamespace(provider_name="finnhub"),
        SimpleNamespace(provider_name="alpaca"),
    ]

    async def resolve(_db, resolved_capability, **kwargs):
        scope = _EXPLICIT_ACQUISITION_CONTEXT.get()
        assert scope is not None
        assert scope.operations == frozenset({(resolved_capability, operation)})
        assert scope.instrument_id == instrument_id
        assert scope.symbol == "SPY"
        return candidates

    resolution = AsyncMock(side_effect=resolve)
    baseline_calls = []

    async def baseline(_db, provider_name, **_kwargs):
        baseline_calls.append(provider_name)
        if provider_name == "finnhub":
            return None, "native_usage_bootstrap_not_admitted", True
        return None, None, False

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", resolution)
    monkeypatch.setattr(data_tasks, "_native_usage_job_for_operation_baseline", baseline)
    monkeypatch.setattr(
        data_tasks,
        "_native_operation_baseline_states",
        AsyncMock(return_value=(None, "native_usage_bootstrap_not_admitted")),
    )

    result = await data_tasks._native_usage_prerequisite_for_operation(
        object(),
        capability=capability,
        operation=operation,
        instrument_id=instrument_id,
        provider_symbol="SPY",
        priority=10,
        request_id="fallback-test",
        now=datetime(2026, 11, 7, 12, tzinfo=UTC),
    )

    assert result == (None, None, False, None)
    assert baseline_calls == ["finnhub", "alpaca"]
    resolution.assert_awaited_once()


@pytest.mark.parametrize(
    ("capability", "operation", "instrument_id"),
    [
        (ProviderCapability.INSTRUMENT_SEARCH, "search_instruments", None),
        (ProviderCapability.INSTRUMENT_METADATA, "get_instrument_profile", 29),
    ],
)
@pytest.mark.asyncio
async def test_metadata_prerequisite_keeps_all_provider_holds_when_no_fallback_is_admitted(
    monkeypatch, capability, operation, instrument_id
):
    from app.services.provider_runtime import _EXPLICIT_ACQUISITION_CONTEXT

    candidates = [
        SimpleNamespace(provider_name="finnhub"),
        SimpleNamespace(provider_name="alpaca"),
    ]

    async def resolve(_db, resolved_capability, **kwargs):
        scope = _EXPLICIT_ACQUISITION_CONTEXT.get()
        assert scope is not None
        assert scope.operations == frozenset({(resolved_capability, operation)})
        assert scope.instrument_id == instrument_id
        assert scope.symbol == "SPY"
        return candidates

    async def baseline(_db, provider_name, **_kwargs):
        return None, f"{provider_name}_native_usage_bootstrap_not_admitted", True

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", resolve)
    monkeypatch.setattr(data_tasks, "_native_usage_job_for_operation_baseline", baseline)
    monkeypatch.setattr(
        data_tasks,
        "_native_operation_baseline_states",
        AsyncMock(return_value=(None, "native_usage_bootstrap_not_admitted")),
    )

    job, reason, needed, context = await data_tasks._native_usage_prerequisite_for_operation(
        object(),
        capability=capability,
        operation=operation,
        instrument_id=instrument_id,
        provider_symbol="SPY",
        priority=10,
        request_id="all-held-test",
        now=datetime(2026, 11, 7, 12, tzinfo=UTC),
    )

    assert job is None
    assert reason == "finnhub_native_usage_bootstrap_not_admitted"
    assert needed is True
    assert context["provider_name"] == "finnhub"
    assert context["provider_holds"] == [
        {
            "provider_name": "finnhub",
            "capability": capability.value,
            "operation": operation,
            "dimension_names": [],
            "reason_code": "finnhub_native_usage_bootstrap_not_admitted",
        },
        {
            "provider_name": "alpaca",
            "capability": capability.value,
            "operation": operation,
            "dimension_names": [],
            "reason_code": "alpaca_native_usage_bootstrap_not_admitted",
        },
    ]


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
        lambda *_args, **_kwargs: {"requests_per_minute"},
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
@pytest.mark.parametrize(
    ("normally_admitted", "expected_reason"),
    [(True, None), (False, "native_usage_bootstrap_not_admitted")],
)
async def test_native_usage_prerequisite_uses_normal_admission_without_bootstrap_exception(
    monkeypatch, normally_admitted, expected_reason
):
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_ACCOUNT_USAGE_REFRESH_PROVIDERS", ["fmp"])
    now = datetime(2026, 11, 7, 12, tzinfo=UTC)
    dimension = {"name": "requests_per_minute", "unit": "requests", "window_seconds": 60}
    unknown_state = {
        "status": "unknown",
        "account_scope": "fmp:account",
        "quota_group": "account",
        "unit": "requests",
        "limit_units": 100,
        "window_seconds": 60,
        "rolling": True,
        "window_started_at": "2026-11-07T12:00:00+00:00",
    }
    policy = SimpleNamespace(quota_contract={"account_usage_bootstrap": {"enabled": False}})
    usage = SimpleNamespace(provider_name="fmp", policy=policy, data_source=SimpleNamespace())
    monkeypatch.setattr(
        data_tasks,
        "_native_operation_baseline_states",
        AsyncMock(return_value=((SimpleNamespace(), [(dimension, unknown_state)]), None)),
    )
    monkeypatch.setattr(
        "app.services.provider_runtime.resolve_provider_chain",
        AsyncMock(return_value=[usage]),
    )
    monkeypatch.setattr(
        "app.services.provider_runtime.policy_allows_account_usage_bootstrap",
        lambda *_args: False,
    )
    monkeypatch.setattr(
        "app.services.provider_runtime.policy_has_known_quota",
        lambda _policy: normally_admitted,
    )
    monkeypatch.setattr(
        "app.services.provider_runtime.provider_contract_operation_cost_known",
        lambda *_args: normally_admitted,
    )
    reconciled = Mock(return_value={"requests_per_minute"})
    monkeypatch.setattr(
        "app.services.provider_runtime.account_usage_reconciled_dimensions", reconciled
    )
    monkeypatch.setattr(
        "app.services.provider_runtime.quota_dimensions", lambda _policy: [dimension]
    )
    monkeypatch.setattr(
        "app.services.provider_quota_coordinator.provider_quota_baseline_status",
        lambda **_kwargs: {**unknown_state, "status": "verified"},
    )
    monkeypatch.setattr(
        "app.services.provider_routing.quota_group_for_dimension",
        lambda *_args: "same-reviewed-pool",
    )
    enqueued = []

    async def fake_enqueue(_db, **kwargs):
        enqueued.append(kwargs)
        return SimpleNamespace(id=77, status="queued")

    monkeypatch.setattr(data_tasks, "enqueue_refresh_job", fake_enqueue)

    job, reason, needed = await data_tasks._native_usage_job_for_operation_baseline(
        object(),
        provider_name="fmp",
        capability=ProviderCapability.INSTRUMENT_SEARCH,
        operation="search_instruments",
        priority=10,
        now=now,
    )

    assert reason == expected_reason
    assert needed is True
    if normally_admitted:
        assert job.id == 77
        reconciled.assert_called_once_with(policy, "fetch_account_usage", require_bootstrap=False)
        assert enqueued[0]["capability"] == ProviderCapability.ACCOUNT_USAGE.value
    else:
        assert job is None
        assert enqueued == []
        reconciled.assert_not_called()


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
        return {"status": "refreshed", "providers": ["alpaca", "alpaca"]}

    refresh = AsyncMock(side_effect=refresh_with_scoped_authority)
    monkeypatch.setattr(
        "app.services.provider_account_usage.refresh_provider_account_usage", refresh
    )
    dimension = {"name": "requests_per_minute"}
    states = AsyncMock(
        return_value=((SimpleNamespace(), [(dimension, {"status": "verified"})]), None)
    )
    monkeypatch.setattr(data_tasks, "_native_operation_baseline_states", states)
    resume = AsyncMock(return_value=0)
    monkeypatch.setattr(data_tasks, "resume_native_usage_held_identity_jobs", resume)

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
    preflight = AsyncMock(return_value=(usage_job, None, True, None))
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


@pytest.mark.parametrize("profile_only", [False, True])
@pytest.mark.asyncio
async def test_native_usage_bootstrap_hold_stays_waiting_and_records_resume_scope(
    monkeypatch, profile_only
):
    now = datetime(2026, 11, 7, 12, tzinfo=UTC)
    owner = SimpleNamespace(id=33, is_active=True)
    instrument = SimpleNamespace(
        id=17,
        symbol="SPY",
        identity_status="resolved",
        domain_key="us-equity:ARCX:SPY",
        primary_identifier_type="composite_figi",
        primary_identifier_value="BBG000BDTBL9",
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
        id=92,
        capability=ProviderCapability.INSTRUMENT_METADATA.value,
        instrument_id=selected_id,
        timeframe=None,
        status="leased",
        next_attempt_at=now,
        lease_token="metadata-hold-lease",
        priority=10,
        metadata_payload={
            "data_preparation_child": {
                "kind": "identity_profile",
                "request_id": "request-profile-hold" if profile_only else "request-search-hold",
                "dependency_id": "dependency-profile-hold"
                if profile_only
                else "dependency-identity-hold",
                "symbol": "SPY",
                "instrument_id": selected_id,
                "refresh_profile": profile_only,
                "required_profile_fields": [],
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

    operation = "get_instrument_profile" if profile_only else "search_instruments"
    capability = (
        ProviderCapability.INSTRUMENT_METADATA
        if profile_only
        else ProviderCapability.INSTRUMENT_SEARCH
    )
    hold_context = {
        "provider_name": "alpaca",
        "capability": capability.value,
        "operation": operation,
        "dimension_names": ["market_data_requests_per_minute"],
    }
    preflight = AsyncMock(
        return_value=(None, "native_usage_bootstrap_not_admitted", True, hold_context)
    )
    record_outcome = AsyncMock()
    complete = AsyncMock()
    profile_fetch = AsyncMock()
    acquire = AsyncMock()
    monkeypatch.setattr(data_tasks, "AsyncSessionLocal", Session)
    monkeypatch.setattr(data_tasks, "claim_refresh_jobs", AsyncMock(return_value=[job]))
    monkeypatch.setattr(data_tasks, "_native_usage_prerequisite_for_operation", preflight)
    monkeypatch.setattr(
        "app.services.data_preparation.record_identity_preparation_outcome", record_outcome
    )
    monkeypatch.setattr(data_tasks, "complete_refresh_job", complete)
    monkeypatch.setattr("app.services.market_data.get_provider_profile_async", profile_fetch)
    monkeypatch.setattr("app.routers.instruments.acquire_instrument", acquire)

    result = await data_tasks.process_refresh_jobs({})

    assert result["claimed"] == 1
    assert result["completed"] == 1
    assert result["retried"] == 0
    assert job.metadata_payload["data_preparation_child"]["native_usage_hold"] == {
        **hold_context,
        "reason_code": "native_usage_bootstrap_not_admitted",
    }
    assert record_outcome.await_args.kwargs["status"] == "held"
    assert record_outcome.await_args.kwargs["reason_code"] == "native_usage_bootstrap_not_admitted"
    assert complete.await_args.kwargs["result_summary"]["preparation_status"] == "held"
    assert complete.await_args.kwargs["result_summary"]["native_usage_prerequisite"] == {
        **hold_context,
        "reason_code": "native_usage_bootstrap_not_admitted",
    }
    assert profile_fetch.await_count == 0
    acquire.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "profile_only",
        "held_provider",
        "baseline_statuses",
        "expected_resumed",
        "has_recorded_hold",
    ),
    [
        (True, "alpaca", {"alpaca": "verified"}, 1, True),
        (True, "alpaca", {"alpaca": "unknown"}, 0, True),
        (True, "", {"alpaca": "verified"}, 1, False),
        (True, "finnhub", {"finnhub": "unknown", "alpaca": "verified"}, 1, True),
        (True, "finnhub", {"finnhub": "unknown", "alpaca": "unknown"}, 0, True),
        (False, "finnhub", {"finnhub": "unknown", "alpaca": "verified"}, 1, True),
        (False, "finnhub", {"finnhub": "unknown", "alpaca": "unknown"}, 0, True),
    ],
)
async def test_verified_native_usage_resumes_only_matching_held_identity_child(
    db,
    monkeypatch,
    profile_only,
    held_provider,
    baseline_statuses,
    expected_resumed,
    has_recorded_hold,
):
    now = datetime(2026, 11, 7, 12, tzinfo=UTC)
    parent = MarketRefreshJob(
        request_key="native-resume-parent",
        capability="data_preparation_request",
        priority=10,
        status="completed",
        attempts=0,
        next_attempt_at=now,
        metadata_payload={
            "data_preparation": {
                "role": "owner_request_tracking",
                "owner_user_id": 29,
                "version": 2,
                "dependencies": [
                    {
                        "dependency_id": "identity-dep",
                        "dataset": "identity",
                        "status": "waiting",
                        "reason_code": "native_usage_bootstrap_not_admitted",
                        "job_ids": [],
                    },
                    {
                        "dependency_id": "profile-dep",
                        "dataset": "profile",
                        "status": "unavailable",
                        "reason_code": "native_usage_bootstrap_not_admitted",
                        "job_ids": [],
                    },
                    {
                        "dependency_id": "history-dep",
                        "dataset": "history",
                        "status": "unavailable",
                        "reason_code": "native_usage_bootstrap_not_admitted",
                        "depends_on": ["identity-dep"],
                        "job_ids": [],
                    },
                ],
            }
        },
    )
    db.add(parent)
    db.flush()
    child = MarketRefreshJob(
        request_key="native-resume-identity-child",
        capability=ProviderCapability.INSTRUMENT_METADATA.value,
        priority=10,
        status="completed",
        attempts=1,
        next_attempt_at=now,
        result_summary={
            "preparation_status": "held",
            "reason_code": "native_usage_bootstrap_not_admitted",
        },
        metadata_payload={
            "data_preparation_child": {
                "kind": "identity_profile",
                "request_id": "owner-request-29",
                "symbol": "SPY",
                "instrument_id": 17 if profile_only else None,
                "refresh_profile": profile_only,
                "parent_refs": [{"parent_job_id": parent.id, "owner_user_id": 29}],
                "native_usage_hold": {
                    "provider_name": held_provider or "alpaca",
                    "capability": (
                        ProviderCapability.INSTRUMENT_METADATA.value
                        if profile_only
                        else ProviderCapability.INSTRUMENT_SEARCH.value
                    ),
                    "operation": (
                        "get_instrument_profile" if profile_only else "search_instruments"
                    ),
                    "dimension_names": ["market_data_requests_per_minute"],
                    "reason_code": "native_usage_bootstrap_not_admitted",
                },
            }
        },
    )
    db.add(child)
    db.flush()
    if not has_recorded_hold:
        child_payload = deepcopy(child.metadata_payload)
        child_payload["data_preparation_child"].pop("native_usage_hold")
        child.metadata_payload = child_payload
        db.flush()
    parent_data = deepcopy(parent.metadata_payload["data_preparation"])
    for dependency in parent_data["dependencies"]:
        if dependency["dataset"] in {"identity", "profile"}:
            dependency["job_ids"] = [child.id]
    parent.metadata_payload = {"data_preparation": parent_data}
    db.flush()

    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)

    async def resolved_chain(_db, capability, **kwargs):
        from app.services.provider_runtime import _EXPLICIT_ACQUISITION_CONTEXT

        scope = _EXPLICIT_ACQUISITION_CONTEXT.get()
        assert scope is not None
        assert scope.provider_names is None
        assert scope.operations == frozenset({(capability, kwargs["operation"])})
        assert capability is (
            ProviderCapability.INSTRUMENT_METADATA
            if profile_only
            else ProviderCapability.INSTRUMENT_SEARCH
        )
        assert kwargs["read_only"] is True
        providers = ["alpaca"]
        if held_provider == "finnhub":
            providers = ["finnhub", "alpaca"]
        return [SimpleNamespace(provider_name=provider) for provider in providers]

    async def baseline(_db, provider, *, capability, operation, now):
        assert capability is (
            ProviderCapability.INSTRUMENT_METADATA
            if profile_only
            else ProviderCapability.INSTRUMENT_SEARCH
        )
        assert operation == ("get_instrument_profile" if profile_only else "search_instruments")
        assert provider in baseline_statuses
        return (
            (
                SimpleNamespace(),
                [
                    (
                        {"name": "market_data_requests_per_minute"},
                        {"status": baseline_statuses[provider]},
                    )
                ],
            ),
            None,
        )

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", resolved_chain)
    monkeypatch.setattr(data_tasks, "_native_operation_baseline_states", baseline)

    resumed = await data_tasks.resume_native_usage_held_identity_jobs(
        AsyncSessionAdapter(db), provider_name="alpaca", now=now
    )

    assert resumed == expected_resumed
    if expected_resumed:
        assert child.status == "queued"
        assert child.result_summary["reason_code"] == "native_usage_baseline_verified"
        child_metadata = child.metadata_payload["data_preparation_child"]
        assert "native_usage_hold" not in child_metadata
        if held_provider == "finnhub":
            assert child_metadata["native_usage_hold_history"] == [
                {
                    "provider_name": "finnhub",
                    "capability": (
                        ProviderCapability.INSTRUMENT_METADATA.value
                        if profile_only
                        else ProviderCapability.INSTRUMENT_SEARCH.value
                    ),
                    "operation": (
                        "get_instrument_profile" if profile_only else "search_instruments"
                    ),
                    "dimension_names": ["market_data_requests_per_minute"],
                    "reason_code": "native_usage_bootstrap_not_admitted",
                }
            ]
        statuses = {
            item["dataset"]: (item["status"], item.get("reason_code"))
            for item in parent.metadata_payload["data_preparation"]["dependencies"]
        }
        assert statuses["identity"] == ("queued", None)
        if profile_only:
            assert statuses["profile"] == ("queued", None)
        assert statuses["history"] == ("waiting", "identity_dependency_pending")
    else:
        assert child.status == "completed"
        assert child.metadata_payload["data_preparation_child"].get("native_usage_hold", {}).get(
            "provider_name"
        ) == (held_provider or "alpaca")
