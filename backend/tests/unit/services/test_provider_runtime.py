from __future__ import annotations

import asyncio
import base64
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlalchemy import select

from app.config import provider_rate_limit_seed, settings
from app.models.data_source import DataSource
from app.models.market_data_foundation import ProviderQuotaWindow
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderEntitlementRevision,
    ProviderHealthState,
    ProviderPolicy,
    ProviderRequestLog,
)
from app.providers import finra_otc_directory
from app.providers.base import ProviderAccountUsage, ProviderAccountUsageDimension
from app.providers.errors import ProviderRateLimitError, ProviderResponseError
from app.providers.finra import FINRAProvider
from app.providers.finra_otc_directory import FINRAOTCDirectoryProvider
from app.providers.registry import get_provider_usage_profile
from app.providers.telemetry import observe_binary_response_payload, observe_response
from app.services.provider_quota_coordinator import (
    ProviderQuotaAdmissionError,
    provider_quota_coordinator_summary,
)
from app.services.provider_runtime import (
    ProviderQuotaUnknownError,
    ResolvedProvider,
    TokenBucket,
    _apply_marketstack_api_error_usage,
    _apply_policy_defaults,
    _apply_provider_capacity_hold,
    _capacity_response_headers,
    _coordinator_settlement,
    _entitlement_seed,
    _get_bucket,
    _get_semaphore,
    execute_provider_call,
    list_provider_status,
    policy_allows_account_usage_bootstrap,
    policy_allows_unreviewed_account_usage_checkpoint,
    provider_entitlement_admission,
    provider_runtime_quota_admission_active,
    quota_contract_missing_dimensions,
    resolve_provider_chain,
    seed_provider_runtime,
)
from tests.unit.conftest import AsyncSessionAdapter


def _grant_test_perpetual_archive(monkeypatch, prefix: str) -> None:
    """Supply a deliberately explicit provider grant for routing unit tests."""

    monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_AUTHORIZED", True)
    monkeypatch.setattr(
        settings,
        f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_REFERENCE",
        "unit-test written provider grant",
    )
    monkeypatch.setattr(
        settings,
        f"{prefix}_PERSISTENT_STORAGE_AUTHORITY_SCOPE",
        "written_single_user_automated_internal_display_perpetual_archive",
    )
    monkeypatch.setattr(
        settings,
        f"{prefix}_PERSISTENT_STORAGE_REVIEWED_AT",
        datetime(2026, 10, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(settings, f"{prefix}_PERSISTENT_STORAGE_EXPIRES_AT", None)


def test_capacity_response_headers_retain_provider_native_usage_state_only():
    assert _capacity_response_headers(
        {
            "X-Bapi-Limit": "50",
            "X-Bapi-Limit-Status": "49",
            "X-Bapi-Limit-Reset-Timestamp": "1700000000000",
            "X-Api-Ratelimit-Limit": "100",
            "X-Api-Ratelimit-Remaining": "87",
            "X-Api-Ratelimit-Reset": "1700000000",
            "X-Api-Ratelimit-Consumed": "4",
            "X-RateLimit-Limit-Second": "5",
            "X-RateLimit-Remaining-Second": "4",
            "X-RateLimit-Reset-Second": "1791837416",
            "Authorization": "secret",
        }
    ) == {
        "x-bapi-limit": "50",
        "x-bapi-limit-status": "49",
        "x-bapi-limit-reset-timestamp": "1700000000000",
        "x-api-ratelimit-limit": "100",
        "x-api-ratelimit-remaining": "87",
        "x-api-ratelimit-reset": "1700000000",
        "x-api-ratelimit-consumed": "4",
        "x-ratelimit-limit-second": "5",
        "x-ratelimit-remaining-second": "4",
        "x-ratelimit-reset-second": "1791837416",
    }


def test_unresettable_capacity_rejection_disables_only_shared_quota_scope_policies(db):
    source = DataSource(name="marketstack", is_active=True)
    db.add(source)
    db.flush()
    request_policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.UNIVERSE_DISCOVERY,
        is_enabled=True,
        quota_scope="api_key",
    )
    history_policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        is_enabled=True,
        quota_scope="api_key",
    )
    independent_policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.ACCOUNT_USAGE,
        is_enabled=True,
        quota_scope="separate_pool",
    )
    db.add_all([request_policy, history_policy, independent_policy])
    db.flush()

    asyncio.run(
        _apply_provider_capacity_hold(
            AsyncSessionAdapter(db),
            data_source_id=source.id,
            policy=request_policy,
            error=ProviderRateLimitError(
                "marketstack",
                "monthly usage limit reached",
                status_code=429,
                scope="api_key",
            ),
        )
    )

    assert request_policy.is_enabled is False
    assert history_policy.is_enabled is False
    assert independent_policy.is_enabled is True


def test_provider_reset_circuit_is_shared_across_same_quota_scope(db):
    source = DataSource(name="marketstack-reset-test", is_active=True)
    db.add(source)
    db.flush()
    discovery = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.UNIVERSE_DISCOVERY,
        is_enabled=True,
        quota_scope="api_key",
    )
    history = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        is_enabled=True,
        quota_scope="api_key",
    )
    separate = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.ACCOUNT_USAGE,
        is_enabled=True,
        quota_scope="separate_pool",
    )
    db.add_all([discovery, history, separate])
    db.flush()
    discovery_health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.UNIVERSE_DISCOVERY,
    )
    history_health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
    )
    separate_health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.ACCOUNT_USAGE,
    )
    db.add_all([discovery_health, history_health, separate_health])
    db.flush()
    reset_at = datetime(2026, 10, 16, tzinfo=UTC)

    asyncio.run(
        _apply_provider_capacity_hold(
            AsyncSessionAdapter(db),
            data_source_id=source.id,
            policy=discovery,
            error=ProviderRateLimitError(
                "marketstack-reset-test",
                "temporary provider capacity limit",
                retry_at=reset_at,
                status_code=429,
                scope="api_key",
            ),
        )
    )

    assert discovery_health.circuit_open_until == reset_at
    assert history_health.circuit_open_until == reset_at
    assert separate_health.circuit_open_until is None


def test_eodhd_entitlement_403_does_not_consume_daily_call_credit():
    policy = SimpleNamespace(
        quota_contract={
            "reset": "per_dimension",
            "dimensions": [
                {
                    "name": "calls_per_day",
                    "limit": 20,
                    "window_seconds": 86400,
                    "unit": "calls",
                    "scope": "api_key",
                    "source": "https://eodhd.com/financial-apis/api-limits",
                    "reset": "calendar_day_gmt",
                },
                {
                    "name": "requests_per_minute",
                    "limit": 1000,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "https://eodhd.com/financial-apis/api-limits",
                    "reset": "rolling",
                },
            ],
        }
    )
    measurement = SimpleNamespace(http_requests=1, response_bytes=128)
    entitlement_error = ProviderResponseError(
        "eodhd", "plan does not include Fundamentals", status_code=403
    )

    observed, unknown = _coordinator_settlement(
        policy,
        measurement,
        {"calls_per_day": 10, "requests_per_minute": 1},
        provider_name="eodhd",
        operation="get_instrument_profile",
        error=entitlement_error,
    )

    assert observed == {"calls_per_day": 0, "requests_per_minute": 1}
    assert unknown == set()


def test_eodhd_quota_exception_rule_is_narrowly_scoped():
    policy = SimpleNamespace(
        quota_contract={
            "reset": "per_dimension",
            "dimensions": [
                {
                    "name": "calls_per_day",
                    "limit": 20,
                    "window_seconds": 86400,
                    "unit": "calls",
                    "scope": "api_key",
                    "source": "https://eodhd.com/financial-apis/api-limits",
                    "reset": "calendar_day_gmt",
                }
            ],
        }
    )
    measurement = SimpleNamespace(http_requests=1, response_bytes=128)
    error = ProviderResponseError("eodhd", "forbidden", status_code=403)

    observed, _ = _coordinator_settlement(
        policy,
        measurement,
        {"calls_per_day": 10},
        provider_name="eodhd",
        operation="fetch_ohlcv",
        error=error,
    )

    assert observed == {"calls_per_day": 10}


def test_marketstack_api_errors_do_not_debit_monthly_allowance_only():
    policy = SimpleNamespace(
        quota_contract={
            "dimensions": [
                {"name": "requests_per_month", "unit": "requests", "window_seconds": 2592000},
                {"name": "requests_per_second", "unit": "requests", "window_seconds": 1},
            ]
        }
    )
    measurement = SimpleNamespace(http_requests=1, response_bytes=128)
    api_error = ProviderResponseError("marketstack", "provider rejected request", status_code=403)

    observed, unknown = _coordinator_settlement(
        policy,
        measurement,
        {"requests_per_month": 1, "requests_per_second": 1},
        provider_name="marketstack",
        operation="get_current_price",
        error=api_error,
    )

    assert observed == {"requests_per_month": 0, "requests_per_second": 1}
    assert unknown == set()

    process_local_costs = {"requests_per_month": 1, "requests_per_second": 1}
    _apply_marketstack_api_error_usage("marketstack", api_error, process_local_costs)
    assert process_local_costs == {"requests_per_month": 0, "requests_per_second": 1}

    # A timeout or post-response parsing error has no HTTP status and remains
    # conservatively charged against the monthly reservation.
    ambiguous_costs = {"requests_per_month": 1, "requests_per_second": 1}
    _apply_marketstack_api_error_usage("marketstack", RuntimeError("ambiguous"), ambiguous_costs)
    assert ambiguous_costs == {"requests_per_month": 1, "requests_per_second": 1}


def test_tiingo_selected_plan_is_visible_in_provider_entitlement_diagnostics(monkeypatch):
    monkeypatch.setattr(settings, "TIINGO_REVIEWED_PLAN", "starter")
    starter = _entitlement_seed("tiingo", ProviderCapability.PRICE_HISTORY)
    assert starter["configured_plan"] == "tiingo-starter-operator-reviewed"
    assert starter["is_free"] is True

    monkeypatch.setattr(settings, "TIINGO_REVIEWED_PLAN", "power")
    power = _entitlement_seed("tiingo", ProviderCapability.PRICE_HISTORY)
    assert power["configured_plan"] == "tiingo-power-operator-reviewed"
    assert power["is_free"] is False

    monkeypatch.setattr(settings, "TIINGO_REVIEWED_PLAN", "custom")
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_UNIQUE_SYMBOLS_PER_MONTH", 0)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_REQUESTS_PER_HOUR", 0)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_REQUESTS_PER_DAY", 0)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_BANDWIDTH_BYTES_PER_MONTH", 0)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_QUOTA_EVIDENCE", "")
    unreviewed = _entitlement_seed("tiingo", ProviderCapability.PRICE_HISTORY)
    assert unreviewed["configured_plan"] == "unreviewed"


def test_account_usage_bootstrap_allows_only_explicit_unknown_dimensions():
    contract = {
        "reset": "per_dimension",
        "unknown_dimensions": ["provider_minute_pool"],
        "account_usage_bootstrap": {
            "enabled": True,
            "source": "application_policy:provider_native_baseline_bootstrap",
            "allowed_unknown_dimensions": ["provider_minute_pool"],
            "reconciled_dimensions": ["calls_per_day"],
        },
        "dimensions": [
            {
                "name": "calls_per_day",
                "limit": 20,
                "window_seconds": 86400,
                "unit": "calls",
                "scope": "api_key",
                "source": "unit-test",
                "reset": "calendar_day_gmt",
            },
            {
                "name": "account_usage_probe_concurrency",
                "limit": 1,
                "window_seconds": 1,
                "unit": "concurrent_requests",
                "scope": "deployment",
                "source": "unit-test",
                "reset": "rolling",
                "applies_to_operations": ["fetch_account_usage"],
            },
        ],
    }
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.ACCOUNT_USAGE,
        quota_contract=contract,
        quota_scope="api_key",
        quota_source="unit-test",
    )
    assert policy_allows_account_usage_bootstrap(policy, "fetch_account_usage") is True
    contract["account_usage_bootstrap"]["allowed_unknown_dimensions"] = []
    assert policy_allows_account_usage_bootstrap(policy, "fetch_account_usage") is False


def test_account_usage_bootstrap_requires_valid_reconciled_dimension_map():
    contract = {
        "reset": "per_dimension",
        "account_usage_bootstrap": {
            "enabled": True,
            "source": "unit-test",
            "reconciled_dimensions": ["not_declared"],
        },
        "dimensions": [
            {
                "name": "calls_per_day",
                "limit": 20,
                "window_seconds": 86400,
                "unit": "calls",
                "scope": "api_key",
                "source": "unit-test",
                "reset": "calendar_day_utc",
            },
            {
                "name": "account_usage_probe_concurrency",
                "limit": 1,
                "window_seconds": 1,
                "unit": "concurrent_requests",
                "scope": "deployment",
                "source": "unit-test",
                "reset": "rolling",
                "applies_to_operations": ["fetch_account_usage"],
            },
        ],
    }
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.ACCOUNT_USAGE,
        quota_contract=contract,
        quota_scope="api_key",
        quota_source="unit-test",
    )
    assert policy_allows_account_usage_bootstrap(policy, "fetch_account_usage") is False
    contract["account_usage_bootstrap"]["reconciled_dimensions"] = [
        "calls_per_day",
        "calls_per_day",
    ]
    assert policy_allows_account_usage_bootstrap(policy, "fetch_account_usage") is False
    contract["account_usage_bootstrap"]["reconciled_dimensions"] = [
        "account_usage_probe_concurrency"
    ]
    assert policy_allows_account_usage_bootstrap(policy, "fetch_account_usage") is False
    assert (
        "quota_contract.account_usage_bootstrap.reconciled_dimensions"
        in quota_contract_missing_dimensions(policy)
    )


@pytest.mark.parametrize("pinned", [False, True])
def test_eodhd_legacy_high_repository_seed_migrates_only_unpinned_policy(pinned, monkeypatch):
    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 0)
    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_RESET", "")
    monkeypatch.setattr(settings, "EODHD_MINUTE_QUOTA_EVIDENCE", "")
    current_seed = provider_rate_limit_seed("eodhd")
    legacy_contract = deepcopy(current_seed["quota_contract"])
    request_dimension = next(
        item for item in legacy_contract["dimensions"] if item["name"] == "requests_per_minute"
    )
    request_dimension.update(
        {
            "limit": 1000,
            "source": "https://eodhd.com/financial-apis/api-limits",
            "reset": "rolling",
            "limit_basis": "documented all-plan request ceiling",
        }
    )
    legacy_contract["account_usage_bootstrap"]["reconciled_dimensions"] = ["calls_per_day"]
    legacy_contract["account_usage_bootstrap"]["allowed_unknown_dimensions"] = []
    legacy_contract.pop("source_conflicts", None)
    legacy_contract["unknown_dimensions"] = []
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        is_enabled=True,
        is_pinned=pinned,
        tokens_per_minute=1000,
        quota_contract=legacy_contract,
        quota_scope=current_seed["quota_scope"],
        quota_source=current_seed["quota_source"],
    )

    _apply_policy_defaults(
        policy,
        provider_name="eodhd",
        providers=["eodhd"],
        freshness_seconds=300,
        rate_seed=current_seed,
    )

    if pinned:
        assert policy.tokens_per_minute == 1000
        assert policy.quota_contract == legacy_contract
    else:
        # The detailed EODHD limits page documents 1,000 requests/minute;
        # the former 20/minute pricing-card interpretation was corrected.
        assert policy.tokens_per_minute == 1000
        assert policy.quota_contract == current_seed["quota_contract"]


@pytest.mark.asyncio
async def test_execute_provider_call_persists_transport_measurement(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(
        name="measured-provider",
        is_active=True,
        config={
            "usage_tracking": {
                "operation_costs": {"get_current_price": 1},
                "dimension_costs": {
                    "response_bytes": {"get_current_price": 100},
                    "credits_per_minute": {"get_current_price": 1},
                },
            }
        },
    )
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        is_enabled=True,
        max_concurrency=1,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test contract",
                },
                {
                    "name": "response_bytes",
                    "limit": 10_000,
                    "window_seconds": 60,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "unit-test contract",
                },
                {
                    "name": "credits_per_minute",
                    "limit": 8,
                    "window_seconds": 60,
                    "unit": "credits",
                    "scope": "api_key",
                    "source": "https://support.twelvedata.com/en/articles/5713553-control-over-usage",
                },
            ],
            "dimension_costs_required": True,
        },
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("0"),
    )
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
    )
    resolved = ResolvedProvider(
        provider_name="measured-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=health,
    )

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)

    def invoke(_provider, _symbol):
        assert provider_runtime_quota_admission_active()
        response = type(
            "Response",
            (),
            {
                "content": b"measured-response",
                "json": lambda _self: {"price": "123.45", "provider_field": "retained"},
                "headers": {
                    "x-ratelimit-remaining": "9",
                    "api-credits-used": "3",
                    "api-credits-left": "5",
                },
            },
        )()
        observe_response(response)
        return 123.45

    await execute_provider_call(
        async_db,
        ProviderCapability.LATEST_PRICE,
        "get_current_price",
        invoke=invoke,
    )
    assert not provider_runtime_quota_admission_active()
    row = db.execute(select(ProviderRequestLog)).scalar_one()
    assert row.http_requests == 1
    assert row.response_bytes == len(b"measured-response")
    assert row.response_headers == {
        "x-ratelimit-remaining": "9",
        "api-credits-used": "3",
        "api-credits-left": "5",
    }
    assert row.response_payloads == [{"price": "123.45", "provider_field": "retained"}]
    windows = {
        item.dimension: item for item in db.execute(select(ProviderQuotaWindow)).scalars().all()
    }
    assert windows["requests_per_minute"].consumed_units == 1
    assert windows["response_bytes"].consumed_units == len(b"measured-response")
    assert windows["credits_per_minute"].consumed_units == 3
    assert all(item.reserved_units == 0 for item in windows.values())

    def invoke_with_validation_error(_provider, _symbol):
        assert provider_runtime_quota_admission_active()
        response = type(
            "Response",
            (),
            {
                "content": b"provider-row-that-fails-validation",
                "json": lambda _self: {"symbol": "AAPL", "provider_field": "still-retain"},
                "headers": {},
            },
        )()
        observe_response(response)
        raise ProviderResponseError("measured-provider", "row validation failed")

    with pytest.raises(ProviderResponseError, match="row validation failed"):
        await execute_provider_call(
            async_db,
            ProviderCapability.LATEST_PRICE,
            "get_current_price",
            invoke=invoke_with_validation_error,
        )
    assert not provider_runtime_quota_admission_active()
    rows = db.execute(select(ProviderRequestLog).order_by(ProviderRequestLog.id)).scalars().all()
    assert rows[-1].response_payloads == [{"symbol": "AAPL", "provider_field": "still-retain"}]
    assert rows[-1].http_requests == 1
    assert rows[-1].error_message == "row validation failed"

    partial_result = b"finra-partial-result"

    def invoke_with_partial_binary_result(_provider, _symbol):
        observe_binary_response_payload("finra_async_result", partial_result, complete=False)
        raise ProviderResponseError("measured-provider", "stream interrupted")

    with pytest.raises(ProviderResponseError, match="stream interrupted"):
        await execute_provider_call(
            async_db,
            ProviderCapability.LATEST_PRICE,
            "get_current_price",
            invoke=invoke_with_partial_binary_result,
        )
    rows = db.execute(select(ProviderRequestLog).order_by(ProviderRequestLog.id)).scalars().all()
    assert rows[-1].response_payloads == [
        {
            "kind": "finra_async_result",
            "encoding": "base64",
            "complete": False,
            "bytes_received": len(partial_result),
            "sha256": sha256(partial_result).hexdigest(),
            "body_base64": base64.b64encode(partial_result).decode("ascii"),
        }
    ]
    assert rows[-1].error_message == "stream interrupted"


@pytest.mark.asyncio
async def test_execute_provider_call_reports_quota_denial_before_transport(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(
        name="quota-denied-provider",
        is_active=True,
        config={"usage_tracking": {"operation_costs": {"get_current_price": 1}}},
    )
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        is_enabled=True,
        max_concurrency=1,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 1,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test contract",
                }
            ],
        },
    )
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
    )
    resolved = ResolvedProvider(
        provider_name=source.name,
        provider=object(),
        data_source=source,
        policy=policy,
        health=health,
    )

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    async def deny_reservation(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)
    monkeypatch.setattr("app.services.provider_routing.reserve_provider_contract", deny_reservation)

    with pytest.raises(ProviderQuotaAdmissionError, match="quota admission denied"):
        await execute_provider_call(
            async_db,
            ProviderCapability.LATEST_PRICE,
            "get_current_price",
            provider_name=source.name,
            invoke=lambda *_args: pytest.fail("quota denial must precede provider transport"),
        )

    assert db.execute(select(ProviderRequestLog)).scalars().all() == []


@pytest.mark.asyncio
async def test_execute_provider_call_retains_first_orf_file_if_second_download_fails(
    db, monkeypatch
):
    """A paid-for ORF response survives failure of its paired file request."""

    async_db = AsyncSessionAdapter(db)
    source = DataSource(
        name="finra_otc_directory",
        is_active=True,
        config={
            "usage_tracking": {
                "operation_costs": {"discover_universe_page": 3},
            }
        },
    )
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.UNIVERSE_DISCOVERY,
        is_enabled=True,
        max_concurrency=1,
        quota_scope="traqs_account",
        quota_source="unit-test reviewed operation contract",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "traqs_account",
                    "source": "unit-test reviewed operation contract",
                },
            ],
        },
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("0"),
    )
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.UNIVERSE_DISCOVERY,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
        failure_streak=0,
    )
    resolved = ResolvedProvider(
        provider_name="finra_otc_directory",
        provider=FINRAOTCDirectoryProvider(),
        data_source=source,
        policy=policy,
        health=health,
    )

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
    )
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL",
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF",
    )
    monkeypatch.setattr(settings, "FINRA_ORF_USERNAME", "traqs-user")
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN", "refresh-token")
    active_payload = (
        "FINRA_OTC_ID|SYM_CD|SCRTY_DS|STTS_CD|CUSIP_ID\n"
        "100|AAA|Example Active|A|\n"
        "Footer - Count: 00000001, Facility: ORF, File Created: 20260916120000\n"
    )
    active = httpx.Response(
        200,
        text=active_payload,
        request=httpx.Request(
            "POST",
            "https://apidownload.finratraqs.org/DownloadHandler.ashx?action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF",
        ),
    )
    with (
        patch.object(
            finra_otc_directory,
            "_cache",
            None,
        ),
        patch(
            "app.providers.finra_otc_directory._orf_access_token",
            return_value="access-token",
        ),
        patch(
            "app.providers.finra_otc_directory.httpx.post",
            side_effect=[active, httpx.ReadTimeout("inactive file unavailable")],
        ),
    ):
        with pytest.raises(ProviderResponseError, match="transport failure"):
            await execute_provider_call(
                async_db,
                ProviderCapability.UNIVERSE_DISCOVERY,
                "discover_universe_page:OTC:0",
                invoke=lambda candidate, _symbol: candidate.discover_universe_page("OTC", 0),
                response_items=lambda page: len(page.get("quotes") or []),
            )

    request_log = db.execute(select(ProviderRequestLog)).scalar_one()
    assert request_log.success is False
    assert request_log.http_requests == 1
    assert request_log.response_payloads == [active_payload]
    assert request_log.error_message == "transport failure: inactive file unavailable"


@pytest.mark.asyncio
async def test_execute_provider_call_settles_marketdata_app_native_credit_charge(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(
        name="marketdata_app",
        is_active=True,
        config={
            "usage_tracking": {
                "mode": "credit_count",
                "unit_label": "credits",
                "operation_costs": {"get_current_price": 12},
            }
        },
    )
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        is_enabled=True,
        max_concurrency=1,
        quota_scope="api_key",
        quota_source="MarketData.app rate-limiting documentation",
        quota_contract={
            "reset": "09:30 America/New_York",
            "dimensions": [
                {
                    "name": "credits_per_day",
                    "limit": 100,
                    "window_seconds": 86400,
                    "unit": "credits",
                    "scope": "api_key",
                    "source": "https://www.marketdata.app/docs/api/rate-limiting/",
                }
            ],
        },
    )
    db.add(policy)
    db.flush()
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
    )
    db.add(health)
    db.flush()
    resolved = ResolvedProvider(
        provider_name="marketdata_app",
        provider=object(),
        data_source=source,
        policy=policy,
        health=health,
    )

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)

    def invoke(_provider, _symbol):
        response = type(
            "Response",
            (),
            {
                "content": b"marketdata-response",
                "headers": {
                    "x-api-ratelimit-limit": "100",
                    "x-api-ratelimit-remaining": "87",
                    "x-api-ratelimit-reset": "1700000000",
                    "x-api-ratelimit-consumed": "4",
                },
            },
        )()
        observe_response(response)
        return 123.45

    await execute_provider_call(
        async_db,
        ProviderCapability.LATEST_PRICE,
        "get_current_price",
        invoke=invoke,
    )
    row = db.execute(select(ProviderRequestLog)).scalar_one()
    assert row.response_headers == {
        "x-api-ratelimit-limit": "100",
        "x-api-ratelimit-remaining": "87",
        "x-api-ratelimit-reset": "1700000000",
        "x-api-ratelimit-consumed": "4",
    }
    assert row.usage_units == Decimal("12")
    assert row.settled_usage_units == Decimal("4")
    window = db.execute(select(ProviderQuotaWindow)).scalar_one()
    assert window.consumed_units == 13
    assert window.reserved_units == 0


@pytest.mark.asyncio
async def test_execute_provider_call_applies_dynamic_operation_override(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(
        name="binance",
        is_active=True,
        config={
            "usage_tracking": {
                "mode": "weighted_request",
                "unit_label": "request_weight",
                "operation_costs": {"get_current_price": 2},
            }
        },
    )
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        is_enabled=True,
        max_concurrency=1,
        tokens_per_minute=6000,
        burst_capacity=6000,
        quota_scope="ip",
        quota_source="unit-test Binance contract",
        quota_contract={
            "reset": "fixed_minute",
            "dynamic_endpoint_weights": True,
            "dimensions": [
                {
                    "name": "request_weight_per_minute",
                    "limit": 6000,
                    "window_seconds": 60,
                    "unit": "weight",
                    "scope": "ip",
                    "source": "unit-test Binance contract",
                }
            ],
        },
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("0"),
    )
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
    )
    resolved = ResolvedProvider(
        provider_name="binance",
        provider=object(),
        data_source=source,
        policy=policy,
        health=health,
    )

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)

    await execute_provider_call(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        "fetch_ohlcv:1d",
        operation_cost_overrides={"binance": 4},
        invoke=lambda _provider, _symbol: [1],
        response_items=len,
    )

    request = db.execute(select(ProviderRequestLog)).scalar_one()
    assert request.usage_units == Decimal("4")
    windows = db.execute(select(ProviderQuotaWindow)).scalars().all()
    assert [item.dimension for item in windows] == ["request_weight_per_minute"]
    window = windows[0]
    assert window.reserved_units == 0
    assert window.consumed_units == 4


@pytest.mark.asyncio
async def test_finra_async_download_settles_measured_bytes_in_monthly_window(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 4 * 1024 * 1024)
    source = DataSource(
        name="finra",
        is_active=True,
        config={"usage_tracking": get_provider_usage_profile("finra")},
    )
    db.add(source)
    db.flush()
    finra_contract = deepcopy(settings.PROVIDER_RATE_LIMIT_SEEDS["finra"]["quota_contract"])
    # Production deliberately leaves FINRA's public-credential month reset
    # provider-defined/unknown. This fixture supplies an explicit reviewed
    # UTC calendar boundary so the settlement mechanics can be tested without
    # weakening production admission.
    finra_contract["reset"] = "calendar_month_utc"
    finra_contract.pop("unknown_dimensions", None)
    for dimension in finra_contract["dimensions"]:
        if dimension["name"] == "download_bytes_per_calendar_month":
            dimension["reset"] = "calendar_month_utc"
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.SHORT_INTEREST,
        is_enabled=True,
        max_concurrency=1,
        quota_scope="ip",
        quota_source="unit-test FINRA contract",
        quota_contract=finra_contract,
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("0"),
    )
    health = ProviderHealthState(
        data_source_id=source.id,
        capability=ProviderCapability.SHORT_INTEREST,
        ewma_latency_ms=Decimal("0"),
        ewma_success_rate=Decimal("1"),
        ewma_completeness=Decimal("1"),
        ewma_freshness=Decimal("1"),
        ewma_consistency=Decimal("1"),
        observed_score=Decimal("0"),
    )
    resolved = ResolvedProvider(
        provider_name="finra",
        provider=FINRAProvider(),
        data_source=source,
        policy=policy,
        health=health,
    )

    async def fake_chain(*_args, **_kwargs):
        return [resolved]

    monkeypatch.setattr("app.services.provider_runtime.resolve_provider_chain", fake_chain)

    def invoke(_provider, _symbol):
        response = type(
            "Response",
            (),
            {"content": b"async-result", "headers": {"content-length": "12"}},
        )()
        observe_response(response)
        return response.content

    await execute_provider_call(
        async_db,
        ProviderCapability.SHORT_INTEREST,
        "download_async_result",
        invoke=invoke,
        response_items=len,
    )

    windows = db.execute(select(ProviderQuotaWindow)).scalars().all()
    assert [item.dimension for item in windows] == ["download_bytes_per_calendar_month"]
    window = windows[0]
    assert window.dimension == "download_bytes_per_calendar_month"
    assert window.consumed_units == len(b"async-result")
    assert window.reserved_units == 0

    partial_body = b"received-before-reset"
    request = httpx.Request("GET", "https://signed.example.test/result")

    def interrupted_body():
        yield partial_body
        raise httpx.ReadError("connection reset", request=request)

    response = MagicMock(status_code=200)
    response.headers = {"content-length": "128"}
    response.iter_bytes.return_value = interrupted_body()
    response.raise_for_status.return_value = None
    response.__enter__.return_value = response
    response.__exit__.return_value = None
    with (
        patch("app.providers.finra.httpx.stream", return_value=response),
        pytest.raises(ProviderResponseError, match="transport failure"),
    ):
        await execute_provider_call(
            async_db,
            ProviderCapability.SHORT_INTEREST,
            "download_async_result",
            invoke=lambda provider, _symbol: provider.download_async_result(
                "https://signed.example.test/result", max_bytes=1024
            ),
            response_items=len,
        )

    request_logs = db.execute(select(ProviderRequestLog).order_by(ProviderRequestLog.id)).scalars()
    assert [row.response_bytes for row in request_logs] == [
        len(b"async-result"),
        len(partial_body),
    ]
    window = db.execute(select(ProviderQuotaWindow)).scalar_one()
    assert window.consumed_units == len(b"async-result") + len(partial_body)
    assert window.reserved_units == 0


@pytest.mark.asyncio
async def test_seed_provider_runtime_creates_policies_for_supported_non_seeded_providers(db):
    async_db = AsyncSessionAdapter(db)

    await seed_provider_runtime(async_db)

    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == data_source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one_or_none()

    assert policy is not None
    assert policy.base_priority >= 10


@pytest.mark.asyncio
async def test_provider_chain_excludes_non_free_entitlements(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    entitlement.is_free = False
    db.commit()

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)

    assert all(item.provider_name != "alpaca" for item in chain)


@pytest.mark.asyncio
async def test_provider_routing_emergency_switch_keeps_all_adapters_out_of_chain(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", False)

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)

    assert chain == []


@pytest.mark.asyncio
async def test_provider_chain_filters_raw_only_provider_for_adjusted_history(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "ALPHA_VANTAGE_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "ALPHA_VANTAGE_REVIEWED_RESET", "rolling")
    monkeypatch.setattr(settings, "ALPHA_VANTAGE_QUOTA_EVIDENCE", "reviewed test fixture")
    _grant_test_perpetual_archive(monkeypatch, "ALPHA_VANTAGE")
    # The live Alpha Vantage contract intentionally keeps its daily reset
    # boundary unknown. This resolver test supplies an explicit reviewed test
    # fixture so it can isolate the raw-vs-adjusted capability filter without
    # pretending that the production daily pool is routable.
    seeds = deepcopy(settings.PROVIDER_RATE_LIMIT_SEEDS)
    alpha_seed = seeds["alpha_vantage"]
    alpha_seed["quota_contract"]["reset"] = "rolling"
    alpha_seed["quota_contract"].pop("unknown_dimensions", None)
    monkeypatch.setattr(settings, "PROVIDER_RATE_LIMIT_SEEDS", seeds)
    await seed_provider_runtime(async_db)

    raw_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        adjusted=False,
    )
    adjusted_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        adjusted=True,
    )

    assert any(item.provider_name == "alpha_vantage" for item in raw_chain)
    assert all(item.provider_name != "alpha_vantage" for item in adjusted_chain)


@pytest.mark.asyncio
async def test_provider_chain_requires_positive_live_probe_evidence(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "ALPACA_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "ALPACA_SECRET_KEY", "configured-secret")
    # The repository seed records positive bounded live evidence now. Keep
    # this test focused on the resolver gate by explicitly starting from the
    # pre-evidence state.
    monkeypatch.setattr(
        settings,
        "PROVIDER_LIVE_PROBE_STATUS_SEEDS",
        {**settings.PROVIDER_LIVE_PROBE_STATUS_SEEDS, "alpaca": "not_run"},
    )
    await seed_provider_runtime(async_db)

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)
    assert all(item.provider_name != "alpaca" for item in chain)

    source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    entitlement.live_probe_status = "passed"
    db.commit()
    _grant_test_perpetual_archive(monkeypatch, "ALPACA")

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)
    # The current Alpaca contract is source-backed; once transport evidence
    # is positive, the provider may enter the chain without a second manual
    # reset-boundary gate.
    assert any(item.provider_name == "alpaca" for item in chain)


@pytest.mark.asyncio
async def test_unreviewed_provider_entitlement_is_not_runtime_usable(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    seeds = {
        name: value
        for name, value in settings.PROVIDER_ENTITLEMENT_SEEDS.items()
        if name != "alpaca"
    }
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", seeds)

    await seed_provider_runtime(async_db)
    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert entitlement.configured_plan == "unreviewed"
    assert entitlement.is_free is False

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)
    assert all(item.provider_name != "alpaca" for item in chain)


@pytest.mark.asyncio
async def test_eodhd_free_plan_migrates_and_requires_entitlement_and_provider_terms(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)
    current_seeds = deepcopy(settings.PROVIDER_ENTITLEMENT_SEEDS)
    current_eodhd_seed = deepcopy(current_seeds["eodhd"])
    legacy_eodhd_seed = deepcopy(current_eodhd_seed)
    legacy_eodhd_seed.pop("capabilities")
    legacy_seeds = deepcopy(current_seeds)
    legacy_seeds["eodhd"] = legacy_eodhd_seed

    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", legacy_seeds)
    monkeypatch.setattr(settings, "EODHD_API_KEY", "configured-test-key")
    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 20)
    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_RESET", "rolling")
    monkeypatch.setattr(settings, "EODHD_MINUTE_QUOTA_EVIDENCE", "unit-test account evidence")
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", True)
    await seed_provider_runtime(async_db)

    source = db.execute(select(DataSource).where(DataSource.name == "eodhd")).scalar_one()
    metadata_entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.INSTRUMENT_METADATA,
        )
    ).scalar_one()
    assert metadata_entitlement.configured_plan == "free-20-calls-day"
    assert metadata_entitlement.is_free is True

    # The previous identifier was also repository-owned. Simulate an
    # installation that has not yet run the plan-identifier migration.
    metadata_entitlement.configured_plan = "free-20-day"

    # Existing rows on the repository-managed free plan must pick up the
    # newly recorded capability-level Fundamentals exclusion on reseed.
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", current_seeds)
    await seed_provider_runtime(async_db)
    db.expire_all()
    metadata_entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.INSTRUMENT_METADATA,
        )
    ).scalar_one()
    assert metadata_entitlement.configured_plan == "unreviewed"
    assert metadata_entitlement.is_free is False

    # Pretend positive live evidence exists to prove the plan gate itself
    # remains fail-closed when the global paid-routing switch is enabled.
    reviewed_test_seeds = deepcopy(current_seeds)
    reviewed_test_seeds["eodhd"]["capabilities"]["instrument_metadata"]["live_probe_status"] = (
        "passed"
    )
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", reviewed_test_seeds)
    metadata_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.INSTRUMENT_METADATA,
        operation="get_instrument_profile",
    )
    assert all(provider.provider_name != "eodhd" for provider in metadata_chain)

    free_history_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        adjusted=False,
    )
    assert all(provider.provider_name != "eodhd" for provider in free_history_chain)

    # The owner's storage consent is global and does not admit vendor-restricted
    # display. The provider-specific display-terms exception is independent.
    monkeypatch.setattr(settings, "EODHD_PROVIDER_DISPLAY_TERMS_AUTHORIZED", True)
    monkeypatch.setattr(
        settings,
        "EODHD_PROVIDER_DISPLAY_TERMS_EVIDENCE",
        "unit-test provider terms exception",
    )
    granted_history_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        adjusted=False,
    )
    assert any(provider.provider_name == "eodhd" for provider in granted_history_chain)


@pytest.mark.asyncio
async def test_marketdata_app_entitlement_and_quota_follow_explicit_reviewed_plan(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10000)

    await seed_provider_runtime(async_db)

    source = db.execute(select(DataSource).where(DataSource.name == "marketdata_app")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()

    assert entitlement.configured_plan == "marketdata-starter-operator-reviewed"
    assert entitlement.quota_policy["history_constraints"]["max_lookback_years"] == 1
    assert policy.quota_contract["dimensions"][0]["limit"] == 10000
    assert policy.quota_contract["dimensions"][0]["account_plan"] == "starter"
    assert entitlement.is_free is False


@pytest.mark.asyncio
async def test_free_only_checkpoint_boundary_rejects_reviewed_paid_provider(db, monkeypatch):
    """Checkpoint admission overrides the paid flag and denies trials/unknown plans."""
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10_000)
    monkeypatch.setattr(settings, "MARKETDATA_APP_API_KEY", "unit-test-key")
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", False)
    monkeypatch.setattr(
        "app.services.provider_runtime.provider_missing_routing_controls",
        lambda *_args, **_kwargs: [],
    )
    await seed_provider_runtime(async_db)

    source = db.execute(select(DataSource).where(DataSource.name == "marketdata_app")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.LATEST_PRICE,
        )
    ).scalar_one()
    entitlement.configured_plan = "reviewed-checkpoint-paid-fixture"
    entitlement.is_free = False
    entitlement.authentication_required = True
    entitlement.live_probe_status = "passed"

    # The default checkpoint is free-only, despite a reviewed plan, positive
    # quota, configured credentials, and successful live-probe evidence.
    denied_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.LATEST_PRICE,
        operation="get_current_price",
        operation_cost_overrides={"marketdata_app": 1},
    )
    assert all(item.provider_name != "marketdata_app" for item in denied_chain)

    paid_status = next(
        row
        for row in await list_provider_status(async_db)
        if row["provider"] == "marketdata_app"
        and row["capability"] == ProviderCapability.LATEST_PRICE.value
    )
    assert paid_status["entitlement_state"] == "reviewed"
    assert paid_status["routing_eligible"] is False

    # A shared free-only checkpoint is not bypassed by the full-roadmap flag.
    # Exercise execution too: the injected transport must never be reached.
    transport_calls = []
    for allow_paid in (False, True):
        monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", allow_paid)
        decision = provider_entitlement_admission(entitlement)
        assert decision["allowed"] is False
        assert decision["reason_code"] == "checkpoint_free_only"
        denied_chain = await resolve_provider_chain(
            async_db,
            ProviderCapability.LATEST_PRICE,
            operation="get_current_price",
            operation_cost_overrides={"marketdata_app": 1},
        )
        assert all(item.provider_name != "marketdata_app" for item in denied_chain)
        with pytest.raises(RuntimeError, match="No enabled providers available"):
            await execute_provider_call(
                async_db,
                ProviderCapability.LATEST_PRICE,
                "get_current_price",
                provider_name="marketdata_app",
                operation_cost_overrides={"marketdata_app": 1},
                invoke=lambda *_args: transport_calls.append("called"),
            )
        paid_status = next(
            row
            for row in await list_provider_status(async_db)
            if row["provider"] == "marketdata_app"
            and row["capability"] == ProviderCapability.LATEST_PRICE.value
        )
        assert paid_status["routing_eligible"] is False
        assert paid_status["entitlement_admission"]["reason_code"] == "checkpoint_free_only"
    assert transport_calls == []

    # An affirmative `is_free` bit does not make an unknown plan reviewed.
    # Prove the shared admission, status, resolver, and executor all fail
    # closed under either paid-routing toggle.
    for unknown_plan in ("unknown", "unknown-plan"):
        entitlement.configured_plan = unknown_plan
        entitlement.is_free = True
        for allow_paid in (False, True):
            monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", allow_paid)
            decision = provider_entitlement_admission(entitlement)
            assert decision["allowed"] is False
            assert decision["reason_code"] == "entitlement_unreviewed"
            denied_chain = await resolve_provider_chain(
                async_db,
                ProviderCapability.LATEST_PRICE,
                operation="get_current_price",
                operation_cost_overrides={"marketdata_app": 1},
            )
            assert all(item.provider_name != "marketdata_app" for item in denied_chain)
            with pytest.raises(RuntimeError, match="No enabled providers available"):
                await execute_provider_call(
                    async_db,
                    ProviderCapability.LATEST_PRICE,
                    "get_current_price",
                    provider_name="marketdata_app",
                    operation_cost_overrides={"marketdata_app": 1},
                    invoke=lambda *_args: transport_calls.append("called"),
                )
            unknown_status = next(
                row
                for row in await list_provider_status(async_db)
                if row["provider"] == "marketdata_app"
                and row["capability"] == ProviderCapability.LATEST_PRICE.value
            )
            assert unknown_status["entitlement_state"] == "unreviewed"
            assert unknown_status["routing_eligible"] is False
            assert unknown_status["entitlement_admission"]["reason_code"] == (
                "entitlement_unreviewed"
            )
    assert transport_calls == []

    # Leaving checkpoint mode deliberately restores full-roadmap opt-in
    # semantics, without implying aggregate subscription-cost admission.
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", False)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", False)
    entitlement.configured_plan = "reviewed-checkpoint-paid-fixture"
    entitlement.is_free = False
    assert provider_entitlement_admission(entitlement)["reason_code"] == "paid_routing_disabled"
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", True)
    assert provider_entitlement_admission(entitlement)["reason_code"] == "reviewed_paid_opt_in"
    allowed_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.LATEST_PRICE,
        operation="get_current_price",
        operation_cost_overrides={"marketdata_app": 1},
    )
    assert any(item.provider_name == "marketdata_app" for item in allowed_chain)

    # Unknown and temporary trial plan evidence is never zero-cost admission,
    # even after deliberately leaving checkpoint mode and enabling paid plans.
    for plan, reason in (
        ("unreviewed-cost-profile", "entitlement_unreviewed"),
        ("starter_trial", "trial_cost_not_admissible"),
    ):
        entitlement.configured_plan = plan
        entitlement.is_free = True
        assert provider_entitlement_admission(entitlement)["reason_code"] == reason
    assert transport_calls == []


@pytest.mark.asyncio
async def test_marketdata_trial_expiry_reseeds_entitlement_and_quota_to_free_forever(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter_trial")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10000)
    monkeypatch.setattr(
        settings,
        "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT",
        datetime(2030, 1, 1, tzinfo=UTC),
    )

    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "marketdata_app")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert entitlement.configured_plan == "marketdata-starter_trial-operator-reviewed"
    assert entitlement.is_free is True
    assert entitlement.quota_policy["contract"]["dimensions"][0]["limit"] == 10000
    assert policy.quota_contract["dimensions"][0]["limit"] == 10000

    monkeypatch.setattr(
        settings,
        "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT",
        datetime(2020, 1, 1, tzinfo=UTC),
    )
    await seed_provider_runtime(async_db)
    db.expire_all()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert entitlement.configured_plan == "marketdata-free_forever-operator-reviewed"
    assert entitlement.is_free is True
    assert entitlement.quota_policy["contract"]["dimensions"][0]["limit"] == 100
    assert policy.quota_contract["dimensions"][0]["limit"] == 100


@pytest.mark.asyncio
async def test_marketdata_app_account_usage_before_plan_review_is_not_checkpoint_free(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "MARKETDATA_APP_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 0)
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", None)
    monkeypatch.setattr(settings, "MARKETDATA_APP_PERSISTENT_STORAGE_AUTHORIZED", False)

    await seed_provider_runtime(async_db)

    account_usage_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.ACCOUNT_USAGE,
        operation="fetch_account_usage",
    )
    assert all(item.provider_name != "marketdata_app" for item in account_usage_chain)

    price_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        operation_cost_overrides={"marketdata_app": 1},
    )
    assert all(item.provider_name != "marketdata_app" for item in price_chain)


@pytest.mark.asyncio
async def test_checkpoint_blocks_paid_unknown_and_trial_usage_probes_before_transport(
    db, monkeypatch
):
    """Unreviewed account probes cannot escape free-only admission or quotas."""

    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "MARKETDATA_APP_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 0)
    monkeypatch.setattr(
        "app.services.provider_runtime.provider_missing_routing_controls",
        lambda *_args, **_kwargs: [],
    )
    await seed_provider_runtime(async_db)

    source = db.execute(select(DataSource).where(DataSource.name == "marketdata_app")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.ACCOUNT_USAGE,
        )
    ).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.ACCOUNT_USAGE,
        )
    ).scalar_one()
    base_contract = deepcopy(policy.quota_contract)
    transport_calls = []

    for allow_paid in (False, True):
        monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", allow_paid)
        for plan, is_free in (
            ("reviewed-paid-fixture", False),
            ("unreviewed", False),
            ("unknown-plan", True),
            ("unknown", True),
            ("starter_trial", True),
        ):
            entitlement.configured_plan = plan
            entitlement.is_free = is_free
            for quota_state in ("known", "bootstrap_unknown"):
                contract = deepcopy(base_contract)
                if quota_state == "bootstrap_unknown":
                    unknown = "provider_reset_boundary_unknown"
                    contract["unknown_dimensions"] = [unknown]
                    contract["account_usage_bootstrap"]["allowed_unknown_dimensions"] = [unknown]
                    assert policy_allows_account_usage_bootstrap(
                        ProviderPolicy(
                            data_source_id=source.id,
                            capability=ProviderCapability.ACCOUNT_USAGE,
                            quota_contract=contract,
                            quota_scope=policy.quota_scope,
                        ),
                        "fetch_account_usage",
                    )
                policy.quota_contract = contract
                db.flush()

                chain = await resolve_provider_chain(
                    async_db,
                    ProviderCapability.ACCOUNT_USAGE,
                    operation="fetch_account_usage",
                )
                assert all(item.provider_name != "marketdata_app" for item in chain), (
                    plan,
                    allow_paid,
                    quota_state,
                )
                with pytest.raises(RuntimeError, match="No enabled providers available"):
                    await execute_provider_call(
                        async_db,
                        ProviderCapability.ACCOUNT_USAGE,
                        "fetch_account_usage",
                        provider_name="marketdata_app",
                        invoke=lambda *_args: transport_calls.append("called"),
                    )
                assert transport_calls == []


@pytest.mark.asyncio
async def test_eodhd_reviewed_zero_credit_usage_probe_remains_available_unreviewed(
    db, monkeypatch, tmp_path
):
    """Only EODHD's documented zero-credit usage read gets the narrow exception."""

    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "EODHD_API_KEY", "configured-key")
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_PATH",
        str(tmp_path / "eodhd-zero-credit-bootstrap.sqlite3"),
    )
    reviewed_seed = _entitlement_seed

    def unreviewed_eodhd_usage_seed(provider_name, capability):
        seed = reviewed_seed(provider_name, capability)
        if provider_name == "eodhd" and capability == ProviderCapability.ACCOUNT_USAGE:
            seed["configured_plan"] = "unreviewed"
            seed["is_free"] = False
        return seed

    # Model an account whose plan is genuinely not reviewed. Repository seed
    # reconciliation must not silently turn the exception test into a normal
    # reviewed-free route.
    monkeypatch.setattr(
        "app.services.provider_runtime._entitlement_seed", unreviewed_eodhd_usage_seed
    )
    await seed_provider_runtime(async_db)

    source = db.execute(select(DataSource).where(DataSource.name == "eodhd")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.ACCOUNT_USAGE,
        )
    ).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.ACCOUNT_USAGE,
        )
    ).scalar_one()
    entitlement.configured_plan = "unreviewed"
    entitlement.is_free = False
    usage_dimension_costs = source.config["usage_tracking"]["dimension_costs"]
    assert usage_dimension_costs["calls_per_day"]["fetch_account_usage"] == {}
    assert usage_dimension_costs["requests_per_minute"]["fetch_account_usage"] == 1
    assert policy_allows_unreviewed_account_usage_checkpoint(policy, source, "fetch_account_usage")
    assert not policy_allows_unreviewed_account_usage_checkpoint(
        policy, source, "get_current_price"
    )
    saved_config = deepcopy(source.config)
    no_zero_cost_proof = deepcopy(saved_config)
    no_zero_cost_proof["usage_tracking"]["dimension_costs"]["calls_per_day"].pop(
        "fetch_account_usage"
    )
    source.config = no_zero_cost_proof
    assert not policy_allows_unreviewed_account_usage_checkpoint(
        policy, source, "fetch_account_usage"
    )
    source.config = saved_config
    assert policy_allows_unreviewed_account_usage_checkpoint(policy, source, "fetch_account_usage")

    observed_at = datetime.now(UTC).replace(microsecond=0)
    probe_calls = []
    for allow_paid in (False, True):
        monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", allow_paid)
        monkeypatch.setattr(
            settings,
            "PROVIDER_QUOTA_LEDGER_PATH",
            str(tmp_path / f"eodhd-zero-credit-bootstrap-{allow_paid}.sqlite3"),
        )
        chain = await resolve_provider_chain(
            async_db,
            ProviderCapability.ACCOUNT_USAGE,
            operation="fetch_account_usage",
        )
        assert any(item.provider_name == "eodhd" for item in chain)
        result = await execute_provider_call(
            async_db,
            ProviderCapability.ACCOUNT_USAGE,
            "fetch_account_usage",
            provider_name="eodhd",
            invoke=lambda *_args: probe_calls.append("called")
            or ProviderAccountUsage(
                provider="eodhd",
                observed_at=observed_at,
                unit="calls",
                limit=20,
                remaining=14,
                consumed=6,
                reset_at=observed_at + timedelta(days=1),
                account_plan="free",
            ),
            response_items=lambda value: 1 if value is not None else 0,
            treat_empty_as_failure=True,
        )
        assert result.provider_name == "eodhd"

    assert probe_calls == ["called", "called"]

    # The resolver and execution path must enforce the same evidence contract;
    # a bootstrap reservation alone is not proof that the operation is free.
    original_contract = deepcopy(policy.quota_contract)
    # Pin the fixture so seed reconciliation preserves each deliberately
    # malformed operator contract instead of restoring the reviewed code seed.
    policy.is_pinned = True
    exception = original_contract["account_usage_bootstrap"]["checkpoint_unreviewed_zero_billing"]
    invalid_exceptions = (
        None,
        {**exception, "operation": "get_current_price"},
        {**exception, "cost": 1},
        {**exception, "source": "application_policy:unverified"},
        {**exception, "dimension": "requests_per_minute"},
    )
    for allow_paid in (False, True):
        monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", allow_paid)
        monkeypatch.setattr(
            settings,
            "PROVIDER_QUOTA_LEDGER_PATH",
            str(tmp_path / f"eodhd-invalid-zero-billing-{allow_paid}.sqlite3"),
        )
        for invalid_exception in invalid_exceptions:
            contract = deepcopy(original_contract)
            bootstrap = contract["account_usage_bootstrap"]
            if invalid_exception is None:
                bootstrap.pop("checkpoint_unreviewed_zero_billing")
            else:
                bootstrap["checkpoint_unreviewed_zero_billing"] = invalid_exception
            policy.quota_contract = contract
            db.flush()
            assert not policy_allows_unreviewed_account_usage_checkpoint(
                policy, source, "fetch_account_usage"
            )
            denied_chain = await resolve_provider_chain(
                async_db,
                ProviderCapability.ACCOUNT_USAGE,
                operation="fetch_account_usage",
            )
            assert all(item.provider_name != "eodhd" for item in denied_chain), (
                allow_paid,
                invalid_exception,
            )
            denied_calls = []
            with pytest.raises(RuntimeError, match="No enabled providers available"):
                await execute_provider_call(
                    async_db,
                    ProviderCapability.ACCOUNT_USAGE,
                    "fetch_account_usage",
                    provider_name="eodhd",
                    invoke=lambda *_args: denied_calls.append("called"),
                )
            assert denied_calls == []


@pytest.mark.asyncio
async def test_marketdata_app_and_twelve_data_persistent_routes_require_written_archive_rights(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", False)
    monkeypatch.setattr(settings, "MARKETDATA_APP_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter_trial")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10000)
    monkeypatch.setattr(
        settings,
        "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT",
        datetime(2030, 1, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(settings, "MARKETDATA_APP_PERSISTENT_STORAGE_AUTHORIZED", False)
    monkeypatch.setattr(settings, "TWELVE_DATA_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "TWELVE_DATA_PERSISTENT_STORAGE_AUTHORIZED", False)

    await seed_provider_runtime(async_db)

    marketdata_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        operation_cost_overrides={"marketdata_app": 1},
    )
    twelve_data_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        operation_cost_overrides={"twelve_data": 1},
    )
    assert all(item.provider_name != "marketdata_app" for item in marketdata_chain)
    assert all(item.provider_name != "twelve_data" for item in twelve_data_chain)


@pytest.mark.asyncio
async def test_marketdata_app_account_usage_requires_review_before_credit_bearing_probe(
    db, monkeypatch
):
    """The one-credit /user/ call cannot bootstrap an unreviewed plan."""

    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "MARKETDATA_APP_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 0)
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", None)

    await seed_provider_runtime(async_db)

    account_usage_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.ACCOUNT_USAGE,
        operation="fetch_account_usage",
    )
    assert all(item.provider_name != "marketdata_app" for item in account_usage_chain)
    probe_calls = []
    with pytest.raises(RuntimeError, match="No enabled providers available"):
        await execute_provider_call(
            async_db,
            ProviderCapability.ACCOUNT_USAGE,
            "fetch_account_usage",
            provider_name="marketdata_app",
            invoke=lambda *_args: probe_calls.append("called"),
            response_items=lambda value: 1 if value is not None else 0,
            treat_empty_as_failure=True,
        )
    assert probe_calls == []


@pytest.mark.asyncio
async def test_alpaca_account_usage_bootstrap_observes_headers_with_documented_data_quota(
    db, monkeypatch, tmp_path
):
    """Alpaca's native header snapshot is allowed without guessing its reset window."""

    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "ALPACA_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "ALPACA_SECRET_KEY", "configured-secret")
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_PATH",
        str(tmp_path / "alpaca.sqlite3"),
    )

    await seed_provider_runtime(async_db)
    account_usage_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.ACCOUNT_USAGE,
        operation="fetch_account_usage",
    )
    assert any(item.provider_name == "alpaca" for item in account_usage_chain)

    price_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        operation_cost_overrides={"alpaca": 1},
    )
    # Alpaca's documented 200-requests/minute contract is enough to admit a
    # bounded data call; the header probe refines durable usage observations,
    # not a fictitious daily allowance.
    assert any(item.provider_name == "alpaca" for item in price_chain)

    observed_at = datetime.now(UTC).replace(microsecond=0)
    result = await execute_provider_call(
        async_db,
        ProviderCapability.ACCOUNT_USAGE,
        "fetch_account_usage",
        provider_name="alpaca",
        invoke=lambda _provider, _symbol: ProviderAccountUsage(
            provider="alpaca",
            observed_at=observed_at,
            unit="requests",
            limit=200,
            remaining=199,
            consumed=1,
            reset_at=observed_at + timedelta(seconds=30),
            account_plan="market_data_headers",
            dimensions=(
                ProviderAccountUsageDimension(
                    name="market_data_requests_per_minute",
                    unit="requests",
                    limit=200,
                    remaining=199,
                    consumed=1,
                    reset_at=observed_at + timedelta(seconds=30),
                ),
            ),
        ),
        response_items=lambda value: 1 if value is not None else 0,
        treat_empty_as_failure=True,
    )

    assert result.provider_name == "alpaca"
    summary = provider_quota_coordinator_summary(provider_name="alpaca")
    assert any(row["dimension"] == "account_usage_probe_concurrency" for row in summary["windows"])
    assert all(row["dimension"] != "market_data_requests_per_minute" for row in summary["windows"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_name", "setting_name", "usage"),
    [
        (
            "twelve_data",
            "TWELVE_DATA_API_KEY",
            ProviderAccountUsage(
                provider="twelve_data",
                observed_at=datetime.now(UTC),
                unit="credits",
                limit=8,
                remaining=5,
                consumed=3,
                reset_at=datetime.now(UTC) + timedelta(seconds=30),
                account_plan="Basic",
                dimensions=(
                    ProviderAccountUsageDimension(
                        name="credits_per_minute",
                        unit="credits",
                        limit=8,
                        remaining=5,
                        consumed=3,
                        reset_at=datetime.now(UTC) + timedelta(seconds=30),
                    ),
                    ProviderAccountUsageDimension(
                        name="requests_per_day",
                        unit="requests",
                        limit=800,
                        remaining=763,
                        consumed=37,
                        reset_at=datetime.now(UTC).replace(
                            hour=0, minute=0, second=0, microsecond=0
                        )
                        + timedelta(days=1),
                    ),
                ),
            ),
        ),
        (
            "eodhd",
            "EODHD_API_KEY",
            ProviderAccountUsage(
                provider="eodhd",
                observed_at=datetime.now(UTC),
                unit="calls",
                account_plan="free",
                dimensions=(),
            ),
        ),
    ],
)
async def test_native_account_usage_bootstraps_unknown_provider_pools(
    db, monkeypatch, tmp_path, provider_name, setting_name, usage
):
    """Bootstrap may waive only unknown pools returned by that snapshot."""

    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, setting_name, "configured-key")
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_PATH",
        str(tmp_path / f"{provider_name}.sqlite3"),
    )
    await seed_provider_runtime(async_db)

    result = await execute_provider_call(
        async_db,
        ProviderCapability.ACCOUNT_USAGE,
        "fetch_account_usage",
        provider_name=provider_name,
        invoke=lambda _provider, _symbol: usage,
        response_items=lambda value: 1 if value is not None else 0,
        treat_empty_as_failure=True,
    )

    assert result.provider_name == provider_name
    summary = provider_quota_coordinator_summary(provider_name=provider_name)
    assert any(row["dimension"] == "account_usage_probe_concurrency" for row in summary["windows"])
    assert all(
        row["dimension"]
        not in {
            "credits_per_minute",
            "credits_per_day",
            "requests_per_day",
            "requests_per_minute",
            "calls_per_day",
        }
        for row in summary["windows"]
    )


@pytest.mark.asyncio
async def test_marketstack_history_route_requires_monthly_reset_review(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "MARKETSTACK_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "MARKETSTACK_DISCOVERY_EXCHANGE", "")
    # The public Free cap uses a conservative rolling-30-day window and needs
    # no account override. Simulate an account-specific fixed-month override;
    # it must remain non-routable until its quota evidence is supplied.
    monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_RESET", "fixed_month")
    monkeypatch.setattr(settings, "MARKETSTACK_QUOTA_EVIDENCE", "")

    await seed_provider_runtime(async_db)

    history_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        operation_cost_overrides={"marketstack": 1},
    )
    assert all(item.provider_name != "marketstack" for item in history_chain)

    discovery_chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.UNIVERSE_DISCOVERY,
        operation="discover_universe_page",
    )
    assert all(item.provider_name != "marketstack" for item in discovery_chain)


@pytest.mark.asyncio
async def test_history_route_enforces_seeded_provider_lookback_bound(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "MARKETSTACK_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", True)
    await seed_provider_runtime(async_db)

    now = datetime.now(UTC)
    within_bound = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        operation_cost_overrides={"marketstack": 1},
        history_start=now - timedelta(days=364),
    )
    beyond_bound = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_ohlcv:D1",
        operation_cost_overrides={"marketstack": 1},
        history_start=now - timedelta(days=367),
    )

    assert any(item.provider_name == "marketstack" for item in within_bound)
    assert all(item.provider_name != "marketstack" for item in beyond_bound)


@pytest.mark.asyncio
async def test_history_route_evaluates_provider_specific_start_factory(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "MARKETSTACK_API_KEY", "configured-key")
    monkeypatch.setattr(settings, "PROVIDER_OWNER_ACCEPTS_PROVIDER_TERMS_RISK", True)
    await seed_provider_runtime(async_db)

    now = datetime.now(UTC)
    seen: list[str] = []

    def provider_start(provider_name: str) -> datetime:
        seen.append(provider_name)
        return now - timedelta(days=364)

    chain = await resolve_provider_chain(
        async_db,
        ProviderCapability.PRICE_HISTORY,
        operation="fetch_latest_ohlcv:D1",
        operation_cost_overrides={"marketstack": 1},
        history_start=provider_start,
    )

    assert "marketstack" in seen
    assert any(item.provider_name == "marketstack" for item in chain)


@pytest.mark.asyncio
async def test_paid_routing_switch_does_not_bypass_unreviewed_entitlement(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    seeds = {
        name: value
        for name, value in settings.PROVIDER_ENTITLEMENT_SEEDS.items()
        if name != "alpaca"
    }
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", seeds)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", True)

    await seed_provider_runtime(async_db)
    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert entitlement.configured_plan == "unreviewed"
    assert entitlement.is_free is False

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)
    assert all(item.provider_name != "alpaca" for item in chain)


@pytest.mark.asyncio
async def test_dinari_sandbox_never_enters_normal_provider_routing_even_when_reviewed(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "dinari")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.TOKENIZED_ASSETS,
        )
    ).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.TOKENIZED_ASSETS,
        )
    ).scalar_one()
    policy.is_enabled = True
    policy.quota_scope = "api_key"
    policy.quota_source = "test-only complete Sandbox allowance"
    policy.quota_contract = {
        "reset": "calendar_day_utc",
        "dimensions": [
            {
                "name": "requests_per_day",
                "limit": 100,
                "window_seconds": 86400,
                "unit": "requests",
                "scope": "api_key",
                "quota_group": "dinari-sandbox-test",
                "source": "unit-test fixture only",
            }
        ],
    }
    entitlement.configured_plan = "reviewed-sandbox-fixture"
    entitlement.is_free = False
    entitlement.authentication_required = False
    entitlement.live_probe_status = "passed"
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", True)
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "fixture-id")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "fixture-secret")
    monkeypatch.setattr(
        "app.services.provider_runtime.seed_provider_runtime",
        lambda _db: _async_noop(),
    )

    chain = await resolve_provider_chain(async_db, ProviderCapability.TOKENIZED_ASSETS)

    assert all(item.provider_name != "dinari" for item in chain)


async def _async_noop():
    return None


@pytest.mark.asyncio
async def test_runtime_seeding_is_idempotent_for_entitlement_revisions(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    alpaca = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    first_count = (
        db.execute(
            select(ProviderEntitlementRevision).where(
                ProviderEntitlementRevision.data_source_id == alpaca.id,
                ProviderEntitlementRevision.capability == ProviderCapability.PRICE_HISTORY,
            )
        )
        .scalars()
        .all()
    )
    await seed_provider_runtime(async_db)
    second_count = (
        db.execute(
            select(ProviderEntitlementRevision).where(
                ProviderEntitlementRevision.data_source_id == alpaca.id,
                ProviderEntitlementRevision.capability == ProviderCapability.PRICE_HISTORY,
            )
        )
        .scalars()
        .all()
    )
    assert len(first_count) == len(second_count) == 1


@pytest.mark.asyncio
async def test_marketdata_trial_seed_keeps_dynamic_quota_and_revision_idempotent(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter_trial")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10_000)
    monkeypatch.setattr(
        settings,
        "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT",
        datetime(2030, 1, 1, tzinfo=UTC),
    )

    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "marketdata_app")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == source.id,
            ProviderEntitlement.capability == ProviderCapability.ACCOUNT_USAGE,
        )
    ).scalar_one()
    first_revision = entitlement.revision
    first_policy = dict(entitlement.quota_policy)

    await seed_provider_runtime(async_db)

    revisions = (
        db.execute(
            select(ProviderEntitlementRevision).where(
                ProviderEntitlementRevision.data_source_id == source.id,
                ProviderEntitlementRevision.capability == ProviderCapability.ACCOUNT_USAGE,
            )
        )
        .scalars()
        .all()
    )
    assert entitlement.configured_plan == "marketdata-starter_trial-operator-reviewed"
    assert entitlement.revision == first_revision
    assert entitlement.quota_policy == first_policy
    assert entitlement.quota_policy["contract"]["dimensions"][0]["limit"] == 10_000
    assert len(revisions) == 1


@pytest.mark.asyncio
async def test_reviewed_entitlement_upgrade_creates_next_revision(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    without_alpaca = {
        name: value
        for name, value in settings.PROVIDER_ENTITLEMENT_SEEDS.items()
        if name != "alpaca"
    }
    monkeypatch.setattr(settings, "PROVIDER_ENTITLEMENT_SEEDS", without_alpaca)
    await seed_provider_runtime(async_db)

    monkeypatch.setattr(
        settings,
        "PROVIDER_ENTITLEMENT_SEEDS",
        dict(
            settings.PROVIDER_ENTITLEMENT_SEEDS,
            alpaca={
                "configured_plan": "free-reviewed",
                "is_free": True,
                "authentication_required": True,
            },
        ),
    )
    await seed_provider_runtime(async_db)

    alpaca = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == alpaca.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    revisions = (
        db.execute(
            select(ProviderEntitlementRevision)
            .where(
                ProviderEntitlementRevision.data_source_id == alpaca.id,
                ProviderEntitlementRevision.capability == ProviderCapability.PRICE_HISTORY,
            )
            .order_by(ProviderEntitlementRevision.revision)
        )
        .scalars()
        .all()
    )
    assert entitlement.revision == 2
    assert [row.revision for row in revisions] == [1, 2]
    assert revisions[0].is_free is False
    assert revisions[1].is_free is True


@pytest.mark.asyncio
async def test_new_workstation_chain_excludes_implicit_yfinance_fallback(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    monkeypatch.setattr(settings, "ENABLE_LEGACY_YFINANCE_FALLBACK", False)

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)

    assert all(item.provider_name != "yfinance" for item in chain)


@pytest.mark.asyncio
async def test_otc_directory_requires_explicit_source_before_resolution(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_REVIEWED", False)
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_EVIDENCE", "")
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "")
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "")
    monkeypatch.setattr(
        settings,
        "PROVIDER_RATE_LIMIT_SEEDS",
        {
            **settings.PROVIDER_RATE_LIMIT_SEEDS,
            "finra_otc_directory": {
                "quota_contract": {
                    "reset": "fixed_minute",
                    "dimensions": [
                        {
                            "name": "requests",
                            "limit": 10,
                            "window_seconds": 60,
                            "unit": "requests",
                            "scope": "operator_source",
                            "source": "unit-test",
                        }
                    ],
                },
                "quota_scope": "operator_source",
                "quota_source": "unit-test FINRA OTC contract",
            },
        },
    )
    monkeypatch.setattr(
        settings,
        "PROVIDER_ENTITLEMENT_SEEDS",
        {
            **settings.PROVIDER_ENTITLEMENT_SEEDS,
            "finra_otc_directory": {
                "configured_plan": "operator-reviewed-directory",
                "is_free": True,
                "authentication_required": False,
                "live_probe_status": "passed",
            },
        },
    )

    await seed_provider_runtime(async_db)
    chain = await resolve_provider_chain(async_db, ProviderCapability.UNIVERSE_DISCOVERY)

    assert all(item.provider_name != "finra_otc_directory" for item in chain)

    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "")
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", "https://example.test/otc.txt")
    await seed_provider_runtime(async_db)
    chain = await resolve_provider_chain(async_db, ProviderCapability.UNIVERSE_DISCOVERY)

    # A source URL is necessary but not sufficient: source evidence and the
    # response-dependent pagination/terms controls are independent gates.
    assert all(item.provider_name != "finra_otc_directory" for item in chain)

    monkeypatch.setattr(
        settings,
        "FINRA_OTC_OPERATION_COSTS",
        {"discover_universe_page": 3, "reconcile_universe_page": 3},
    )
    monkeypatch.setattr(settings, "FINRA_OTC_TERMS_REVIEWED", True)
    monkeypatch.setattr(settings, "FINRA_OTC_COMPLETENESS_REVIEWED", True)
    monkeypatch.setattr(settings, "FINRA_OTC_REDISTRIBUTION_REVIEWED", True)
    monkeypatch.setattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", 900)
    await seed_provider_runtime(async_db)
    chain = await resolve_provider_chain(async_db, ProviderCapability.UNIVERSE_DISCOVERY)

    # Even every older cost/terms/completeness control cannot admit the
    # undocumented candidate before its source-specific evidence gate passes.
    assert all(item.provider_name != "finra_otc_directory" for item in chain)

    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_REVIEWED", True)
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_EVIDENCE", "FINRA support case 123")
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_KIND", "finra_orf_security_master")
    active_url = (
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?"
        "action=DOWNLOAD&file=EQUITYMASTERAC&facility=ORF"
    )
    inactive_url = (
        "https://apidownload.finratraqs.org/DownloadHandler.ashx?"
        "action=DOWNLOAD&file=EQUITYMASTERIN&facility=ORF"
    )
    monkeypatch.setattr(settings, "FINRA_OTC_SYMBOL_DIRECTORY_URL", active_url)
    monkeypatch.setattr(settings, "FINRA_OTC_REVIEWED_SOURCE_URL", active_url)
    monkeypatch.setattr(settings, "FINRA_OTC_INACTIVE_SECURITY_MASTER_URL", inactive_url)
    monkeypatch.setattr(settings, "FINRA_OTC_REVIEWED_INACTIVE_SOURCE_URL", inactive_url)
    monkeypatch.setattr(settings, "FINRA_ORF_USERNAME", "traqs-user")
    monkeypatch.setattr(settings, "FINRA_ORF_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setattr(
        settings, "FINRA_ORF_REFRESH_TOKEN_STATE_FILE", "/tmp/orf-refresh-token-state.json"
    )
    monkeypatch.setattr(settings, "FINRA_OTC_TERMS_REVIEWED", True)
    monkeypatch.setattr(settings, "FINRA_OTC_COMPLETENESS_REVIEWED", True)
    monkeypatch.setattr(settings, "FINRA_OTC_REDISTRIBUTION_REVIEWED", True)
    monkeypatch.setattr(settings, "FINRA_OTC_POLL_INTERVAL_SECONDS", 900)
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSED", True)
    monkeypatch.setattr(settings, "FINRA_ORF_CUSIP_LICENSE_EVIDENCE", "unit-test CGS license")
    await seed_provider_runtime(async_db)
    chain = await resolve_provider_chain(async_db, ProviderCapability.UNIVERSE_DISCOVERY)
    # All source/access/terms/quota evidence now matches the documented ORF
    # active/inactive files. No owner-storage attestation is involved.
    assert any(item.provider_name == "finra_otc_directory" for item in chain)


@pytest.mark.asyncio
async def test_otc_directory_default_entitlement_uses_verified_query_api_contract(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
    )
    monkeypatch.setattr(settings, "FINRA_CLIENT_ID", "configured-test-client")
    monkeypatch.setattr(settings, "FINRA_CLIENT_SECRET", "configured-test-secret")
    await seed_provider_runtime(async_db)
    chain = await resolve_provider_chain(async_db, ProviderCapability.UNIVERSE_DISCOVERY)

    assert any(item.provider_name == "finra_otc_directory" for item in chain)
    entitlement = db.execute(
        select(ProviderEntitlement).join(DataSource).where(DataSource.name == "finra_otc_directory")
    ).scalar_one()
    assert entitlement.configured_plan == "public-query-api"
    assert entitlement.live_probe_status == "credentialed_live_verified"


@pytest.mark.asyncio
async def test_explicit_legacy_yfinance_requires_a_verified_quota(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    monkeypatch.setattr(settings, "ENABLE_LEGACY_YFINANCE_FALLBACK", True)

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)

    assert all(item.provider_name != "yfinance" for item in chain)


@pytest.mark.asyncio
async def test_provider_chain_excludes_environment_ineligible_entitlements(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    entitlement.enabled_environments = ["production"]
    db.commit()
    monkeypatch.setattr("app.services.provider_runtime.settings.APP_ENV", "development")

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)

    assert all(item.provider_name != "alpaca" for item in chain)


@pytest.mark.asyncio
async def test_provider_chain_excludes_expired_entitlements(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    data_source = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    entitlement.review_due_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()

    chain = await resolve_provider_chain(async_db, ProviderCapability.PRICE_HISTORY)

    assert all(item.provider_name != "alpaca" for item in chain)


@pytest.mark.asyncio
async def test_seed_provider_runtime_backfills_missing_policy_defaults(db):
    async_db = AsyncSessionAdapter(db)
    data_source = DataSource(name="yfinance")
    db.add(data_source)
    db.flush()

    db.add(
        ProviderPolicy(
            data_source_id=data_source.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            base_priority=None,
            max_concurrency=None,
            tokens_per_minute=None,
            burst_capacity=None,
            cooldown_seconds=None,
            freshness_seconds=None,
            score_floor=None,
            score_ceiling=None,
            learned_weight=None,
            effective_score=None,
        )
    )
    db.add(
        ProviderHealthState(
            data_source_id=data_source.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            ewma_latency_ms=None,
            ewma_success_rate=None,
            ewma_completeness=None,
            ewma_freshness=None,
            ewma_consistency=None,
            observed_score=None,
        )
    )
    db.commit()

    await seed_provider_runtime(async_db)

    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == data_source.id,
            ProviderPolicy.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one()
    health = db.execute(
        select(ProviderHealthState).where(
            ProviderHealthState.data_source_id == data_source.id,
            ProviderHealthState.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one()

    assert policy.base_priority is not None
    assert policy.max_concurrency is None
    assert policy.tokens_per_minute is None
    assert policy.burst_capacity is None
    assert policy.cooldown_seconds is None
    assert policy.freshness_seconds is not None
    assert policy.score_floor == Decimal("0")
    assert policy.score_ceiling == Decimal("100")
    assert policy.learned_weight == Decimal("0")
    assert policy.effective_score is not None
    assert health.ewma_latency_ms == Decimal("0")
    assert health.ewma_success_rate == Decimal("1")
    assert health.ewma_completeness == Decimal("1")
    assert health.ewma_freshness == Decimal("1")
    assert health.ewma_consistency == Decimal("1")
    assert health.observed_score == policy.effective_score


@pytest.mark.asyncio
async def test_seed_provider_runtime_resyncs_unpinned_base_priority(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    monkeypatch.setattr(
        settings,
        "PROVIDER_CHAIN_SEEDS",
        {"instrument_search": ["edgar", "coingecko"]},
    )
    data_source = DataSource(name="coingecko")
    db.add(data_source)
    db.flush()

    db.add(
        ProviderPolicy(
            data_source_id=data_source.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            base_priority=10,
            is_pinned=False,
        )
    )
    db.add(
        ProviderHealthState(
            data_source_id=data_source.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
        )
    )
    db.commit()

    await seed_provider_runtime(async_db)

    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == data_source.id,
            ProviderPolicy.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one()

    expected_priority = (
        settings.PROVIDER_CHAIN_SEEDS["instrument_search"].index("coingecko") + 1
    ) * 10
    assert policy.base_priority == expected_priority


@pytest.mark.asyncio
async def test_provider_chain_ignores_stale_policy_for_unsupported_capability(db):
    """Old runtime rows must not call methods removed from a provider adapter."""
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    alpaca = db.execute(select(DataSource).where(DataSource.name == "alpaca")).scalar_one()
    stale_policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == alpaca.id,
            ProviderPolicy.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one_or_none()
    if stale_policy is None:
        stale_policy = ProviderPolicy(
            data_source_id=alpaca.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            is_enabled=True,
        )
        db.add(stale_policy)
    stale_policy.base_priority = 1
    # Runtime seeding creates entitlement/health rows for every adapter
    # capability.  Mutate those rows into a stale legacy record instead of
    # inserting a duplicate under the composite uniqueness constraint.
    stale_entitlement = db.execute(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == alpaca.id,
            ProviderEntitlement.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one_or_none()
    if stale_entitlement is None:
        stale_entitlement = ProviderEntitlement(
            data_source_id=alpaca.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            is_free=True,
        )
        db.add(stale_entitlement)
    stale_entitlement.configured_plan = "legacy"
    db.commit()

    chain = await resolve_provider_chain(async_db, ProviderCapability.INSTRUMENT_SEARCH)

    assert all(item.provider_name != "alpaca" for item in chain)
    stale_policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == alpaca.id,
            ProviderPolicy.capability == ProviderCapability.INSTRUMENT_SEARCH,
        )
    ).scalar_one()
    assert stale_policy.is_enabled is False


def test_bucket_rebuilds_when_policy_limits_change():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        tokens_per_minute=60,
        burst_capacity=15,
    )
    first = _get_bucket(policy, "alpaca")

    policy.tokens_per_minute = 120
    policy.burst_capacity = 30
    second = _get_bucket(policy, "alpaca")

    assert second is not first
    assert second.capacity == 30
    assert second.rate_per_second == pytest.approx(2.0)


def test_local_admission_controls_share_explicit_quota_group_across_capabilities():
    contract = {
        "reset": "rolling",
        "dimensions": [
            {
                "name": "requests_per_minute",
                "limit": 120,
                "window_seconds": 60,
                "unit": "requests",
                "scope": "api_key",
                "quota_group": "account",
                "source": "unit-test contract",
            },
            {
                "name": "concurrent_requests",
                "limit": 2,
                "window_seconds": 1,
                "unit": "concurrent_requests",
                "scope": "api_key",
                "quota_group": "account",
                "source": "unit-test contract",
            },
        ],
    }
    first_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        tokens_per_minute=120,
        burst_capacity=4,
        max_concurrency=2,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract=contract,
    )
    second_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        tokens_per_minute=120,
        burst_capacity=4,
        max_concurrency=2,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract=contract,
    )

    assert _get_bucket(first_policy, "shared-provider") is _get_bucket(
        second_policy, "shared-provider"
    )
    assert _get_semaphore(first_policy, "shared-provider") is _get_semaphore(
        second_policy, "shared-provider"
    )


def test_local_admission_controls_keep_ungrouped_capabilities_isolated():
    contract = {
        "reset": "rolling",
        "dimensions": [
            {
                "name": "requests_per_minute",
                "limit": 120,
                "window_seconds": 60,
                "unit": "requests",
                "scope": "api_key",
                "source": "unit-test contract",
            }
        ],
    }
    first_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        tokens_per_minute=120,
        burst_capacity=4,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract=contract,
    )
    second_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        tokens_per_minute=120,
        burst_capacity=4,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract=contract,
    )

    assert _get_bucket(first_policy, "isolated-provider") is not _get_bucket(
        second_policy, "isolated-provider"
    )


def test_token_bucket_charges_weighted_units():
    bucket = TokenBucket(rate_per_minute=60, burst_capacity=4)

    assert bucket.try_acquire(2)
    assert bucket.try_acquire(2)
    assert not bucket.try_acquire(2)


@pytest.mark.parametrize("units", [0, -1, True, 1.5, "1", None])
def test_token_bucket_rejects_invalid_acquisition_units(units):
    bucket = TokenBucket(rate_per_minute=60, burst_capacity=4)

    with pytest.raises(ProviderQuotaUnknownError):
        bucket.try_acquire(units)


@pytest.mark.parametrize(
    ("rate_per_minute", "burst_capacity"),
    [(0, 1), (1, 0), (-1, 1), (1, -1), (True, 1), (1, True)],
)
def test_token_bucket_rejects_invalid_provider_limits(rate_per_minute, burst_capacity):
    with pytest.raises(ProviderQuotaUnknownError):
        TokenBucket(rate_per_minute, burst_capacity)


def test_get_bucket_rejects_invalid_policy_limits():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        tokens_per_minute=0,
        burst_capacity=1,
    )
    with pytest.raises(ProviderQuotaUnknownError):
        _get_bucket(policy, "invalid-policy")


def test_semaphore_rebuilds_when_policy_concurrency_changes():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.OPTION_CHAIN,
        max_concurrency=2,
        base_priority=10,
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("0"),
    )
    first = _get_semaphore(policy, "yfinance")

    policy.max_concurrency = 5
    second = _get_semaphore(policy, "yfinance")

    assert second is not first
    assert second._value == 5
