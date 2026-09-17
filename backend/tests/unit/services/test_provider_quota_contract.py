from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

import app.config as app_config
from app.config import (
    FRED_MAPPED_SERIES_IDS,
    Settings,
    provider_quota_admission_reset,
    provider_quota_reset_is_admission_safe,
    provider_quota_reset_is_known,
    provider_rate_limit_seed,
    settings,
)
from app.models.data_source import DataSource
from app.models.market_data_foundation import ProviderQuotaIdentity, ProviderQuotaWindow
from app.models.provider_runtime import ProviderCapability, ProviderPolicy
from app.providers.registry import (
    ensure_data_source,
    get_provider_usage_profile,
    supported_provider_names,
)
from app.services.provider_routing import (
    _window_start_for_dimension,
    reserve_provider_contract,
    reserve_provider_quota,
    settle_provider_contract,
)
from app.services.provider_runtime import (
    ProviderQuotaUnknownError,
    ProviderRateLimitError,
    ResolvedProvider,
    _consumed_dimension_costs,
    _dimension_costs_for_operation,
    _observed_dimension_totals,
    policy_has_known_quota,
    provider_contract_operation_cost_known,
    provider_contract_operation_costs_configured,
    provider_rate_limit_error,
    quota_contract_missing_dimensions,
    quota_dimensions,
    seed_provider_runtime,
)
from tests.unit.conftest import AsyncSessionAdapter

INTENTIONAL_QUOTA_UNKNOWN_PROVIDERS = {
    # Public/provider-internal surfaces without a complete reviewed contract
    # in this branch. They stay visible to diagnostics but cannot be routed.
    "etf_holdings_internal",
    "fred",
    "finra_otc_directory",
    "yfinance",
    "ondo_global_markets",
    "dinari",
    "alpaca_itn",
}


def test_registered_providers_are_explicitly_quota_reviewed_or_intentionally_unknown():
    registered = set(supported_provider_names())
    assert INTENTIONAL_QUOTA_UNKNOWN_PROVIDERS <= registered

    for provider_name in registered:
        seed = settings.PROVIDER_RATE_LIMIT_SEEDS.get(provider_name)
        if provider_name in INTENTIONAL_QUOTA_UNKNOWN_PROVIDERS:
            if seed is None:
                continue
            contract = seed.get("quota_contract") or {}
            assert (
                not contract.get("dimensions")
                or contract.get("unknown_dimensions")
                or contract.get("untracked_constraints")
            ), provider_name
            continue

        assert isinstance(seed, dict), provider_name
        contract = seed.get("quota_contract")
        assert isinstance(contract, dict), provider_name
        dimensions = contract.get("dimensions")
        assert isinstance(dimensions, list) and dimensions, provider_name
        assert str(contract.get("reset") or "").strip(), provider_name
        for dimension in dimensions:
            assert all(
                str(dimension.get(field) or "").strip()
                for field in ("name", "unit", "scope", "source")
            ), (provider_name, dimension)
            assert int(dimension["limit"]) > 0, (provider_name, dimension)
            assert int(dimension["window_seconds"]) > 0, (provider_name, dimension)


def test_published_bandwidth_pools_use_conservative_decimal_byte_ceilings():
    assert (
        provider_rate_limit_seed("finra")["quota_contract"]["dimensions"][2]["limit"]
        == 10_000_000_000
    )
    assert (
        provider_rate_limit_seed("tiingo")["quota_contract"]["untracked_constraints"][0]["limit"]
        == 1_000_000_000
    )
    assert (
        provider_rate_limit_seed("fmp")["quota_contract"]["untracked_constraints"][0]["limit"]
        == 500_000_000
    )
    for provider_name in ("finra", "tiingo", "fmp"):
        contract = provider_rate_limit_seed(provider_name)["quota_contract"]
        dimensions = contract.get("dimensions", []) + contract.get("untracked_constraints", [])
        byte_pools = [item for item in dimensions if item.get("unit") == "bytes"]
        assert byte_pools
        assert all(
            str(item.get("limit_basis", "")).startswith("decimal_bytes_") for item in byte_pools
        )


def test_xstocks_and_bybit_public_quota_contracts_are_explicit_and_provider_scoped():
    xstocks = provider_rate_limit_seed("xstocks")["quota_contract"]
    assert (xstocks.get("unknown_dimensions") or []) == []
    assert xstocks["dimensions"] == [
        {
            "name": "public_requests_per_minute",
            "limit": 1000,
            "window_seconds": 60,
            "unit": "requests",
            "scope": "public_api",
            "quota_group": "public_api",
            "source": "https://docs.xstocks.fi/apis/openapi",
            "evidence": "The public assets and corporate-actions endpoints returned the same X-RateLimit-Limit/Remaining/Reset window (limit 1000) during bounded live validation on 2026-09-14.",
            "verified_at": "2026-09-14",
        }
    ]
    assert xstocks["reset"] == "rolling"

    bybit = provider_rate_limit_seed("bybit_xstocks")["quota_contract"]
    assert (bybit.get("unknown_dimensions") or []) == []
    assert bybit.get("untracked_constraints", []) == []
    assert bybit["dimensions"][0]["limit"] == 600
    assert bybit["dimensions"][0]["window_seconds"] == 5
    assert bybit["dimensions"][0]["scope"] == "ip"
    assert bybit.get("provider_headers_required") is not True


def test_provider_seeds_do_not_reintroduce_generic_limiter_defaults():
    """Production seeds must not silently resurrect the retired fallback policy."""

    for provider_name, seed in settings.PROVIDER_RATE_LIMIT_SEEDS.items():
        assert "cooldown_seconds" not in seed, provider_name
        assert "max_concurrency" not in seed, provider_name

    # Coinbase's burst is an explicitly documented provider-native exception,
    # not the old global fallback.  Keep the exception tied to its contract.
    coinbase = provider_rate_limit_seed("coinbase")
    assert coinbase["tokens_per_minute"] == 600
    assert coinbase["burst_capacity"] == 15
    assert coinbase["quota_contract"]["dimensions"][0]["limit"] == 10
    assert coinbase["quota_contract"]["dimensions"][0]["window_seconds"] == 1


def test_alpaca_native_minute_pool_uses_rolling_safety_envelope():
    alpaca = provider_rate_limit_seed("alpaca")["quota_contract"]
    assert alpaca["dimensions"][0]["limit"] == 200
    assert alpaca["reset"] == "rolling"
    assert alpaca["dimensions"][0]["name"] == "market_data_requests_per_minute"
    assert alpaca["account_usage_bootstrap"]["enabled"] is True
    alpaca_entitlement = settings.PROVIDER_ENTITLEMENT_SEEDS["alpaca"]
    assert alpaca_entitlement["quota_policy"]["latest_data_delay_seconds"] == 900
    assert alpaca_entitlement["quota_policy"]["websocket_symbol_limit"] == 30
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="account",
        quota_source="Alpaca market data API documentation",
        quota_contract=alpaca,
    )
    assert "quota_contract.dimensions[0].reset.unresolved" not in quota_contract_missing_dimensions(policy)

    massive = provider_rate_limit_seed("massive")["quota_contract"]
    assert massive["dimensions"][0]["limit"] == 5
    assert massive["reset"] == "provider_defined"
    assert massive["unknown_dimensions"] == ["requests_per_minute_reset_boundary"]

    edgar = provider_rate_limit_seed("edgar")["quota_contract"]
    assert edgar["dimensions"][0]["limit"] == 10
    assert edgar["reset"] == "provider_defined"
    assert edgar["unknown_dimensions"] == ["requests_per_second_reset_boundary"]

    alpha = provider_rate_limit_seed("alpha_vantage")["quota_contract"]
    assert alpha["dimensions"][0]["limit"] == 25
    assert alpha["reset"] == "provider_defined"
    assert alpha["unknown_dimensions"] == ["requests_per_day_reset_boundary"]

    for provider_name, dimension_name in (
        ("massive", "requests_per_minute"),
        ("edgar", "requests_per_second"),
        ("alpha_vantage", "requests_per_day"),
    ):
        contract = provider_rate_limit_seed(provider_name)["quota_contract"]
        dimension = next(item for item in contract["dimensions"] if item["name"] == dimension_name)
        assert dimension.get("reset") is None
        assert dimension["safety_reset"] == "rolling"
        assert provider_quota_admission_reset(
            dimension.get("reset"), dimension["safety_reset"]
        ) == "rolling"
        policy = ProviderPolicy(
            data_source_id=1,
            capability=ProviderCapability.PRICE_HISTORY,
            quota_scope=provider_name,
            quota_source=f"{provider_name} reviewed provider contract",
            quota_contract=contract,
        )
        assert quota_contract_missing_dimensions(policy) == []
        assert policy_has_known_quota(policy)

    finnhub = provider_rate_limit_seed("finnhub")["quota_contract"]
    assert all(item["safety_reset"] == "rolling" for item in finnhub["dimensions"])


def test_provider_quota_admission_reset_never_invents_a_boundary():
    assert provider_quota_admission_reset("provider_defined", "") == "provider_defined"
    assert provider_quota_admission_reset("provider_defined", "not-a-reset") == "provider_defined"
    assert provider_quota_admission_reset("rolling", "fixed_minute") == "rolling"

    fred = provider_rate_limit_seed("fred")["quota_contract"]
    assert fred["dimensions"][0]["reset"] == "provider_defined"
    assert fred["reset"] == "provider_defined"
    assert fred["unknown_dimensions"] == [
        "v1_enforcement_scope",
        "provider_adjustable_limits",
        "series_terms_and_redistribution",
        "requests_per_minute_reset_boundary",
    ]


def test_massive_reviewed_reset_promotes_only_explicit_evidence(monkeypatch):
    monkeypatch.setattr(settings, "MASSIVE_REVIEWED_RESET", "rolling")
    monkeypatch.setattr(settings, "MASSIVE_QUOTA_EVIDENCE", "operator review")
    contract = provider_rate_limit_seed("massive")["quota_contract"]
    assert contract["reset"] == "rolling"
    assert contract["unknown_dimensions"] == []
    assert contract["dimensions"][0]["reset"] == "rolling"

    monkeypatch.setattr(settings, "MASSIVE_REVIEWED_RESET", "fixed_minute")
    monkeypatch.setattr(settings, "MASSIVE_QUOTA_EVIDENCE", "")
    contract = provider_rate_limit_seed("massive")["quota_contract"]
    assert contract["reset"] == "provider_defined"
    assert contract["unknown_dimensions"] == ["requests_per_minute_reset_boundary"]


def test_edgar_reviewed_reset_promotes_only_explicit_evidence(monkeypatch):
    monkeypatch.setattr(settings, "EDGAR_REVIEWED_RESET", "rolling")
    monkeypatch.setattr(settings, "EDGAR_QUOTA_EVIDENCE", "operator review")
    contract = provider_rate_limit_seed("edgar")["quota_contract"]
    assert contract["reset"] == "rolling"
    assert contract["unknown_dimensions"] == []
    assert contract["dimensions"][0]["reset"] == "rolling"

    monkeypatch.setattr(settings, "EDGAR_REVIEWED_RESET", "fixed_minute")
    monkeypatch.setattr(settings, "EDGAR_QUOTA_EVIDENCE", "")
    contract = provider_rate_limit_seed("edgar")["quota_contract"]
    assert contract["reset"] == "provider_defined"
    assert contract["unknown_dimensions"] == ["requests_per_second_reset_boundary"]


def test_alpaca_reviewed_reset_promotes_only_explicit_evidence(monkeypatch):
    monkeypatch.setattr(settings, "ALPACA_REVIEWED_RESET", "rolling")
    monkeypatch.setattr(settings, "ALPACA_QUOTA_EVIDENCE", "operator review")
    contract = provider_rate_limit_seed("alpaca")["quota_contract"]
    assert contract["reset"] == "rolling"
    assert contract["unknown_dimensions"] == []
    assert contract["dimensions"][0]["reset"] == "rolling"

    monkeypatch.setattr(settings, "ALPACA_REVIEWED_RESET", "fixed_minute")
    monkeypatch.setattr(settings, "ALPACA_QUOTA_EVIDENCE", "")
    contract = provider_rate_limit_seed("alpaca")["quota_contract"]
    # An invalid optional override must not replace the safe rolling envelope.
    assert contract["reset"] == "rolling"
    assert contract["unknown_dimensions"] == ["operator_reset_override_invalid"]
    assert contract["dimensions"][0].get("reset") == "rolling"


def test_alpha_vantage_reviewed_reset_promotes_only_explicit_evidence(monkeypatch):
    monkeypatch.setattr(settings, "ALPHA_VANTAGE_REVIEWED_RESET", "calendar_day_utc")
    monkeypatch.setattr(settings, "ALPHA_VANTAGE_QUOTA_EVIDENCE", "operator review")
    contract = provider_rate_limit_seed("alpha_vantage")["quota_contract"]
    assert contract["reset"] == "calendar_day_utc"
    assert contract["unknown_dimensions"] == []
    assert contract["dimensions"][0]["reset"] == "calendar_day_utc"

    monkeypatch.setattr(settings, "ALPHA_VANTAGE_REVIEWED_RESET", "rolling")
    monkeypatch.setattr(settings, "ALPHA_VANTAGE_QUOTA_EVIDENCE", "")
    contract = provider_rate_limit_seed("alpha_vantage")["quota_contract"]
    assert contract["reset"] == "provider_defined"
    assert contract["unknown_dimensions"] == ["requests_per_day_reset_boundary"]


def test_fred_reset_requires_independent_current_evidence(monkeypatch):
    monkeypatch.setattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "api_key")
    monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 120)
    monkeypatch.setattr(settings, "FRED_REVIEWED_QUOTA_EVIDENCE", "provider-confirmed scope")
    monkeypatch.setattr(settings, "FRED_REVIEWED_RESET", "")
    monkeypatch.setattr(settings, "FRED_RESET_EVIDENCE", "")
    monkeypatch.setattr(settings, "FRED_PERSISTED_STORAGE_AUTHORIZED", True)
    monkeypatch.setattr(settings, "FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE", "written permission")
    monkeypatch.setattr(settings, "FRED_AUTOMATED_USE_AUTHORIZED", True)
    monkeypatch.setattr(settings, "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE", "written permission")
    monkeypatch.setattr(
        settings,
        "FRED_SERIES_RIGHTS_EVIDENCE",
        {series_id: "written series rights" for series_id in FRED_MAPPED_SERIES_IDS},
    )
    contract = provider_rate_limit_seed("fred")["quota_contract"]
    assert contract["reset"] == "provider_defined"
    assert "requests_per_minute_reset_boundary" in contract["unknown_dimensions"]


@pytest.mark.asyncio
async def test_seed_records_fred_v1_numeric_limit_without_applying_v2(db, monkeypatch):
    monkeypatch.setattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "")
    monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 0)
    monkeypatch.setattr(settings, "FRED_REVIEWED_QUOTA_EVIDENCE", "")
    monkeypatch.setattr(settings, "FRED_REVIEWED_RESET", "")
    monkeypatch.setattr(settings, "FRED_RESET_EVIDENCE", "")
    monkeypatch.setattr(settings, "FRED_PERSISTED_STORAGE_AUTHORIZED", False)
    monkeypatch.setattr(settings, "FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE", "")
    monkeypatch.setattr(settings, "FRED_AUTOMATED_USE_AUTHORIZED", False)
    monkeypatch.setattr(settings, "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE", "")
    monkeypatch.setattr(settings, "FRED_SERIES_RIGHTS_EVIDENCE", {})
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "fred")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert policy.quota_contract is not None
    assert policy.quota_contract["dimensions"] == [
        {
            "name": "requests_per_minute",
            "limit": 120,
            "window_seconds": 60,
            "unit": "requests",
            "scope": "provider_defined",
            "source": "https://fred.stlouisfed.org/docs/api/fred/errors.html",
            "reset": "provider_defined",
        }
    ]
    assert {
        "v1_enforcement_scope",
        "provider_adjustable_limits",
        "series_terms_and_redistribution",
        "requests_per_minute_reset_boundary",
    } <= set(policy.quota_contract["unknown_dimensions"])
    assert {
        "quota_contract.unknown_dimensions.v1_enforcement_scope",
        "quota_contract.unknown_dimensions.provider_adjustable_limits",
        "quota_contract.unknown_dimensions.series_terms_and_redistribution",
        "quota_contract.unknown_dimensions.requests_per_minute_reset_boundary",
    } <= set(quota_contract_missing_dimensions(policy))
    assert policy.tokens_per_minute is None
    assert policy.burst_capacity is None
    assert policy.max_concurrency is None
    assert policy.quota_verified_at is None
    assert not policy_has_known_quota(policy)


@pytest.mark.asyncio
async def test_reviewed_fred_controls_promote_only_the_explicit_conservative_contract(
    db, monkeypatch
):
    monkeypatch.setattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "api_key")
    monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 120)
    monkeypatch.setattr(settings, "FRED_REVIEWED_QUOTA_EVIDENCE", "provider-confirmed scope")
    monkeypatch.setattr(settings, "FRED_REVIEWED_RESET", "rolling")
    monkeypatch.setattr(settings, "FRED_RESET_EVIDENCE", "current provider/account review")
    monkeypatch.setattr(settings, "FRED_PERSISTED_STORAGE_AUTHORIZED", True)
    monkeypatch.setattr(
        settings,
        "FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE",
        "written permission for persisted data",
    )
    monkeypatch.setattr(settings, "FRED_AUTOMATED_USE_AUTHORIZED", True)
    monkeypatch.setattr(
        settings,
        "FRED_AUTOMATED_USE_AUTHORITY_EVIDENCE",
        "written automated-use permission",
    )
    monkeypatch.setattr(
        settings,
        "FRED_SERIES_RIGHTS_EVIDENCE",
        {series_id: "written series rights" for series_id in FRED_MAPPED_SERIES_IDS},
    )
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "fred")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert policy.quota_contract["unknown_dimensions"] == []
    assert policy.quota_contract["dimensions"][0]["limit"] == 120
    assert policy.quota_contract["dimensions"][0]["scope"] == "api_key"
    assert policy.quota_contract["dimensions"][0]["reset"] == "rolling"
    assert policy.quota_contract["reset"] == "rolling"
    assert quota_contract_missing_dimensions(policy) == []
    assert policy_has_known_quota(policy)


@pytest.mark.asyncio
async def test_seeded_tiingo_and_fmp_bandwidth_pools_remain_non_routable(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)

    for provider_name in ("tiingo", "fmp"):
        source = db.execute(select(DataSource).where(DataSource.name == provider_name)).scalar_one()
        policy = db.execute(
            select(ProviderPolicy).where(
                ProviderPolicy.data_source_id == source.id,
                ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
            )
        ).scalar_one()
        assert not policy_has_known_quota(policy)
        assert policy.quota_verified_at is None
        assert any(
            item.startswith("quota_contract.untracked_constraints.bandwidth_bytes")
            for item in quota_contract_missing_dimensions(policy)
        )


@pytest.mark.asyncio
async def test_runtime_seed_refreshes_provider_generated_contract_after_byte_map_change(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    complete_bounds = {
        "fetch_ohlcv": 1_000_000,
        "fetch_latest_ohlcv": 1_000_000,
        "get_current_price": 100_000,
        "bulk_fetch": 1_000_000,
        "search_instruments": 100_000,
        "get_instrument_profile": 100_000,
    }
    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", complete_bounds)
    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "tiingo")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.PRICE_HISTORY,
        )
    ).scalar_one()
    assert policy_has_known_quota(policy)
    assert quota_contract_missing_dimensions(policy) == []

    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", {})
    await seed_provider_runtime(async_db)
    db.refresh(policy)
    # A previously promoted contract is durable and is not silently destroyed
    # merely because a later process starts without the optional local byte map.
    assert policy_has_known_quota(policy)
    assert quota_contract_missing_dimensions(policy) == []


def test_known_request_limit_with_untracked_bandwidth_remains_non_routable():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_day",
                    "limit": 250,
                    "window_seconds": 86400,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "operator-dashboard",
                }
            ],
            "reset": "provider_defined_daily",
            "untracked_constraints": [
                {
                    "name": "bandwidth_per_30_days",
                    "limit": 512,
                    "unit": "megabytes",
                    "source": "operator-dashboard",
                }
            ],
        },
    )
    assert not policy_has_known_quota(policy)
    assert (
        "quota_contract.untracked_constraints.bandwidth_per_30_days"
        in quota_contract_missing_dimensions(policy)
    )


def test_unknown_quota_reset_semantics_fail_closed_in_runtime_contract():
    assert provider_quota_reset_is_known("provider_defined_daily")
    assert not provider_quota_reset_is_admission_safe("provider_defined_daily")
    assert provider_quota_reset_is_admission_safe("rolling")
    assert provider_quota_reset_is_admission_safe("fixed_second")
    assert not provider_quota_reset_is_known("one_request_per_whatever")
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test contract",
        quota_contract={
            "reset": "one_request_per_whatever",
            "dimensions": [
                {
                    "name": "requests",
                    "limit": 1,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test contract",
                }
            ],
        },
    )
    assert not quota_dimensions(policy)
    assert "quota_contract.reset.unknown" in quota_contract_missing_dimensions(policy)


def test_unresolved_provider_reset_cannot_be_converted_to_a_local_window():
    with pytest.raises(ProviderQuotaUnknownError, match="reset boundary is unresolved"):
        _window_start_for_dimension(
            {
                "name": "requests_per_day",
                "limit": 1,
                "window_seconds": 86400,
                "unit": "requests",
                "scope": "api_key",
                "source": "operator-dashboard",
            },
            reset="provider_defined",
            now=datetime(2026, 9, 5, 12, tzinfo=UTC),
        )


def test_per_dimension_without_dimension_reset_is_not_a_window():
    with pytest.raises(ProviderQuotaUnknownError, match="reset boundary is unresolved"):
        _window_start_for_dimension(
            {
                "name": "requests_per_day",
                "limit": 1,
                "window_seconds": 86400,
                "unit": "requests",
                "scope": "api_key",
                "source": "unit-test",
            },
            reset="per_dimension",
            now=datetime(2026, 9, 5, 12, tzinfo=UTC),
        )


def test_tiingo_byte_pool_uses_provider_scoped_reset_safety_envelopes(monkeypatch):
    bounds = {
        "fetch_ohlcv": 1_000_000,
        "fetch_latest_ohlcv": 1_000_000,
        "get_current_price": 100_000,
        "bulk_fetch": 1_000_000,
        "search_instruments": 100_000,
        "get_instrument_profile": 100_000,
    }
    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", bounds)
    monkeypatch.setattr(settings, "TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET", "")
    monkeypatch.setattr(settings, "TIINGO_REVIEWED_HOURLY_RESET", "")
    monkeypatch.setattr(settings, "TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE", "")
    monkeypatch.setattr(settings, "TIINGO_HOURLY_QUOTA_EVIDENCE", "")
    safety_seed = provider_rate_limit_seed("tiingo")
    safety_contract = safety_seed["quota_contract"]
    assert safety_contract["untracked_constraints"] == []
    assert safety_contract["unknown_dimensions"] == [
        "unique_symbols_reset_anchor",
        "requests_per_hour_reset_boundary_model",
    ]
    assert next(
        item
        for item in safety_contract["dimensions"]
        if item["name"] == "unique_symbols_per_month"
    )["safety_reset"] == "rolling_31_days"
    assert next(
        item
        for item in safety_contract["dimensions"]
        if item["name"] == "requests_per_hour"
    )["safety_reset"] == "rolling"
    assert safety_seed["_byte_reservation_bounds"] == bounds

    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", {"fetch_ohlcv": 1_000_000})
    blocked = provider_rate_limit_seed("tiingo")
    assert blocked["quota_contract"]["untracked_constraints"]
    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", bounds)
    monkeypatch.setattr(settings, "TIINGO_REVIEWED_UNIQUE_SYMBOL_RESET", "calendar_month_est")
    monkeypatch.setattr(settings, "TIINGO_REVIEWED_HOURLY_RESET", "rolling")
    monkeypatch.setattr(settings, "TIINGO_UNIQUE_SYMBOL_QUOTA_EVIDENCE", "symbol review")
    monkeypatch.setattr(settings, "TIINGO_HOURLY_QUOTA_EVIDENCE", "hourly review")
    seed = provider_rate_limit_seed("tiingo")
    contract = seed["quota_contract"]
    assert contract["untracked_constraints"] == []
    bytes_dimension = next(item for item in contract["dimensions"] if item["unit"] == "bytes")
    assert bytes_dimension["limit"] == 1_000_000_000
    assert contract["dimension_costs_required"] is True
    assert seed["_byte_reservation_bounds"] == bounds
    profile = get_provider_usage_profile("tiingo")
    assert profile["dimension_costs"][bytes_dimension["name"]] == bounds
    assert profile["operation_costs"]["fetch_ohlcv"] == 1
    assert profile["operation_costs"]["get_current_price"] == 1
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope=seed["quota_scope"],
        quota_source=seed["quota_source"],
        quota_contract=contract,
    )
    assert policy_has_known_quota(policy)
    assert quota_contract_missing_dimensions(policy) == []
    source = DataSource(
        name="tiingo",
        config={"usage_tracking": get_provider_usage_profile("tiingo")},
    )
    assert not provider_contract_operation_cost_known(policy, source, "fetch_ohlcv")
    assert provider_contract_operation_cost_known(
        policy, source, "fetch_ohlcv", usage_identity="AAPL"
    )
    assert provider_contract_operation_cost_known(
        policy, source, "get_current_price", usage_identity="AAPL"
    )
    assert provider_contract_operation_cost_known(
        policy, source, "bulk_fetch:d1", usage_identity="AAPL"
    )

    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", {"fetch_ohlcv": 1_000_000})
    assert provider_rate_limit_seed("tiingo")["quota_contract"].get("untracked_constraints")

    malformed = dict(bounds)
    malformed["get_current_price"] = True
    monkeypatch.setattr(settings, "TIINGO_OPERATION_BYTE_BOUNDS", malformed)
    seed = provider_rate_limit_seed("tiingo")
    assert seed["quota_contract"].get("untracked_constraints")


def test_fmp_byte_pool_uses_documented_trailing_window_and_daily_safety_envelope(monkeypatch):
    bounds = {
        "fetch_ohlcv": 1_000_000,
        "fetch_latest_ohlcv": 1_000_000,
        "get_current_price": 100_000,
        "bulk_fetch": 1_000_000,
        "get_instrument_profile": 100_000,
        "fetch_market_events": 100_000,
        "discover_universe_page": 100_000,
    }
    monkeypatch.setattr(settings, "FMP_OPERATION_BYTE_BOUNDS", bounds)
    monkeypatch.setattr(settings, "FMP_REVIEWED_DAILY_RESET", "")
    monkeypatch.setattr(settings, "FMP_REVIEWED_BANDWIDTH_RESET", "")
    monkeypatch.setattr(settings, "FMP_DAILY_QUOTA_EVIDENCE", "")
    monkeypatch.setattr(settings, "FMP_BANDWIDTH_QUOTA_EVIDENCE", "current plan evidence")
    promoted_by_safety = provider_rate_limit_seed("fmp")
    safety_contract = promoted_by_safety["quota_contract"]
    assert safety_contract["untracked_constraints"] == []
    assert safety_contract["unknown_dimensions"] == ["calls_daily_reset_anchor"]
    safety_daily = next(
        item for item in safety_contract["dimensions"] if item["name"] == "calls_per_day"
    )
    assert "reset" not in safety_daily
    assert safety_daily["safety_reset"] == "rolling"
    assert safety_contract["reset"] == "per_dimension"
    assert promoted_by_safety["_byte_reservation_bounds"] == bounds

    monkeypatch.setattr(settings, "FMP_BANDWIDTH_QUOTA_EVIDENCE", "")
    blocked = provider_rate_limit_seed("fmp")["quota_contract"]
    assert blocked["untracked_constraints"]
    assert blocked["unknown_dimensions"] == ["calls_daily_reset_anchor"]

    monkeypatch.setattr(settings, "FMP_REVIEWED_DAILY_RESET", "calendar_day_utc")
    monkeypatch.setattr(settings, "FMP_DAILY_QUOTA_EVIDENCE", "current account evidence")
    monkeypatch.setattr(settings, "FMP_BANDWIDTH_QUOTA_EVIDENCE", "current plan evidence")
    promoted = provider_rate_limit_seed("fmp")
    contract = promoted["quota_contract"]
    assert contract["unknown_dimensions"] == []
    assert contract["untracked_constraints"] == []
    assert contract["reset"] == "per_dimension"
    assert next(item for item in contract["dimensions"] if item["name"] == "calls_per_day")["reset"] == "calendar_day_utc"
    assert next(item for item in contract["dimensions"] if item["name"] == "bandwidth_bytes_per_30_days")["reset"] == "rolling_30_days"
    assert promoted["_byte_reservation_bounds"] == bounds

    monkeypatch.setattr(settings, "FMP_REVIEWED_BANDWIDTH_RESET", "not-a-reset")
    assert "bandwidth_bytes_per_30_days" in provider_rate_limit_seed("fmp")["quota_contract"]["untracked_constraints"][0]["name"]


def test_marketstack_monthly_limit_and_reset_require_account_review(monkeypatch):
    monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_LIMIT", 0)
    monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_RESET", "")
    monkeypatch.setattr(settings, "MARKETSTACK_QUOTA_EVIDENCE", "")
    blocked = provider_rate_limit_seed("marketstack")["quota_contract"]
    assert blocked["unknown_dimensions"] == [
        "published_monthly_limit_conflict",
        "monthly_cap_reset_boundary",
    ]

    monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_LIMIT", 10_000)
    monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_RESET", "calendar_month_utc")
    monkeypatch.setattr(settings, "MARKETSTACK_QUOTA_EVIDENCE", "current paid-plan review")
    promoted = provider_rate_limit_seed("marketstack")["quota_contract"]
    assert promoted["unknown_dimensions"] == []
    assert promoted["reset"] == "calendar_month_utc"
    dimension = next(item for item in promoted["dimensions"] if item["name"] == "requests_per_month")
    assert dimension["limit"] == 10_000
    assert dimension["reset"] == "calendar_month_utc"


def test_finra_async_download_requires_positive_bound_for_monthly_reservation(monkeypatch):
    source = DataSource(
        name="finra",
        config={"usage_tracking": settings.PROVIDER_USAGE_PROFILE_SEEDS["finra"]},
    )
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["finra"]
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.SHORT_INTEREST,
        quota_contract=seed["quota_contract"],
    )
    assert not provider_contract_operation_cost_known(policy, source, "download_async_result")

    monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", 4 * 1024 * 1024)
    source.config = {"usage_tracking": get_provider_usage_profile("finra")}
    profile = source.config["usage_tracking"]
    assert profile["operation_costs"]["download_async_result"] == 1
    assert (
        profile["dimension_costs"]["download_bytes_per_calendar_month"]["download_async_result"]
        == 4 * 1024 * 1024
    )
    assert provider_contract_operation_cost_known(policy, source, "download_async_result")


def test_finra_async_boolean_bound_does_not_promote_bandwidth_profile(monkeypatch):
    monkeypatch.setattr(settings, "FINRA_ASYNC_MAX_RESULT_BYTES", True)
    profile = get_provider_usage_profile("finra")
    assert "download_async_result" not in profile["operation_costs"]
    assert (
        "download_async_result"
        not in profile["dimension_costs"]["download_bytes_per_calendar_month"]
    )


def test_fred_quota_review_alone_does_not_authorize_persisted_usage(monkeypatch):
    monkeypatch.setattr(settings, "FRED_REVIEWED_LIMIT_SCOPE", "api_key")
    monkeypatch.setattr(settings, "FRED_REVIEWED_REQUESTS_PER_MINUTE", 60)
    monkeypatch.setattr(settings, "FRED_REVIEWED_QUOTA_EVIDENCE", "provider-confirmed scope")
    monkeypatch.setattr(settings, "FRED_REVIEWED_RESET", "rolling")
    monkeypatch.setattr(settings, "FRED_RESET_EVIDENCE", "current provider/account review")
    monkeypatch.setattr(settings, "FRED_PERSISTED_STORAGE_AUTHORITY_EVIDENCE", "written permission")
    monkeypatch.setattr(settings, "FRED_PERSISTED_STORAGE_AUTHORIZED", False)
    seed = provider_rate_limit_seed("fred")
    assert seed["quota_contract"].get("unknown_dimensions")


def test_finra_authenticated_dataset_usage_covers_cold_oauth_token_request():
    profile = get_provider_usage_profile("finra")
    assert profile["operation_costs"]["fetch_short_interest"] == 2
    assert profile["operation_costs"]["fetch_market_events"] == 2


def test_edgar_metadata_and_events_cover_cold_ticker_directory_lookup():
    profile = get_provider_usage_profile("edgar")
    assert profile["operation_costs"]["discover_issuer_ciks_page"] == 1
    assert profile["operation_costs"]["get_instrument_profile"] == 2
    assert profile["operation_costs"]["fetch_instrument_events"] == 2
    assert profile["operation_costs"]["fetch_ipo_pipeline_events"] == 1


def test_massive_corporate_actions_reserve_two_endpoint_requests():
    profile = get_provider_usage_profile("massive")
    assert profile["operation_costs"]["fetch_instrument_events"] == 2


@pytest.mark.asyncio
async def test_quota_windows_are_isolated_by_dimension(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="multi-window", is_active=True)
    db.add(source)
    db.flush()
    now = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    minute = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="price_history",
        dimension="per_minute",
        units=1,
        limit_units=2,
        window_seconds=60,
        now=now,
    )
    month = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="price_history",
        dimension="per_month",
        units=1,
        limit_units=10,
        window_seconds=2_678_400,
        now=now,
    )
    assert minute is not None and month is not None
    rows = db.execute(select(ProviderQuotaWindow)).scalars().all()
    assert {row.dimension for row in rows} == {"per_minute", "per_month"}


@pytest.mark.asyncio
async def test_distinct_identity_dimension_is_durable_and_not_request_counted(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="distinct-symbol-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "provider_defined",
            "dimensions": [
                {
                    "name": "unique_symbols_per_month",
                    "limit": 2,
                    "window_seconds": 2_678_400,
                    "unit": "symbols",
                    "scope": "api_key",
                    "source": "https://provider.example/pricing",
                    "reset": "calendar_month_est",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="distinct-symbol-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        usage_identity="aapl",
        now=now,
    )
    repeat = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        usage_identity="AAPL",
        now=now,
    )
    second = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        usage_identity="MSFT",
        now=now,
    )
    exhausted = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        usage_identity="NVDA",
        now=now,
    )
    assert first is not None and len(first) == 1
    assert repeat == []
    assert second is not None and len(second) == 1
    assert exhausted is None
    identities = db.execute(select(ProviderQuotaIdentity)).scalars().all()
    assert {row.identity_key for row in identities} == {"AAPL", "MSFT"}
    settle_provider_contract(
        first,
        units=1,
        success=False,
        reserved_dimension_units={"unique_symbols_per_month": 1},
        consumed_dimension_units={"unique_symbols_per_month": 1},
        consume_on_failure_dimensions={"unique_symbols_per_month"},
    )
    db.flush()
    window = db.execute(
        select(ProviderQuotaWindow).where(
            ProviderQuotaWindow.dimension == "unique_symbols_per_month"
        )
    ).scalar_one()
    assert window.consumed_units == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid_units", [True, 1.5, "1", -1])
async def test_contract_reservation_rejects_malformed_dimension_units(db, invalid_units):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="invalid-dimension-units-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test provider contract",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="invalid-dimension-units-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )

    result = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        dimension_units={"requests_per_minute": invalid_units},
        now=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
    )

    assert result is None
    assert db.query(ProviderQuotaWindow).count() == 0


@pytest.mark.asyncio
async def test_rolling_quota_reservation_accumulates_across_second_buckets(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="rolling-provider", is_active=True)
    db.add(source)
    db.flush()
    now = datetime(2026, 9, 5, 12, 0, 10, tzinfo=UTC)
    first = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="latest_price",
        dimension="per_minute",
        units=2,
        limit_units=3,
        window_seconds=60,
        now=now,
        rolling=True,
    )
    second = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="latest_price",
        dimension="per_minute",
        units=1,
        limit_units=3,
        window_seconds=60,
        now=now + timedelta(seconds=1),
        rolling=True,
    )
    rejected = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="latest_price",
        dimension="per_minute",
        units=1,
        limit_units=3,
        window_seconds=60,
        now=now + timedelta(seconds=2),
        rolling=True,
    )
    after_expiry = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="latest_price",
        dimension="per_minute",
        units=1,
        limit_units=3,
        window_seconds=60,
        now=now + timedelta(seconds=61),
        rolling=True,
    )
    assert first is not None and second is not None
    assert rejected is None
    assert after_expiry is not None


def test_rate_limit_error_honors_retry_after_and_status():
    response = httpx.Response(
        429,
        headers={"Retry-After": "7", "X-RateLimit-Limit": "5"},
        request=httpx.Request("GET", "https://provider.example/data"),
    )
    exc = httpx.HTTPStatusError(
        "429 Too Many Requests", request=response.request, response=response
    )
    typed = provider_rate_limit_error("example", exc, scope="api_key")
    assert isinstance(typed, ProviderRateLimitError)
    assert typed.status_code == 429
    assert typed.scope == "api_key"
    assert typed.retry_at is not None
    assert 6 <= (typed.retry_at - datetime.now(UTC)).total_seconds() <= 8


def test_ip_ban_status_is_typed_as_provider_capacity_failure():
    response = httpx.Response(
        418,
        headers={"Retry-After": "120"},
        request=httpx.Request("GET", "https://provider.example/data"),
    )
    exc = httpx.HTTPStatusError("418 IP banned", request=response.request, response=response)
    typed = provider_rate_limit_error("example", exc, scope="ip")
    assert isinstance(typed, ProviderRateLimitError)
    assert typed.status_code == 418
    assert typed.scope == "ip"


def test_existing_typed_capacity_error_is_preserved_for_durable_event_recording():
    typed = ProviderRateLimitError(
        "example",
        "provider quota exceeded",
        status_code=429,
        headers={"Authorization": "must-not-be-persisted", "Retry-After": "5"},
    )
    preserved = provider_rate_limit_error("example", typed, scope="api_key")
    assert preserved is typed
    assert preserved.scope == "api_key"


def test_provider_rate_limit_error_derives_reset_for_typed_adapter_error():
    typed = ProviderRateLimitError(
        "example",
        "provider quota exceeded",
        status_code=429,
        headers={"Retry-After": "7"},
    )

    before = datetime.now(UTC) + timedelta(seconds=6)
    preserved = provider_rate_limit_error("example", typed, scope="api_key")
    after = datetime.now(UTC) + timedelta(seconds=8)

    assert preserved is typed
    assert preserved.scope == "api_key"
    assert preserved.retry_at is not None
    assert before <= preserved.retry_at <= after


def test_non_capacity_http_error_is_not_misclassified():
    response = httpx.Response(500, request=httpx.Request("GET", "https://provider.example/data"))
    exc = httpx.HTTPStatusError("500 Server Error", request=response.request, response=response)
    assert provider_rate_limit_error("example", exc) is None


def test_dynamic_endpoint_contract_is_non_routable_without_operation_costs():
    source = DataSource(name="binance", config={"usage_tracking": {"operation_costs": {}}})
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.CRYPTO_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "weight",
                    "limit": 1200,
                    "window_seconds": 60,
                    "unit": "weight",
                    "scope": "ip",
                    "source": "unit-test",
                }
            ],
            "reset": "fixed_minute",
            "dynamic_endpoint_weights": True,
        },
    )
    assert not provider_contract_operation_cost_known(policy, source)
    assert not provider_contract_operation_cost_known(policy, source, "fetch_ohlcv")
    assert provider_contract_operation_cost_known(
        policy, source, "fetch_ohlcv", operation_cost_override=4
    )


def test_simple_request_contract_is_non_routable_without_operation_costs():
    source = DataSource(name="unprofiled-provider", config={"usage_tracking": {}})
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 60,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test",
                }
            ],
            "reset": "rolling",
        },
    )
    assert not provider_contract_operation_cost_known(policy, source, "get_current_price")
    source.config["usage_tracking"] = {"operation_costs": {"get_current_price": 1}}
    assert provider_contract_operation_cost_known(policy, source, "get_current_price")
    source.config["usage_tracking"]["operation_costs"]["get_current_price"] = 0
    assert not provider_contract_operation_cost_known(policy, source, "get_current_price")
    source.config["usage_tracking"]["operation_costs"]["get_current_price"] = "not-a-cost"
    assert not provider_contract_operation_cost_known(policy, source, "get_current_price")
    assert not provider_contract_operation_cost_known(
        policy, source, "get_current_price", operation_cost_override=0
    )


@pytest.mark.parametrize("invalid_cost", [0.5, Decimal("1.5"), True, "1.5"])
def test_operation_costs_reject_non_integral_values(invalid_cost):
    source = DataSource(
        name="fractional-cost-provider",
        config={"usage_tracking": {"operation_costs": {"get_current_price": invalid_cost}}},
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 60,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test",
                }
            ],
            "reset": "rolling",
        },
    )

    assert not provider_contract_operation_cost_known(policy, source, "get_current_price")
    assert not provider_contract_operation_cost_known(
        policy, source, "get_current_price", operation_cost_override=invalid_cost
    )


@pytest.mark.parametrize("invalid_reserved", [True, 1.5, "1", -1])
def test_settlement_measurement_rejects_malformed_reserved_units(invalid_reserved):
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "response_bytes",
                    "limit": 1000,
                    "window_seconds": 60,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "unit-test",
                }
            ],
        },
    )

    with pytest.raises(ProviderQuotaUnknownError):
        _consumed_dimension_costs(
            policy,
            SimpleNamespace(http_requests=1, response_bytes=10),
            {"response_bytes": invalid_reserved},
        )


def test_byte_dimension_requires_explicit_operation_bound():
    source = DataSource(
        name="byte-provider",
        config={
            "usage_tracking": {
                "operation_costs": {"fetch_short_interest": 1},
                "dimension_costs": {
                    "download_bytes_per_month": {"fetch_short_interest": 3_000_000}
                },
            }
        },
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.SHORT_INTEREST,
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 1200,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "ip",
                    "source": "unit-test",
                },
                {
                    "name": "download_bytes_per_month",
                    "limit": 10_000_000,
                    "window_seconds": 2_678_400,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "unit-test",
                },
                {
                    "name": "async_requests_per_minute",
                    "limit": 20,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "dataset",
                    "source": "unit-test",
                },
            ],
            "reset": "calendar_month",
            "dimension_costs_required": True,
        },
    )
    assert provider_contract_operation_cost_known(policy, source, "fetch_short_interest")
    source.config["usage_tracking"]["dimension_costs"]["requests_per_minute"] = {
        "fetch_short_interest": 0
    }
    assert not provider_contract_operation_cost_known(policy, source, "fetch_short_interest")
    with pytest.raises(ProviderQuotaUnknownError):
        _dimension_costs_for_operation(policy, source, "fetch_short_interest", default_units=1)
    source.config["usage_tracking"]["dimension_costs"].pop("requests_per_minute")
    for invalid_bound in (0, -1, True, 1.5, "not-a-bound"):
        source.config["usage_tracking"]["dimension_costs"]["download_bytes_per_month"][
            "fetch_short_interest"
        ] = invalid_bound
        assert not provider_contract_operation_cost_known(policy, source, "fetch_short_interest")
        with pytest.raises(ProviderQuotaUnknownError):
            _dimension_costs_for_operation(policy, source, "fetch_short_interest", default_units=1)
    source.config["usage_tracking"]["dimension_costs"]["download_bytes_per_month"][
        "fetch_short_interest"
    ] = 3_000_000
    source.config["usage_tracking"].pop("dimension_costs")
    assert not provider_contract_operation_cost_known(policy, source, "fetch_short_interest")


def test_operation_and_dimension_costs_may_be_carried_in_reviewed_contract():
    source = DataSource(name="contract-cost-provider", config={})
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.SHORT_INTEREST,
        quota_contract={
            "dimensions": [
                {
                    "name": "download_bytes",
                    "limit": 1000,
                    "window_seconds": 60,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "operator-review",
                }
            ],
            "reset": "rolling",
            "operation_costs_required": True,
            "operation_costs": {"fetch_short_interest": 1},
            "dimension_costs_required": True,
            "dimension_costs": {"download_bytes": {"fetch_short_interest": 100}},
        },
    )
    assert provider_contract_operation_cost_known(policy, source, "fetch_short_interest")


def test_operation_cost_readiness_uses_reviewed_contract_map():
    source = DataSource(name="contract-cost-provider", config={})
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "request_weight",
                    "limit": 100,
                    "window_seconds": 60,
                    "unit": "weight",
                    "scope": "ip",
                    "source": "operator-review",
                }
            ],
            "reset": "rolling",
            "dynamic_endpoint_weights": True,
            "operation_costs": {"fetch_ohlcv": 4},
        },
    )
    assert provider_contract_operation_costs_configured(policy, source)


@pytest.mark.asyncio
async def test_dimension_reservation_settles_observed_bytes_without_charging_request_units(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="byte-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.SHORT_INTEREST,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test",
                },
                {
                    "name": "download_bytes_per_month",
                    "limit": 10_000,
                    "window_seconds": 2_678_400,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "unit-test",
                },
                {
                    "name": "async_requests_per_minute",
                    "limit": 20,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "dataset",
                    "source": "unit-test",
                },
            ],
            "reset": "calendar_month",
        },
    )
    resolved = ResolvedProvider(
        provider_name="byte-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    windows = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.SHORT_INTEREST.value,
        units=1,
        dimension_units={
            "requests_per_minute": 1,
            "download_bytes_per_month": 3_000,
            "async_requests_per_minute": 0,
        },
        now=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
    )
    assert windows is not None
    settle_provider_contract(
        windows,
        units=1,
        reserved_dimension_units={
            "requests_per_minute": 1,
            "download_bytes_per_month": 3_000,
            "async_requests_per_minute": 0,
        },
        consumed_dimension_units={
            "requests_per_minute": 1,
            "download_bytes_per_month": 1_200,
        },
    )
    rows = {row.dimension: row for row in db.execute(select(ProviderQuotaWindow)).scalars().all()}
    assert rows["requests_per_minute"].consumed_units == 1
    assert rows["download_bytes_per_month"].consumed_units == 1_200
    assert "async_requests_per_minute" not in rows
    assert all(row.reserved_units == 0 for row in rows.values())


def test_binance_seed_tracks_current_spot_ceiling_but_stays_dynamic_cost_gated():
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["binance"]
    contract = seed["quota_contract"]
    assert contract["dimensions"][0]["limit"] == 6000
    assert contract["dimensions"][0]["unit"] == "weight"
    assert contract["dynamic_endpoint_weights"] is True
    assert contract["reset"] == "per_dimension"
    assert contract["account_usage_bootstrap"]["enabled"] is True
    assert contract["dimensions"][1]["name"] == "account_usage_probe_concurrency"


def test_binance_only_admits_operations_with_exact_documented_weights():
    source = DataSource(name="binance")
    source.config = {"usage_tracking": settings.PROVIDER_USAGE_PROFILE_SEEDS["binance"]}
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["binance"]
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        quota_contract=seed["quota_contract"],
    )
    assert provider_contract_operation_cost_known(policy, source, "get_current_price")
    assert not provider_contract_operation_cost_known(policy, source, "fetch_ohlcv:1d")


def test_marketstack_and_ibkr_use_provider_specific_pacing_contracts():
    marketstack = settings.PROVIDER_RATE_LIMIT_SEEDS["marketstack"]["quota_contract"]
    assert marketstack["dimensions"][0]["limit"] == 100
    assert marketstack["dimensions"][0]["window_seconds"] == 2_592_000
    assert marketstack["reset"] == "provider_defined"
    assert marketstack["unknown_dimensions"] == [
        "published_monthly_limit_conflict",
        "monthly_cap_reset_boundary",
    ]
    assert marketstack["source_conflicts"][0] == {
        "source": "https://marketstack.com/faq",
        "claim": "1,000 requests per month",
        "conflicts_with": "https://marketstack.com/pricing",
    }
    assert marketstack["usage_semantics"] == {
        "multi_symbol_request": "one_request_per_symbol",
        "api_errors_counted": False,
        "notifications_at_fraction": [0.75, 0.90, 1.00],
        "maximum_overdraft_fraction": 0.05,
        "disable_at_fraction_without_overage_billing": 1.20,
        "overage_billing": "account_configurable",
        "source": "https://marketstack.com/faq",
    }

    ibkr = settings.PROVIDER_RATE_LIMIT_SEEDS["ibkr"]["quota_contract"]
    assert {
        dimension["name"]: dimension["limit"] for dimension in ibkr["dimensions"]
    } == {
        "global_requests_per_second": 10,
        "historical_requests_per_minute": 50,
    }
    assert all(dimension["unit"] != "concurrent_requests" for dimension in ibkr["dimensions"])
    assert all(
        dimension["source"].startswith("https://ibkrcampus.com/")
        for dimension in ibkr["dimensions"]
    )
    assert ibkr["endpoint_constraints"]["iserver/marketdata/history"]["max_response_points"] == 1000
    usage = settings.PROVIDER_USAGE_PROFILE_SEEDS["ibkr"]
    assert usage["operation_costs"]["get_current_price"] == 2
    assert usage["dimension_costs"]["historical_requests_per_minute"]["get_current_price"] == {}
    assert "historical_requests_concurrent" not in usage["dimension_costs"]


def test_nasdaq_directory_uses_a_client_imposed_daily_ceiling_not_a_vendor_quota():
    contract = provider_rate_limit_seed("nasdaq")["quota_contract"]
    dimension = contract["dimensions"][0]
    assert dimension["limit"] == 2
    assert dimension["window_seconds"] == 86_400
    assert dimension["scope"] == "deployment"
    assert dimension["source"].startswith("application_policy:")
    assert "does not publish a numeric quota" in provider_rate_limit_seed("nasdaq")["quota_source"]


def test_openfigi_switches_between_exact_anonymous_and_keyed_contracts(monkeypatch):
    monkeypatch.setattr(settings, "OPENFIGI_API_KEY", "")
    anonymous = provider_rate_limit_seed("openfigi")
    anonymous_dimension = anonymous["quota_contract"]["dimensions"][0]
    assert anonymous_dimension["name"] == "mapping_requests_per_minute"
    assert anonymous_dimension["limit"] == 25
    assert anonymous_dimension["window_seconds"] == 60
    assert anonymous_dimension["scope"] == "ip"
    assert anonymous["tokens_per_minute"] == 25
    assert anonymous["quota_contract"]["endpoint_constraints"]["mapping"][
        "max_jobs_per_request"
    ] == 5
    assert (
        anonymous["quota_contract"]["dimensions"][1]["name"]
        == "account_usage_probe_concurrency"
    )
    assert anonymous["quota_contract"]["account_usage_bootstrap"]["enabled"] is True

    monkeypatch.setattr(settings, "OPENFIGI_API_KEY", "reviewed-key")
    keyed = provider_rate_limit_seed("openfigi")
    keyed_dimension = keyed["quota_contract"]["dimensions"][0]
    assert keyed_dimension["name"] == "mapping_requests_per_6_seconds"
    assert keyed_dimension["limit"] == 25
    assert keyed_dimension["window_seconds"] == 6
    assert keyed_dimension["scope"] == "api_key"
    assert "tokens_per_minute" not in keyed
    assert keyed["quota_contract"]["endpoint_constraints"]["mapping"][
        "max_jobs_per_request"
    ] == 100
    assert (
        keyed["quota_contract"]["dimensions"][1]["name"]
        == "account_usage_probe_concurrency"
    )


def test_marketdata_app_records_documented_daily_credit_and_concurrency_limits():
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["marketdata_app"]
    contract = seed["quota_contract"]
    assert contract["dimensions"][0]["limit"] == 100
    assert contract["reset"] == "09:30 America/New_York"
    assert contract["dimensions"][1]["name"] == "concurrent_requests"
    assert contract["dimensions"][1]["limit"] == 50
    assert contract["dimensions"][1]["unit"] == "concurrent_requests"
    assert seed.get("max_concurrency") is None
    assert {item["quota_group"] for item in contract["dimensions"]} == {"account"}

    profile = get_provider_usage_profile("marketdata_app")
    assert profile["operation_costs"]["fetch_account_usage"] == 1
    # /user/ is an account-introspection read: it must be admitted and
    # tracked, but the native x-api-ratelimit-consumed counter proves that it
    # does not spend the daily credit pool. The concurrent-request dimension
    # remains reserved normally because it is not excluded here.
    assert profile["dimension_costs"]["credits_per_day"]["fetch_account_usage"] == {}

    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.ACCOUNT_USAGE,
        quota_scope=seed["quota_scope"],
        quota_source=seed["quota_source"],
        quota_contract=contract,
    )
    source = DataSource(name="marketdata_app", config={"usage_tracking": profile})
    assert provider_contract_operation_cost_known(policy, source, "fetch_account_usage")
    assert _dimension_costs_for_operation(
        policy, source, "fetch_account_usage", default_units=1
    ) == {"credits_per_day": 0, "concurrent_requests": 1}


def test_twelve_data_account_usage_uses_one_reviewed_credit_per_native_snapshot():
    profile = get_provider_usage_profile("twelve_data")
    assert profile["operation_costs"]["fetch_account_usage"] == 1
    seed = provider_rate_limit_seed("twelve_data")
    dimensions = seed["quota_contract"]["dimensions"]
    assert [item["name"] for item in dimensions] == [
        "credits_per_minute",
        "credits_per_day",
        "account_usage_probe_concurrency",
    ]
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.ACCOUNT_USAGE,
        quota_scope=seed["quota_scope"],
        quota_source=seed["quota_source"],
        quota_contract=seed["quota_contract"],
    )
    source = DataSource(name="twelve_data", config={"usage_tracking": profile})
    assert provider_contract_operation_cost_known(policy, source, "fetch_account_usage")
    assert _dimension_costs_for_operation(
        policy, source, "fetch_account_usage", default_units=1
    ) == {
        "credits_per_minute": 1,
        "credits_per_day": 1,
        "account_usage_probe_concurrency": 1,
    }
    assert _dimension_costs_for_operation(
        policy, source, "fetch_ohlcv", default_units=1
    )["account_usage_probe_concurrency"] == 0


def test_account_and_ip_scoped_provider_contracts_declare_cross_capability_groups():
    grouped_providers = {
        "alpaca",
        "massive",
        "alpha_vantage",
        "openfigi",
        "edgar",
        "finra",
        "coingecko",
        "binance",
        "coinbase",
        "robinhood_tokens",
        "bybit_xstocks",
        "gate_tradfi",
        "tiingo",
        "twelve_data",
        "finnhub",
        "eodhd",
        "fmp",
        "marketdata_app",
        "tradier",
        "marketstack",
        "ibkr",
    }
    for provider_name in grouped_providers:
        dimensions = settings.PROVIDER_RATE_LIMIT_SEEDS[provider_name]["quota_contract"][
            "dimensions"
        ]
        assert dimensions, provider_name
        assert all(str(item.get("quota_group") or "").strip() for item in dimensions), provider_name


@pytest.mark.asyncio
async def test_explicit_quota_group_shares_one_budget_across_capabilities(db):
    """Provider account budgets must not be multiplied by capability."""

    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="account-budget-provider", is_active=True)
    db.add(source)
    db.flush()
    contract = {
        "reset": "rolling",
        "dimensions": [
            {
                "name": "credits_per_day",
                "limit": 3,
                "window_seconds": 86400,
                "unit": "credits",
                "scope": "api_key",
                "quota_group": "account",
                "source": "https://provider.example/rate-limits",
            }
        ],
    }
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract=contract,
    )
    resolved = ResolvedProvider(
        provider_name="account-budget-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=2,
        now=now,
    )
    second = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.LATEST_PRICE.value,
        units=2,
        now=now,
    )

    assert first is not None and len(first) == 1
    assert second is None
    row = db.execute(select(ProviderQuotaWindow)).scalar_one()
    assert row.quota_group == "account"
    assert row.reserved_units == 2


@pytest.mark.asyncio
async def test_ungrouped_quota_dimensions_remain_capability_scoped(db):
    """No provider grouping is inferred when a contract omits the marker."""

    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="capability-budget-provider", is_active=True)
    db.add(source)
    db.flush()
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    first = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY.value,
        dimension="requests_per_minute",
        units=1,
        limit_units=1,
        window_seconds=60,
        now=now,
    )
    second = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability=ProviderCapability.LATEST_PRICE.value,
        dimension="requests_per_minute",
        units=1,
        limit_units=1,
        window_seconds=60,
        now=now,
    )

    assert first is not None and second is not None
    assert {row.quota_group for row in db.execute(select(ProviderQuotaWindow)).scalars()} == {
        ProviderCapability.PRICE_HISTORY.value,
        ProviderCapability.LATEST_PRICE.value,
    }


def test_marketdata_app_only_widens_daily_limit_for_exact_reviewed_plan_pair(monkeypatch):
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 0)
    conservative = provider_rate_limit_seed("marketdata_app")
    assert conservative["quota_contract"]["dimensions"][0]["limit"] == 100
    assert "account_plan" not in conservative["quota_contract"]["dimensions"][0]

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10000)
    reviewed = provider_rate_limit_seed("marketdata_app")
    dimension = reviewed["quota_contract"]["dimensions"][0]
    assert dimension["limit"] == 10000
    assert dimension["account_plan"] == "starter"
    assert dimension["account_limit_reviewed"] is True

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter_trial")
    # Trial plans are only admitted while an operator-reviewed, timezone-aware
    # entitlement expiry is present. The plan identifier alone must never
    # widen a daily pool after the provider's 30-day trial has elapsed.
    monkeypatch.setattr(
        settings,
        "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT",
        datetime(2030, 1, 1, tzinfo=UTC),
    )
    trial = provider_rate_limit_seed("marketdata_app")
    trial_dimension = trial["quota_contract"]["dimensions"][0]
    assert trial_dimension["limit"] == 10000
    assert trial_dimension["account_plan"] == "starter_trial"
    assert trial_dimension["account_limit_reviewed"] is True
    assert trial_dimension["account_plan_expires_at"] == "2030-01-01T00:00:00+00:00"

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "trader_trial")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 100000)
    trader_trial = provider_rate_limit_seed("marketdata_app")
    trader_trial_dimension = trader_trial["quota_contract"]["dimensions"][0]
    assert trader_trial_dimension["limit"] == 100000
    assert trader_trial_dimension["account_plan"] == "trader_trial"
    assert trader_trial_dimension["account_limit_reviewed"] is True

    monkeypatch.setattr(
        settings,
        "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT",
        datetime(2020, 1, 1, tzinfo=UTC),
    )
    expired_trial = provider_rate_limit_seed("marketdata_app")
    assert expired_trial["quota_contract"]["dimensions"][0]["limit"] == 100
    assert expired_trial["quota_contract"]["dimensions"][0]["account_plan"] == "free_forever"
    assert expired_trial["quota_contract"]["dimensions"][0]["account_limit_reviewed"] is True
    assert "account_plan_expires_at" not in expired_trial["quota_contract"]["dimensions"][0]

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", None)
    missing_expiry_trial = provider_rate_limit_seed("marketdata_app")
    assert missing_expiry_trial["quota_contract"]["dimensions"][0]["limit"] == 100
    assert "account_plan" not in missing_expiry_trial["quota_contract"]["dimensions"][0]

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 100)
    mismatched = provider_rate_limit_seed("marketdata_app")
    assert mismatched["quota_contract"]["dimensions"][0]["limit"] == 100
    assert "account_plan" not in mismatched["quota_contract"]["dimensions"][0]

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "quant")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 100000)
    unsupported = provider_rate_limit_seed("marketdata_app")
    assert unsupported["quota_contract"]["dimensions"][0]["limit"] == 100


def test_marketdata_starter_trial_uses_approved_lisbon_expiry_boundary(monkeypatch):
    expires_at = datetime.fromisoformat("2026-10-11T18:09:00+01:00")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter_trial")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10_000)
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", expires_at)

    monkeypatch.setattr(
        app_config,
        "_marketdata_app_policy_now_utc",
        lambda: expires_at.astimezone(UTC) - timedelta(seconds=1),
    )
    active = provider_rate_limit_seed("marketdata_app")["quota_contract"]["dimensions"][0]
    assert active["limit"] == 10_000
    assert active["account_plan"] == "starter_trial"

    monkeypatch.setattr(
        app_config, "_marketdata_app_policy_now_utc", lambda: expires_at.astimezone(UTC)
    )
    expired = provider_rate_limit_seed("marketdata_app")["quota_contract"]["dimensions"][0]
    assert expired["limit"] == 100
    assert expired["account_plan"] == "free_forever"

    monkeypatch.setattr(
        app_config,
        "_marketdata_app_policy_now_utc",
        lambda: expires_at.astimezone(UTC) + timedelta(seconds=1),
    )
    after = provider_rate_limit_seed("marketdata_app")["quota_contract"]["dimensions"][0]
    assert after["limit"] == 100
    assert after["account_plan"] == "free_forever"


def test_blank_marketdata_trial_expiry_is_unset_for_environment_boot(monkeypatch):
    monkeypatch.delenv("MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", raising=False)
    parsed = Settings(
        _env_file=None,
        MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT="",
    )
    assert parsed.MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT is None


def test_json_seed_code_default_sentinel_preserves_code_defaults_and_empty_is_explicit():
    parsed = Settings(
        _env_file=None,
        PROVIDER_RATE_LIMIT_SEEDS="__CODE_DEFAULT__",
        PROVIDER_FRESHNESS_SEEDS="__CODE_DEFAULT__",
        PROVIDER_USAGE_PROFILE_SEEDS="__CODE_DEFAULT__",
    )
    assert "alpaca" in parsed.PROVIDER_RATE_LIMIT_SEEDS
    assert "massive" in parsed.PROVIDER_USAGE_PROFILE_SEEDS

    explicitly_empty = Settings(
        _env_file=None,
        PROVIDER_RATE_LIMIT_SEEDS="{}",
        PROVIDER_FRESHNESS_SEEDS="{}",
        PROVIDER_USAGE_PROFILE_SEEDS="{}",
    )
    assert explicitly_empty.PROVIDER_RATE_LIMIT_SEEDS == {}
    assert explicitly_empty.PROVIDER_FRESHNESS_SEEDS == {}
    assert explicitly_empty.PROVIDER_USAGE_PROFILE_SEEDS == {}


def test_json_seed_environment_sentinel_bypasses_eager_settings_decode(monkeypatch):
    monkeypatch.setenv("PROVIDER_RATE_LIMIT_SEEDS", "__CODE_DEFAULT__")
    monkeypatch.setenv("PROVIDER_FRESHNESS_SEEDS", "__CODE_DEFAULT__")
    monkeypatch.setenv("PROVIDER_USAGE_PROFILE_SEEDS", "__CODE_DEFAULT__")

    parsed = Settings(_env_file=None)

    assert "alpaca" in parsed.PROVIDER_RATE_LIMIT_SEEDS
    assert parsed.PROVIDER_FRESHNESS_SEEDS == {}
    assert "massive" in parsed.PROVIDER_USAGE_PROFILE_SEEDS

    monkeypatch.setenv("PROVIDER_RATE_LIMIT_SEEDS", "{}")
    explicit_empty = Settings(_env_file=None)
    assert explicit_empty.PROVIDER_RATE_LIMIT_SEEDS == {}


def test_blank_explicit_quota_group_fails_closed():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 1,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "quota_group": "   ",
                    "source": "https://provider.example/rate-limits",
                }
            ],
        },
    )

    assert quota_dimensions(policy) == []


def test_marketdata_app_option_chain_cost_requires_explicit_symbol_bound(monkeypatch):
    monkeypatch.setattr(settings, "MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", 0)
    assert (
        "fetch_option_chain" not in get_provider_usage_profile("marketdata_app")["operation_costs"]
    )

    monkeypatch.setattr(settings, "MARKETDATA_APP_OPTION_CHAIN_MAX_SYMBOLS", 12)
    profile = get_provider_usage_profile("marketdata_app")
    assert profile["operation_costs"]["fetch_option_chain"] == 12


def test_marketdata_app_headers_settle_actual_credit_charge_and_cumulative_total():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.OPTION_CHAIN,
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
    measurement = SimpleNamespace(
        response_headers={
            "x-api-ratelimit-limit": "100",
            "x-api-ratelimit-remaining": "87",
            "x-api-ratelimit-consumed": "4",
        }
    )
    from app.services.provider_runtime import _consumed_dimension_costs

    assert _consumed_dimension_costs(policy, measurement, {"credits_per_day": 12}) == {
        "credits_per_day": 4
    }
    assert _observed_dimension_totals(policy, measurement) == {"credits_per_day": 13}

    mismatched = SimpleNamespace(
        response_headers={
            "x-api-ratelimit-limit": "10",
            "x-api-ratelimit-remaining": "8",
            "x-api-ratelimit-consumed": "2",
        }
    )
    assert _observed_dimension_totals(policy, mismatched) == {}


def test_alpaca_market_data_headers_reconcile_only_matching_request_window():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "reset": "provider_defined",
            "dimensions": [
                {
                    "name": "historical_api_calls",
                    "limit": 200,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "account",
                    "source": "https://docs.alpaca.markets/us/v1.1/docs/about-market-data-api",
                }
            ],
        },
    )
    measurement = SimpleNamespace(
        response_headers={
            "x-ratelimit-limit": "200",
            "x-ratelimit-remaining": "199",
            "x-ratelimit-reset": "1789238854",
        }
    )
    assert _observed_dimension_totals(policy, measurement) == {"historical_api_calls": 1}

    mismatched = SimpleNamespace(
        response_headers={
            "x-ratelimit-limit": "100",
            "x-ratelimit-remaining": "99",
            "x-ratelimit-reset": "1789238854",
        }
    )
    assert _observed_dimension_totals(policy, mismatched) == {}

    missing_reset = SimpleNamespace(
        response_headers={
            "x-ratelimit-limit": "200",
            "x-ratelimit-remaining": "199",
        }
    )
    assert _observed_dimension_totals(policy, missing_reset) == {}

    malformed_reset = SimpleNamespace(
        response_headers={
            "x-ratelimit-limit": "200",
            "x-ratelimit-remaining": "199",
            "x-ratelimit-reset": "not-an-epoch",
        }
    )
    assert _observed_dimension_totals(policy, malformed_reset) == {}

    nonpositive_reset = SimpleNamespace(
        response_headers={
            "x-ratelimit-limit": "200",
            "x-ratelimit-remaining": "199",
            "x-ratelimit-reset": "0",
        }
    )
    assert _observed_dimension_totals(policy, nonpositive_reset) == {}


def test_xstocks_native_headers_reconcile_only_matching_shared_public_window():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.TOKENIZED_ASSETS,
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "public_requests_per_minute",
                    "limit": 1000,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "public_api",
                    "quota_group": "public_api",
                    "source": "https://docs.xstocks.fi/apis/openapi",
                }
            ],
        },
    )
    assert _observed_dimension_totals(
        policy,
        SimpleNamespace(
            response_headers={
                "x-ratelimit-limit": "1000",
                "x-ratelimit-remaining": "993",
                "x-ratelimit-reset": "1789238854",
            }
        ),
    ) == {"public_requests_per_minute": 7}
    assert (
        _observed_dimension_totals(
            policy,
            SimpleNamespace(
                response_headers={
                    "x-ratelimit-limit": "100",
                    "x-ratelimit-remaining": "93",
                }
            ),
        )
        == {}
    )


def test_non_applicable_dimension_is_not_charged_during_runtime_settlement():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.SHORT_INTEREST,
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
                    "name": "async_download_bytes",
                    "limit": 1000,
                    "window_seconds": 60,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "unit-test contract",
                },
            ],
        },
    )
    from app.services.provider_runtime import _consumed_dimension_costs

    measurement = SimpleNamespace(http_requests=1, response_bytes=123)
    assert _consumed_dimension_costs(
        policy,
        measurement,
        {"requests_per_minute": 1, "async_download_bytes": 0},
    ) == {"requests_per_minute": 1, "async_download_bytes": 0}


@pytest.mark.asyncio
async def test_in_flight_concurrency_dimension_is_released_not_consumed(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="concurrency-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "concurrent_requests",
                    "limit": 2,
                    "window_seconds": 1,
                    "unit": "concurrent_requests",
                    "scope": "api_key",
                    "source": "https://provider.example/rate-limits",
                    "reset": "rolling",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="concurrency-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    now = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=5,
        now=now,
    )
    second = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=7,
        now=now,
    )
    exhausted = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=2,
        now=now,
    )
    assert first is not None and second is not None and exhausted is None

    settle_provider_contract(
        first,
        units=1,
        success=True,
        reserved_dimension_units={"concurrent_requests": 1},
        consumed_dimension_units={"concurrent_requests": 1},
        release_only_dimensions={"concurrent_requests"},
    )
    released = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=now,
    )
    assert released is not None
    window = db.execute(select(ProviderQuotaWindow)).scalars().one()
    assert window.consumed_units == 0
    assert window.reserved_units == 2


@pytest.mark.asyncio
async def test_failed_contract_rolls_back_one_in_flight_slot(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="rollback-concurrency-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "concurrent_requests",
                    "limit": 2,
                    "window_seconds": 1,
                    "unit": "concurrent_requests",
                    "scope": "api_key",
                    "source": "https://provider.example/rate-limits",
                    "reset": "rolling",
                },
                {
                    "name": "requests_per_minute",
                    "limit": 1,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "https://provider.example/rate-limits",
                    "reset": "rolling",
                },
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="rollback-concurrency-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )

    result = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=9,
        dimension_units={"concurrent_requests": 9, "requests_per_minute": 2},
        now=datetime(2026, 9, 9, 12, 0, tzinfo=UTC),
    )

    assert result is None
    db.flush()
    windows = db.execute(select(ProviderQuotaWindow)).scalars().all()
    assert {
        window.dimension: (window.reserved_units, window.consumed_units) for window in windows
    } == {
        "concurrent_requests": (0, 0),
        "requests_per_minute": (0, 0),
    }


def test_provider_reset_metadata_preserves_documented_calendar_boundaries():
    tiingo = settings.PROVIDER_RATE_LIMIT_SEEDS["tiingo"]["quota_contract"]
    assert [item["reset"] for item in tiingo["dimensions"]] == [
        "provider_defined",
        "provider_defined",
        "calendar_day_est",
    ]
    assert tiingo["untracked_constraints"][0]["reset"] == "calendar_month_est"
    assert {
        "unique_symbols_reset_anchor",
        "requests_per_hour_reset_boundary_model",
    } == set(tiingo["unknown_dimensions"])

    coingecko = settings.PROVIDER_RATE_LIMIT_SEEDS["coingecko"]["quota_contract"]
    assert [item["reset"] for item in coingecko["dimensions"]] == [
        "rolling",
        "calendar_month_utc",
    ]
    assert "unknown_dimensions" not in coingecko

    twelve = settings.PROVIDER_RATE_LIMIT_SEEDS["twelve_data"]["quota_contract"]
    assert [item["reset"] for item in twelve["dimensions"]] == [
        "fixed_minute",
        "calendar_day_utc",
        "rolling",
    ]
    assert twelve["account_usage_bootstrap"]["reconciled_dimensions"] == [
        "credits_per_minute"
    ]

    eodhd = settings.PROVIDER_RATE_LIMIT_SEEDS["eodhd"]["quota_contract"]
    assert [item["reset"] for item in eodhd["dimensions"]] == [
        "provider_defined",
        "calendar_day_gmt",
        "rolling",
    ]
    assert [item["limit"] for item in eodhd["dimensions"]] == [20, 20, 1]
    assert [item["unit"] for item in eodhd["dimensions"]] == [
        "requests",
        "calls",
        "concurrent_requests",
    ]
    assert eodhd["dimensions"][0]["source"] == "https://eodhd.com/lp/historical-eod-api"
    assert eodhd["dimensions"][1]["source"] == "https://eodhd.com/lp/historical-eod-api"
    assert (
        eodhd["dimensions"][0]["limit_basis"]
        == "conservative seed pending account-specific review"
    )
    assert eodhd["unknown_dimensions"] == [
        "published_minute_limit_conflict",
        "requests_per_minute_reset_boundary",
    ]
    assert eodhd["account_usage_bootstrap"]["allowed_unknown_dimensions"] == [
        "published_minute_limit_conflict",
        "requests_per_minute_reset_boundary",
    ]
    assert eodhd["account_usage_bootstrap"]["reconciled_dimensions"] == [
        "calls_per_day"
    ]
    assert eodhd["source_conflicts"] == [
        {
            "source": "https://eodhd.com/financial-apis/api-limits",
            "claim": "1,000 requests per minute on every plan",
            "conflicts_with": "https://eodhd.com/lp/historical-eod-api",
        }
    ]
    assert (
        eodhd["dimensions"][1]["reset_source"]
        == "https://eodhd.com/financial-apis/api-limits"
    )
    assert settings.PROVIDER_RATE_LIMIT_SEEDS["eodhd"]["tokens_per_minute"] == 20
    assert eodhd["operation_costs_required"] is True
    assert (
        settings.PROVIDER_USAGE_PROFILE_SEEDS["eodhd"]["operation_costs"]["get_instrument_profile"]
        == 10
    )
    eodhd_costs = settings.PROVIDER_USAGE_PROFILE_SEEDS["eodhd"]["dimension_costs"]
    assert eodhd_costs["requests_per_minute"]["get_instrument_profile"] == 1
    assert eodhd_costs["calls_per_day"]["get_instrument_profile"] == 10
    assert (
        settings.PROVIDER_USAGE_PROFILE_SEEDS["eodhd"]["operation_costs"][
            "fetch_account_usage"
        ]
        == 1
    )
    assert eodhd_costs["requests_per_minute"]["fetch_account_usage"] == 1
    assert eodhd_costs["calls_per_day"]["fetch_account_usage"] == 1

    eodhd_entitlement = settings.PROVIDER_ENTITLEMENT_SEEDS["eodhd"]
    assert eodhd_entitlement["configured_plan"] == "free-20-day"
    assert eodhd_entitlement["capabilities"]["instrument_metadata"] == {
        "configured_plan": "unreviewed",
        "is_free": False,
        "usage_terms": (
            "EODHD Free Starter does not include Fundamentals/profile access; "
            "configure an operator-reviewed plan with this endpoint entitlement "
            "before routing."
        ),
        "live_probe_status": "not_run",
    }

    gate = settings.PROVIDER_RATE_LIMIT_SEEDS["gate_tradfi"]["quota_contract"]
    assert gate.get("untracked_constraints", []) == []
    assert gate["dimensions"] == [
        {
            "name": "stock_public_requests_per_second",
            "limit": 5,
            "window_seconds": 1,
            "unit": "requests",
            "scope": "ip",
            "quota_group": "ip",
            "source": "https://www.gate.com/docs/developers/apiv4/en/",
        }
    ]


def test_tokenized_quote_usage_profiles_charge_asset_and_quote_requests():
    for provider_name in (
        "xstocks",
        "robinhood_tokens",
        "bybit_xstocks",
        "gate_tradfi",
        "kraken_xstocks",
        "dinari",
        "ondo_global_markets",
    ):
        profile = get_provider_usage_profile(provider_name)
        assert profile["operation_costs"]["discover_tokenized_assets"] == 1
        assert profile["operation_costs"]["get_tokenized_asset"] == 1
        expected_price_cost = 4 if provider_name == "robinhood_tokens" else 2
        assert profile["operation_costs"]["get_tokenized_price"] == expected_price_cost
        if provider_name == "dinari":
            assert profile["operation_costs"]["get_tokenized_quote"] == 2


def test_tokenized_history_operations_charge_the_metadata_resolution_and_data_read():
    assert settings.PROVIDER_USAGE_PROFILE_SEEDS["dinari"]["operation_costs"] == {
        "discover_tokenized_assets": 1,
        "get_tokenized_asset": 1,
        "get_tokenized_price": 2,
        "get_tokenized_quote": 2,
        "fetch_tokenized_historical_prices": 2,
        "fetch_tokenized_news": 2,
        "fetch_tokenized_dividends": 2,
        "fetch_tokenized_splits": 2,
        "fetch_tokenized_corporate_actions": 3,
    }
    assert settings.PROVIDER_USAGE_PROFILE_SEEDS["ondo_global_markets"]["operation_costs"] == {
        "discover_tokenized_assets": 1,
        "get_tokenized_asset": 1,
        "get_tokenized_price": 2,
        "fetch_tokenized_market_data": 2,
        "fetch_tokenized_ohlc": 2,
        "fetch_tokenized_historical_prices": 2,
    }


def test_coingecko_profile_usage_profile_covers_id_resolution_and_metadata():
    profile = get_provider_usage_profile("coingecko")
    assert profile["operation_costs"] == {
        "search_instruments": 1,
        "discover_universe_page": 1,
        "get_instrument_profile": 2,
    }


def test_alpha_vantage_profile_covers_each_single_query_operation():
    profile = get_provider_usage_profile("alpha_vantage")
    assert profile["operation_costs"] == {
        "search_instruments": 1,
        "fetch_ohlcv": 1,
        "fetch_latest_ohlcv": 1,
        "get_current_price": 1,
        "bulk_fetch": 1,
        "fetch_rfr_ohlcv": 1,
        "discover_universe_page": 1,
        "fetch_market_events": 1,
        "fetch_earnings_calendar": 1,
        "fetch_instrument_events": 1,
    }


def test_optional_latest_price_profiles_charge_the_actual_quote_operation():
    for provider_name in ("tiingo", "eodhd", "fmp", "marketstack", "marketdata_app"):
        assert (
            get_provider_usage_profile(provider_name)["operation_costs"]["get_current_price"] == 1
        )


def test_fmp_profile_charges_market_event_calendar_operation():
    assert get_provider_usage_profile("fmp")["operation_costs"]["fetch_market_events"] == 1


def test_deep_history_profiles_charge_the_bulk_fetch_operation():
    for provider_name in (
        "alpha_vantage",
        "fred",
        "finnhub",
        "tradier",
        "tiingo",
        "eodhd",
        "fmp",
        "marketdata_app",
    ):
        profile = get_provider_usage_profile(provider_name)
        if provider_name == "marketdata_app":
            # MarketData.app bills stock candles by returned volume; bulk
            # callers must provide a date-granular 1-credit-per-1,000 estimate
            # instead of falling back to one request == one credit.
            assert "bulk_fetch" not in profile["operation_costs"]
        else:
            assert profile["operation_costs"]["bulk_fetch"] == 1


def test_single_request_provider_profiles_are_explicit():
    expected = {
        "alpaca": {
            "get_current_price": 1,
            "fetch_rfr_ohlcv": 1,
            "discover_universe_page": 1,
            "get_instrument_profile": 1,
            "fetch_account_usage": 1,
        },
        "massive": {
            "search_instruments": 1,
            "discover_universe_page": 1,
            "get_instrument_profile": 1,
            "fetch_instrument_events": 2,
            "fetch_market_events": 1,
            "fetch_market_holidays": 1,
        },
        "fred": {
            "fetch_ohlcv": 1,
            "fetch_latest_ohlcv": 1,
            "get_current_price": 1,
            "bulk_fetch": 1,
            "fetch_rfr_ohlcv": 1,
        },
        "openfigi": {
            "fetch_stable_identifiers": 1,
            "resolve_instrument_profile": 1,
            "fetch_account_usage": 1,
        },
        "coinbase": {"get_current_price": 1, "discover_universe_page": 1},
        "kraken": {"get_current_price": 1, "discover_universe_page": 1},
        "marketstack": {"discover_universe_page": 1, "get_current_price": 1},
        "tradier": {
            "fetch_ohlcv": 1,
            "fetch_latest_ohlcv": 1,
            "get_current_price": 1,
            "search_instruments": 1,
            "bulk_fetch": 1,
            "list_option_expirations": 1,
            "fetch_option_chain": 1,
        },
    }
    for provider_name, operation_costs in expected.items():
        assert get_provider_usage_profile(provider_name)["operation_costs"] == operation_costs


def test_twelve_data_cumulative_credit_headers_update_only_matching_minute_window():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "reset": "fixed_minute",
            "dimensions": [
                {
                    "name": "credits_per_minute",
                    "limit": 8,
                    "window_seconds": 60,
                    "unit": "credits",
                    "scope": "api_key",
                    "source": "https://support.twelvedata.com/en/articles/5713553-control-over-usage",
                }
            ],
        },
    )
    measurement = SimpleNamespace(
        response_headers={"Api-Credits-Used": "3", "api-credits-left": "5"}
    )
    assert _observed_dimension_totals(policy, measurement) == {"credits_per_minute": 3}

    mismatched = SimpleNamespace(
        response_headers={"api-credits-used": "3", "api-credits-left": "4"}
    )
    assert _observed_dimension_totals(policy, mismatched) == {}


def test_provider_native_tradier_and_binance_counters_require_contract_match():
    tradier_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "market_data_requests_per_minute",
                    "limit": 120,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "production_token",
                    "source": "https://docs.tradier.com/docs/rate-limiting",
                }
            ],
        },
    )
    assert _observed_dimension_totals(
        tradier_policy,
        SimpleNamespace(
            response_headers={
                "x-ratelimit-allowed": "120",
                "x-ratelimit-used": "17",
                "x-ratelimit-available": "103",
            }
        ),
    ) == {"market_data_requests_per_minute": 17}
    assert (
        _observed_dimension_totals(
            tradier_policy,
            SimpleNamespace(
                response_headers={
                    "x-ratelimit-allowed": "60",
                    "x-ratelimit-used": "17",
                    "x-ratelimit-available": "43",
                }
            ),
        )
        == {}
    )

    binance_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.LATEST_PRICE,
        quota_contract={
            "reset": "fixed_minute",
            "dimensions": [
                {
                    "name": "request_weight_per_minute",
                    "limit": 6000,
                    "window_seconds": 60,
                    "unit": "weight",
                    "scope": "ip",
                    "source": "https://developers.binance.com/en/docs/products/spot/rest-api",
                }
            ],
        },
    )
    assert _observed_dimension_totals(
        binance_policy,
        SimpleNamespace(response_headers={"x-mbx-used-weight-1m": "42"}),
    ) == {"request_weight_per_minute": 42}

    bybit_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.TOKENIZED_ASSETS,
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "http_requests_per_five_seconds",
                    "limit": 600,
                    "window_seconds": 5,
                    "unit": "requests",
                    "scope": "ip",
                    "source": "https://bybit-exchange.github.io/docs/v5/rate-limit",
                }
            ],
        },
    )
    assert (
        _observed_dimension_totals(
            bybit_policy,
            SimpleNamespace(
                response_headers={
                    "x-bapi-limit": "600",
                    "x-bapi-limit-status": "587",
                }
            ),
        )
        == {}
    )
    assert (
        _observed_dimension_totals(
            bybit_policy,
            SimpleNamespace(
                response_headers={
                    "x-bapi-limit": "100",
                    "x-bapi-limit-status": "87",
                }
            ),
        )
        == {}
    )

    gate_policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.TOKENIZED_ASSETS,
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": "stock_public_requests_per_second",
                    "limit": 5,
                    "window_seconds": 1,
                    "unit": "requests",
                    "scope": "ip",
                    "source": "https://www.gate.com/docs/developers/apiv4/en/stock/",
                }
            ],
        },
    )
    assert _observed_dimension_totals(
        gate_policy,
        SimpleNamespace(
            response_headers={
                "x-ratelimit-limit": "5",
                "x-ratelimit-remaining": "3",
            }
        ),
    ) == {"stock_public_requests_per_second": 2}
    assert (
        _observed_dimension_totals(
            gate_policy,
            SimpleNamespace(
                response_headers={
                    "x-ratelimit-limit": "10",
                    "x-ratelimit-remaining": "8",
                }
            ),
        )
        == {}
    )


@pytest.mark.asyncio
async def test_calendar_day_reservation_changes_at_utc_midnight(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="calendar-day-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "per_dimension",
            "dimensions": [
                {
                    "name": "credits_per_day",
                    "limit": 1,
                    "window_seconds": 86400,
                    "unit": "credits",
                    "scope": "api_key",
                    "source": "unit-test",
                    "reset": "calendar_day_utc",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="calendar-day-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 9, 5, 23, 59, tzinfo=UTC),
    )
    second = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 9, 6, 0, 1, tzinfo=UTC),
    )
    assert first is not None and second is not None
    assert first[0].window_started_at != second[0].window_started_at


@pytest.mark.asyncio
async def test_provider_defined_daily_reservation_fails_closed_without_boundary(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="provider-defined-daily", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "provider_defined_daily",
            "dimensions": [
                {
                    "name": "requests_per_day",
                    "limit": 1,
                    "window_seconds": 86400,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "operator-dashboard",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="provider-defined-daily",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    start = datetime(2026, 9, 5, 23, 59, tzinfo=UTC)
    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start,
    )
    before_expiry = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start + timedelta(seconds=86400 - 1),
    )
    after_expiry = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start + timedelta(seconds=86400 + 1),
    )
    assert first is None
    assert before_expiry is None
    assert after_expiry is None
    assert db.execute(select(ProviderQuotaWindow)).scalars().all() == []


@pytest.mark.asyncio
async def test_eastern_calendar_month_reservation_follows_tiingo_reset_boundary(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="eastern-month-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "provider_defined",
            "dimensions": [
                {
                    "name": "bandwidth_bytes_per_month",
                    "limit": 1000,
                    "window_seconds": 2_678_400,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "https://www.tiingo.com/about/pricing",
                    "reset": "calendar_month_est",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="eastern-month-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    before_reset = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 10, 1, 3, 30, tzinfo=UTC),
    )
    after_reset = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 10, 1, 4, 30, tzinfo=UTC),
    )
    assert before_reset is not None and after_reset is not None
    assert before_reset[0].window_started_at == datetime(2026, 9, 1, 4, tzinfo=UTC)
    assert after_reset[0].window_started_at == datetime(2026, 10, 1, 4, tzinfo=UTC)


@pytest.mark.asyncio
async def test_eastern_calendar_day_reservation_follows_tiingo_reset_boundary(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="eastern-day-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "provider_defined",
            "dimensions": [
                {
                    "name": "requests_per_day",
                    "limit": 1,
                    "window_seconds": 86400,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "https://www.tiingo.com/about/pricing",
                    "reset": "calendar_day_est",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="eastern-day-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    before_reset = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 9, 9, 3, 30, tzinfo=UTC),
    )
    after_reset = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=datetime(2026, 9, 9, 4, 30, tzinfo=UTC),
    )
    assert before_reset is not None and after_reset is not None
    assert before_reset[0].window_started_at == datetime(2026, 9, 8, 4, tzinfo=UTC)
    assert after_reset[0].window_started_at == datetime(2026, 9, 9, 4, tzinfo=UTC)


@pytest.mark.asyncio
async def test_rolling_thirty_day_reservation_expires_at_exact_fmp_boundary(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="rolling-thirty-day-provider", is_active=True)
    db.add(source)
    db.flush()
    policy = ProviderPolicy(
        data_source_id=source.id,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test provider contract",
        quota_contract={
            "reset": "provider_defined",
            "dimensions": [
                {
                    "name": "bandwidth_bytes_per_30_days",
                    "limit": 1,
                    "window_seconds": 2_592_000,
                    "unit": "bytes",
                    "scope": "api_key",
                    "source": "operator_account_dashboard_2026-09-07",
                    "reset": "rolling_30_days",
                }
            ],
        },
    )
    resolved = ResolvedProvider(
        provider_name="rolling-thirty-day-provider",
        provider=object(),
        data_source=source,
        policy=policy,
        health=None,  # type: ignore[arg-type]
    )
    start = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    first = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start,
    )
    still_active = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start + timedelta(seconds=2_592_000 - 1),
    )
    expired = await reserve_provider_contract(
        async_db,
        resolved=resolved,
        capability=ProviderCapability.PRICE_HISTORY.value,
        units=1,
        now=start + timedelta(seconds=2_592_000 + 1),
    )
    assert first is not None
    assert still_active is None
    assert expired is not None


def test_operator_plan_limits_are_recorded_without_ignoring_bandwidth_caps():
    finnhub = settings.PROVIDER_RATE_LIMIT_SEEDS["finnhub"]["quota_contract"]
    assert {item["limit"] for item in finnhub["dimensions"]} == {30, 60}
    assert finnhub["reset"] == "provider_defined_minute_and_rolling_second"

    finra = settings.PROVIDER_RATE_LIMIT_SEEDS["finra"]["quota_contract"]
    finra_otc = settings.PROVIDER_RATE_LIMIT_SEEDS["finra_otc_directory"]["quota_contract"]
    tiingo = settings.PROVIDER_RATE_LIMIT_SEEDS["tiingo"]["quota_contract"]
    fmp = settings.PROVIDER_RATE_LIMIT_SEEDS["fmp"]["quota_contract"]
    finra_bytes = next(item for item in finra["dimensions"] if item["unit"] == "bytes")
    assert finra_bytes["limit"] == 10_000_000_000
    assert finra_bytes["reset"] == "provider_defined"
    assert finra_bytes["safety_reset"] == "rolling_31_days"
    assert "download_bytes_month_reset_boundary" in finra["unknown_dimensions"]
    assert finra["reset"] == "provider_defined"
    assert finra["dimension_costs_required"] is True
    assert finra_otc["dimensions"] == []
    assert {
        "orf_product_entitlement_and_mfa",
        "file_download_quota_and_reset",
        "data_use_terms",
        "redistribution_rights",
    } <= set(finra_otc["unknown_dimensions"])
    assert tiingo["dimensions"][0]["name"] == "unique_symbols_per_month"
    assert tiingo["dimensions"][0]["limit"] == 500
    assert tiingo["dimensions"][0]["reset"] == "provider_defined"
    assert tiingo["unknown_dimensions"] == [
        "unique_symbols_reset_anchor",
        "requests_per_hour_reset_boundary_model",
    ]
    assert tiingo["dimensions"][2]["reset"] == "calendar_day_est"
    assert tiingo["untracked_constraints"][0]["reset"] == "calendar_month_est"
    assert tiingo["untracked_constraints"][0]["limit"] == 1_000_000_000
    assert fmp["dimensions"][0]["limit"] == 250
    assert fmp["dimensions"][0]["reset"] == "provider_defined"
    assert fmp["unknown_dimensions"] == ["calls_daily_reset_anchor"]
    assert fmp["untracked_constraints"][0]["limit"] == 500_000_000
    assert fmp["untracked_constraints"][0]["window_seconds"] == 2_592_000
    assert (
        fmp["untracked_constraints"][0]["source"]
        == "https://site.financialmodelingprep.com/developer/docs/pricing"
    )
    assert fmp["untracked_constraints"][0]["reset"] == "rolling_30_days"


def test_finnhub_reviewed_reset_boundaries_promote_each_dimension_only_with_evidence(
    monkeypatch,
):
    monkeypatch.setattr(settings, "FINNHUB_REVIEWED_MINUTE_RESET", "fixed_minute")
    monkeypatch.setattr(settings, "FINNHUB_REVIEWED_SECOND_RESET", "rolling")
    monkeypatch.setattr(settings, "FINNHUB_MINUTE_QUOTA_EVIDENCE", "minute review")
    monkeypatch.setattr(settings, "FINNHUB_SECOND_QUOTA_EVIDENCE", "second review")

    contract = provider_rate_limit_seed("finnhub")["quota_contract"]
    assert contract["reset"] == "per_dimension"
    assert contract["unknown_dimensions"] == []
    assert {
        dimension["name"]: dimension["reset"]
        for dimension in contract["dimensions"]
    } == {
        "calls_per_minute": "fixed_minute",
        "hard_calls_per_second": "rolling",
    }

    monkeypatch.setattr(settings, "FINNHUB_SECOND_QUOTA_EVIDENCE", "")
    contract = provider_rate_limit_seed("finnhub")["quota_contract"]
    assert contract["reset"] == "provider_defined_minute_and_rolling_second"
    assert all("reset" not in dimension for dimension in contract["dimensions"])


def test_finnhub_rate_windows_require_explicit_operation_costs_for_each_dimension():
    contract = settings.PROVIDER_RATE_LIMIT_SEEDS["finnhub"]["quota_contract"]
    profile = get_provider_usage_profile("finnhub")

    assert contract["dimension_costs_required"] is True
    assert set(profile["dimension_costs"]) == {
        "calls_per_minute",
        "hard_calls_per_second",
    }
    for operation, cost in profile["operation_costs"].items():
        assert profile["dimension_costs"]["calls_per_minute"][operation] == cost
        assert profile["dimension_costs"]["hard_calls_per_second"][operation] == cost

    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="Finnhub account dashboard plus API documentation",
        quota_contract=contract,
    )
    source = DataSource(name="finnhub", config={"usage_tracking": profile})
    assert provider_contract_operation_cost_known(policy, source, "fetch_ohlcv")
    assert _dimension_costs_for_operation(policy, source, "fetch_ohlcv", default_units=1) == {
        "calls_per_minute": 1,
        "hard_calls_per_second": 1,
    }

@pytest.mark.asyncio
async def test_existing_finnhub_data_source_receives_new_dimension_cost_maps(db):
    source = DataSource(
        name="finnhub",
        config={"usage_tracking": {"operation_costs": {"fetch_ohlcv": 1}}},
    )
    db.add(source)
    db.flush()

    await ensure_data_source(AsyncSessionAdapter(db), "finnhub")

    usage_tracking = source.config["usage_tracking"]
    assert set(usage_tracking["dimension_costs"]) == {
        "calls_per_minute",
        "hard_calls_per_second",
    }
    # An existing explicit operation override remains intact.
    assert usage_tracking["operation_costs"]["fetch_ohlcv"] == 1


def test_compound_directory_usage_is_not_undercharged_or_guessed():
    nasdaq_profile = get_provider_usage_profile("nasdaq")
    assert nasdaq_profile["operation_costs"]["discover_universe_page"] == 2
    assert nasdaq_profile["operation_costs"]["reconcile_universe_page"] == 2

    finra_seed = settings.PROVIDER_RATE_LIMIT_SEEDS["finra_otc_directory"]
    assert finra_seed["quota_contract"]["operation_costs_required"] is True
    finra_profile = get_provider_usage_profile("finra_otc_directory")
    assert finra_profile["operation_costs"] == {}
    source = DataSource(
        name="finra_otc_directory",
        config={"usage_tracking": finra_profile},
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.UNIVERSE_DISCOVERY,
        quota_contract=finra_seed["quota_contract"],
    )
    assert not provider_contract_operation_cost_known(
        policy,
        source,
        "discover_universe_page",
    )


def test_finra_otc_reviewed_operation_costs_are_explicitly_admitted(monkeypatch):
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_OPERATION_COSTS",
        {"discover_universe_page": 3, "reconcile_universe_page": 3},
    )
    profile = get_provider_usage_profile("finra_otc_directory")
    assert profile["operation_costs"] == {
        "discover_universe_page": 3,
        "reconcile_universe_page": 3,
    }
    source = DataSource(
        name="finra_otc_directory",
        config={"usage_tracking": profile},
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.UNIVERSE_DISCOVERY,
        quota_contract=settings.PROVIDER_RATE_LIMIT_SEEDS["finra_otc_directory"]["quota_contract"],
    )
    assert provider_contract_operation_cost_known(policy, source, "discover_universe_page:OTC:0")
    assert provider_contract_operation_cost_known(policy, source, "reconcile_universe_page:OTC:0")
    assert provider_contract_operation_costs_configured(policy, source)


def test_coinbase_public_token_bucket_matches_documented_burst():
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["coinbase"]
    assert seed["tokens_per_minute"] == 600
    assert seed["burst_capacity"] == 15
    dimension = seed["quota_contract"]["dimensions"][0]
    assert dimension["limit"] == 10
    assert dimension["window_seconds"] == 1
    assert dimension["scope"] == "ip"


def test_finra_synchronous_budget_uses_documented_byte_reservation():
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["finra"]
    contract = seed["quota_contract"]
    bytes_dimension = next(item for item in contract["dimensions"] if item["unit"] == "bytes")
    assert bytes_dimension["limit"] == 10_000_000_000
    assert contract["maximum_synchronous_response_bytes"] == 3_000_000
    source = DataSource(
        name="finra",
        config={"usage_tracking": settings.PROVIDER_USAGE_PROFILE_SEEDS["finra"]},
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.SHORT_INTEREST,
        quota_scope=seed["quota_scope"],
        quota_source=seed["quota_source"],
        quota_contract=contract,
    )
    assert policy_has_known_quota(policy)
    assert quota_contract_missing_dimensions(policy) == []
    assert provider_contract_operation_cost_known(policy, source, "fetch_short_interest")


@pytest.mark.asyncio
async def test_seeded_finra_policy_contains_dimension_cost_profile(db):
    async_db = AsyncSessionAdapter(db)
    await seed_provider_runtime(async_db)
    source = db.execute(select(DataSource).where(DataSource.name == "finra")).scalar_one()
    policy = db.execute(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == source.id,
            ProviderPolicy.capability == ProviderCapability.SHORT_INTEREST,
        )
    ).scalar_one()
    assert policy_has_known_quota(policy)
    assert quota_contract_missing_dimensions(policy) == []
    assert provider_contract_operation_cost_known(policy, source, "fetch_short_interest")
    assert (
        source.config["usage_tracking"]["dimension_costs"]["download_bytes_per_calendar_month"][
            "fetch_short_interest"
        ]
        == 3_000_000
    )


def test_credit_contract_requires_the_requested_operation_cost():
    source = DataSource(
        name="marketdata_app",
        config={"usage_tracking": {"operation_costs": {"fetch_ohlcv": 1}}},
    )
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "credits",
                    "limit": 100,
                    "window_seconds": 86400,
                    "unit": "credits",
                    "scope": "api_key",
                    "source": "unit-test",
                }
            ],
            "reset": "provider_defined",
            "operation_costs_required": True,
        },
    )
    assert not provider_contract_operation_cost_known(policy, source)
    assert provider_contract_operation_cost_known(policy, source, "fetch_ohlcv")
    assert not provider_contract_operation_cost_known(policy, source, "get_current_price")


def test_partial_contract_is_non_routable_instead_of_dropping_a_dimension():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "known",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test",
                },
                {"name": "missing-source", "limit": 10, "window_seconds": 86400},
            ],
            "reset": "provider_defined",
        },
    )
    assert not policy_has_known_quota(policy)
    assert "quota_contract.dimensions[1].source" in quota_contract_missing_dimensions(policy)


@pytest.mark.parametrize("invalid_value", [True, False, 1.5, "10"])
def test_quota_dimension_limits_and_windows_reject_non_strict_positive_integers(invalid_value):
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="api_key",
        quota_source="unit-test",
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": invalid_value,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test",
                }
            ],
            "reset": "rolling",
        },
    )
    assert not policy_has_known_quota(policy)
    assert "quota_contract.dimensions[0].limit" in quota_contract_missing_dimensions(policy)

    policy.quota_contract["dimensions"][0]["limit"] = 10
    policy.quota_contract["dimensions"][0]["window_seconds"] = invalid_value
    assert not policy_has_known_quota(policy)
    assert "quota_contract.dimensions[0].window_seconds" in quota_contract_missing_dimensions(
        policy
    )


def test_missing_quota_contract_is_operator_actionable():
    policy = ProviderPolicy(data_source_id=1, capability=ProviderCapability.PRICE_HISTORY)
    assert quota_contract_missing_dimensions(policy) == [
        "quota_contract",
        "quota_scope",
        "quota_source",
    ]


def test_complete_dimension_contract_without_policy_provenance_is_non_routable():
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "requests_per_minute",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "api_key",
                    "source": "unit-test provider contract",
                }
            ],
            "reset": "rolling",
        },
    )
    assert quota_contract_missing_dimensions(policy) == ["quota_scope", "quota_source"]
    assert not policy_has_known_quota(policy)


def test_dynamic_operation_cost_readiness_is_exposed_separately():
    source = DataSource(name="binance", config={"usage_tracking": {"operation_costs": {}}})
    policy = ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.CRYPTO_HISTORY,
        quota_contract={
            "dimensions": [
                {
                    "name": "weight",
                    "limit": 10,
                    "window_seconds": 60,
                    "unit": "weight",
                    "scope": "ip",
                    "source": "unit-test",
                }
            ],
            "reset": "fixed_minute",
            "dynamic_endpoint_weights": True,
        },
    )
    assert not provider_contract_operation_costs_configured(policy, source)
