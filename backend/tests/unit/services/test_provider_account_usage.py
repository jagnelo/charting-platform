from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.config import settings
from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderAccountUsageObservation
from app.providers.base import ProviderAccountUsage, ProviderAccountUsageDimension
from app.services import provider_account_usage
from tests.unit.conftest import AsyncSessionAdapter


def test_binance_native_weight_snapshot_is_an_exact_baseline_candidate():
    observed_at = datetime.now(UTC).replace(microsecond=0)
    execution = SimpleNamespace(
        provider_name="binance",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "request_weight_per_minute",
                        "limit": 6000,
                        "window_seconds": 60,
                        "unit": "weight",
                        "scope": "ip",
                        "quota_group": "ip",
                        "reset": "fixed_minute",
                    }
                ],
                "reset": "per_dimension",
            }
        ),
    )
    candidate = provider_account_usage._native_baseline_candidate(
        execution,
        ProviderAccountUsageDimension(
            name="request_weight_per_minute",
            unit="weight",
            limit=6000,
            remaining=5942,
            consumed=58,
            reset_at=observed_at.replace(second=0) + timedelta(minutes=1),
        ),
        observed_at,
    )
    assert candidate is not None
    assert candidate[:3] == (
        "request_weight_per_minute",
        "account_usage",
        58,
    )


@pytest.mark.parametrize(
    ("remaining", "expected_used"),
    [(10_000, 0), (9_985, 15)],
)
def test_marketdata_app_native_trial_counter_seeds_only_reviewed_free_cap(remaining, expected_used):
    observed_at = datetime.now(UTC)
    execution = SimpleNamespace(
        provider_name="marketdata_app",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "credits_per_day",
                        "limit": 100,
                        "window_seconds": 86_400,
                        "unit": "credits",
                        "scope": "api_key",
                        "quota_group": "account",
                        "reset": "09:30 America/New_York",
                    }
                ],
                "reset": "per_dimension",
            }
        ),
    )
    candidate = provider_account_usage._native_baseline_candidate(
        execution,
        ProviderAccountUsageDimension(
            name="credits_per_day",
            unit="credits",
            limit=10_000,
            remaining=remaining,
            consumed=None,
            reset_at=observed_at + timedelta(hours=2),
        ),
        observed_at,
    )
    assert candidate is not None
    assert candidate[:3] == ("credits_per_day", "account_usage", expected_used)


def test_marketdata_app_native_usage_above_reviewed_daily_cap_is_not_admitted():
    observed_at = datetime.now(UTC)
    execution = SimpleNamespace(
        provider_name="marketdata_app",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "credits_per_day",
                        "limit": 100,
                        "window_seconds": 86_400,
                        "unit": "credits",
                        "scope": "api_key",
                        "quota_group": "account",
                    }
                ],
                "reset": "per_dimension",
            }
        ),
    )
    over_cap = ProviderAccountUsageDimension(
        name="credits_per_day",
        unit="credits",
        limit=10_000,
        remaining=9_899,
        consumed=101,
        reset_at=observed_at + timedelta(hours=2),
    )
    assert (
        provider_account_usage._native_baseline_candidate(execution, over_cap, observed_at) is None
    )


def test_xstocks_native_public_minute_headers_seed_only_the_reviewed_pool():
    observed_at = datetime.now(UTC)
    execution = SimpleNamespace(
        provider_name="xstocks",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "public_requests_per_minute",
                        "limit": 1000,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "public_api",
                        "quota_group": "public_api",
                        "reset": "rolling",
                    }
                ],
                "reset": "rolling",
            }
        ),
    )
    native_snapshot = ProviderAccountUsageDimension(
        name="public_requests_per_minute",
        unit="requests",
        limit=1000,
        remaining=876,
        consumed=124,
        reset_at=observed_at + timedelta(seconds=45),
    )

    candidate = provider_account_usage._native_baseline_candidate(
        execution, native_snapshot, observed_at
    )
    assert candidate is not None
    assert candidate[:3] == ("public_requests_per_minute", "account_usage", 124)


def test_coingecko_native_monthly_credit_snapshot_is_an_exact_baseline_candidate():
    observed_at = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    reset_at = datetime(2026, 11, 1, 0, 0, tzinfo=UTC)
    execution = SimpleNamespace(
        provider_name="coingecko",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "calls_per_month",
                        "limit": 10000,
                        "window_seconds": 2678400,
                        "unit": "credits",
                        "scope": "demo_api_key",
                        "quota_group": "demo_api_key",
                        "reset": "calendar_month_utc",
                    }
                ],
                "reset": "per_dimension",
            }
        ),
    )
    candidate = provider_account_usage._native_baseline_candidate(
        execution,
        ProviderAccountUsageDimension(
            name="calls_per_month",
            unit="credits",
            limit=10000,
            remaining=9679,
            consumed=321,
            reset_at=reset_at,
        ),
        observed_at,
    )
    assert candidate is not None
    assert candidate[:3] == ("calls_per_month", "account_usage", 321)
    # The coordinator anchors the reserved baseline at observation time;
    # `reset_at` validated the provider's current window but remains evidence
    # in the persisted observation, not the baseline start time.
    assert candidate[3] == observed_at


def test_fmp_native_daily_calls_reconcile_exact_plan_usage():
    observed_at = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    execution = SimpleNamespace(
        provider_name="fmp",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "calls_per_day",
                        "limit": 250,
                        "window_seconds": 86400,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "reset": "provider_defined",
                        "safety_reset": "rolling",
                    }
                ],
                "reset": "provider_defined",
            }
        ),
    )
    candidate = provider_account_usage._native_baseline_candidate(
        execution,
        ProviderAccountUsageDimension(
            name="calls_per_day",
            unit="requests",
            limit=250,
            remaining=243,
            consumed=7,
            reset_at=observed_at + timedelta(days=1),
        ),
        observed_at,
    )
    assert candidate is not None
    assert candidate[:3] == ("calls_per_day", "account_usage", 7)


def test_fmp_native_bandwidth_cap_never_widens_local_quota():
    observed_at = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
    execution = SimpleNamespace(
        provider_name="fmp",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "bandwidth_bytes_per_30_days",
                        "limit": 500_000_000,
                        "window_seconds": 2_592_000,
                        "unit": "bytes",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "reset": "rolling_30_days",
                    }
                ],
                "reset": "per_dimension",
            }
        ),
    )
    native_limit = 512 * 1_048_576
    observed_dimension = ProviderAccountUsageDimension(
        name="bandwidth_bytes_per_30_days",
        unit="bytes",
        limit=native_limit,
        remaining=native_limit - 125_000_000,
        consumed=125_000_000,
        reset_at=observed_at + timedelta(days=30),
    )
    candidate = provider_account_usage._native_baseline_candidate(
        execution, observed_dimension, observed_at
    )
    assert candidate is not None
    assert candidate[:3] == (
        "bandwidth_bytes_per_30_days",
        "account_usage",
        125_000_000,
    )
    over_cap_dimension = ProviderAccountUsageDimension(
        name="bandwidth_bytes_per_30_days",
        unit="bytes",
        limit=native_limit,
        remaining=0,
        consumed=500_000_001,
        reset_at=observed_at + timedelta(days=30),
    )
    assert (
        provider_account_usage._native_baseline_candidate(
            execution, over_cap_dimension, observed_at
        )
        is None
    )


def test_eodhd_native_minute_headers_reconcile_only_within_the_configured_local_cap():
    observed_at = datetime(2026, 9, 25, 3, 30, 29, tzinfo=UTC)
    execution = SimpleNamespace(
        provider_name="eodhd",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "requests_per_minute",
                        "limit": 1000,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "reset": "rolling",
                    }
                ],
                "reset": "per_dimension",
            }
        ),
    )
    candidate = provider_account_usage._native_baseline_candidate(
        execution,
        ProviderAccountUsageDimension(
            name="requests_per_minute",
            unit="requests",
            limit=1200,
            remaining=1199,
            consumed=1,
            reset_at=observed_at + timedelta(seconds=60),
        ),
        observed_at,
    )
    assert candidate is not None
    assert candidate[:3] == ("requests_per_minute", "account_usage", 1)

    over_local_cap = provider_account_usage._native_baseline_candidate(
        execution,
        ProviderAccountUsageDimension(
            name="requests_per_minute",
            unit="requests",
            limit=1200,
            remaining=199,
            consumed=1001,
            reset_at=observed_at + timedelta(seconds=60),
        ),
        observed_at,
    )
    assert over_local_cap is None


def test_marketstack_native_monthly_header_never_widens_reviewed_cap():
    observed_at = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    execution = SimpleNamespace(
        provider_name="marketstack",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "requests_per_month",
                        "limit": 100,
                        "window_seconds": 2_592_000,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "reset": "provider_defined",
                        "safety_reset": "rolling_30_days",
                        "safety_resolves_unknown_dimensions": ["monthly_cap_reset_boundary"],
                    }
                ],
                "reset": "per_dimension",
                "unknown_dimensions": ["monthly_cap_reset_boundary"],
            }
        ),
    )
    native_snapshot = ProviderAccountUsageDimension(
        name="requests_per_month",
        unit="requests",
        limit=1000,
        remaining=970,
        consumed=30,
        reset_at=observed_at + timedelta(days=30),
    )
    candidate = provider_account_usage._native_baseline_candidate(
        execution, native_snapshot, observed_at
    )
    assert candidate is not None
    assert candidate[:3] == ("requests_per_month", "account_usage", 30)

    over_cap = ProviderAccountUsageDimension(
        name="requests_per_month",
        unit="requests",
        limit=1000,
        remaining=899,
        consumed=101,
        reset_at=observed_at + timedelta(days=30),
    )
    assert (
        provider_account_usage._native_baseline_candidate(execution, over_cap, observed_at) is None
    )


def test_alpaca_native_snapshot_accepts_documented_second_precision_skew():
    observed_at = datetime(2026, 9, 25, 3, 30, 29, 900_000, tzinfo=UTC)
    execution = SimpleNamespace(
        provider_name="alpaca",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "market_data_requests_per_minute",
                        "limit": 200,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "account",
                        "quota_group": "account",
                        "native_reset_skew_seconds": 2,
                    }
                ],
                "reset": "rolling",
            }
        ),
    )
    candidate = provider_account_usage._native_baseline_candidate(
        execution,
        ProviderAccountUsageDimension(
            name="market_data_requests_per_minute",
            unit="requests",
            limit=200,
            remaining=199,
            consumed=1,
            reset_at=datetime(2026, 9, 25, 3, 30, 29, tzinfo=UTC),
        ),
        observed_at,
    )
    assert candidate is not None
    assert candidate[:3] == ("market_data_requests_per_minute", "account_usage", 1)


@pytest.mark.parametrize(
    ("native_limit", "remaining"),
    [(999, 998), (1200, 199)],
)
def test_eodhd_native_minute_snapshot_stays_blocked_when_below_or_over_local_cap(
    native_limit, remaining
):
    observed_at = datetime(2026, 9, 25, 3, 30, 29, tzinfo=UTC)
    execution = SimpleNamespace(
        provider_name="eodhd",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "requests_per_minute",
                        "limit": 1000,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "api_key",
                        "quota_group": "api_key",
                        "reset": "rolling",
                    }
                ],
                "reset": "per_dimension",
            }
        ),
    )
    candidate = provider_account_usage._native_baseline_candidate(
        execution,
        ProviderAccountUsageDimension(
            name="requests_per_minute",
            unit="requests",
            limit=native_limit,
            remaining=remaining,
            reset_at=observed_at + timedelta(seconds=60),
        ),
        observed_at,
    )
    assert candidate is None


def test_alpaca_native_snapshot_rejects_reset_stale_beyond_reviewed_skew():
    observed_at = datetime(2026, 9, 25, 3, 30, 29, 900_000, tzinfo=UTC)
    execution = SimpleNamespace(
        provider_name="alpaca",
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "market_data_requests_per_minute",
                        "limit": 200,
                        "window_seconds": 60,
                        "unit": "requests",
                        "scope": "account",
                        "quota_group": "account",
                        "native_reset_skew_seconds": 2,
                    }
                ],
                "reset": "rolling",
            }
        ),
    )
    candidate = provider_account_usage._native_baseline_candidate(
        execution,
        ProviderAccountUsageDimension(
            name="market_data_requests_per_minute",
            unit="requests",
            limit=200,
            remaining=199,
            consumed=1,
            reset_at=datetime(2026, 9, 25, 3, 30, 26, tzinfo=UTC),
        ),
        observed_at,
    )
    assert candidate is None


@pytest.mark.asyncio
async def test_refresh_persists_provider_native_counters_and_stops_after_first_provider(
    db, monkeypatch
):
    source = DataSource(name="marketdata_app", base_url="https://api.marketdata.app/v1")
    db.add(source)
    db.flush()
    observed_at = datetime(2026, 9, 12, 12, 0, tzinfo=UTC)
    reset_at = observed_at + timedelta(days=1)
    resolved = SimpleNamespace(provider_name="marketdata_app")
    execution = SimpleNamespace(
        provider_name="marketdata_app",
        data_source=source,
        result=ProviderAccountUsage(
            provider="marketdata_app",
            observed_at=observed_at,
            unit="credits",
            limit=10000,
            remaining=9994,
            consumed=6,
            reset_at=reset_at,
            options_data_permissions="delayed",
            raw_payload={"plan": "starter", "credits": 6},
            response_headers={"x-api-ratelimit-limit": "10000"},
        ),
    )
    calls = []

    async def fake_chain(*args, **kwargs):
        return [resolved]

    async def fake_execute(*args, **kwargs):
        calls.append(kwargs["provider_name"])
        return execution

    monkeypatch.setattr(provider_account_usage, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(provider_account_usage, "execute_provider_call", fake_execute)

    result = await provider_account_usage.refresh_provider_account_usage(
        AsyncSessionAdapter(db), provider_name="marketdata_app"
    )

    assert result["status"] == "refreshed"
    assert result["providers"] == ["marketdata_app"]
    assert calls == ["marketdata_app"]
    row = db.execute(
        select(ProviderAccountUsageObservation).where(
            ProviderAccountUsageObservation.data_source_id == source.id
        )
    ).scalar_one()
    assert row.limit == 10000
    assert row.dimension == "credits_per_day"
    assert row.remaining == 9994
    assert row.consumed == 6
    assert row.reset_at.replace(tzinfo=UTC) == reset_at
    assert row.payload == {"plan": "starter", "credits": 6}
    assert row.response_headers == {"x-api-ratelimit-limit": "10000"}


@pytest.mark.asyncio
async def test_marketdata_native_usage_reconciles_exact_coordinator_baseline(
    db, monkeypatch, tmp_path
):
    source = DataSource(name="marketdata_app", base_url="https://api.marketdata.app/v1")
    db.add(source)
    db.flush()
    observed_at = datetime.now(UTC).replace(microsecond=0)
    reset_at = observed_at + timedelta(days=1)
    policy = SimpleNamespace(
        quota_contract={
            "dimensions": [
                {
                    "name": "credits_per_day",
                    "limit": 10000,
                    "window_seconds": 86400,
                    "unit": "credits",
                    "scope": "api_key",
                    "quota_group": "account",
                }
            ],
            "reset": "09:30 America/New_York",
        },
        quota_scope="api_key",
    )
    execution = SimpleNamespace(
        provider_name="marketdata_app",
        data_source=source,
        policy=policy,
        result=ProviderAccountUsage(
            provider="marketdata_app",
            observed_at=observed_at,
            unit="credits",
            limit=10000,
            remaining=9975,
            consumed=None,
            reset_at=reset_at,
        ),
    )

    async def fake_chain(*args, **kwargs):
        return [SimpleNamespace(provider_name="marketdata_app")]

    async def fake_execute(*args, **kwargs):
        return execution

    monkeypatch.setattr(provider_account_usage, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(provider_account_usage, "execute_provider_call", fake_execute)
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_PATH",
        str(tmp_path / "quota.sqlite3"),
    )

    result = await provider_account_usage.refresh_provider_account_usage(
        AsyncSessionAdapter(db), provider_name="marketdata_app"
    )

    assert result["baseline_reconciliations"][0]["used_units"] == 25
    assert result["baseline_reconciliations"][0]["source"] == ("provider_account_observation")


@pytest.mark.asyncio
async def test_named_provider_usage_dimensions_persist_as_separate_rows(db, monkeypatch):
    source = DataSource(name="twelve_data", base_url="https://api.twelvedata.com")
    db.add(source)
    db.flush()
    observed_at = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    execution = SimpleNamespace(
        provider_name="twelve_data",
        data_source=source,
        result=ProviderAccountUsage(
            provider="twelve_data",
            observed_at=observed_at,
            unit="credits",
            account_plan="Basic",
            dimensions=(
                ProviderAccountUsageDimension(
                    name="credits_per_minute",
                    unit="credits",
                    limit=8,
                    remaining=5,
                    consumed=3,
                    reset_at=observed_at.replace(second=0) + timedelta(minutes=1),
                ),
                ProviderAccountUsageDimension(
                    name="requests_per_minute",
                    unit="requests",
                    limit=8,
                    remaining=5,
                    consumed=3,
                    reset_at=None,
                ),
                ProviderAccountUsageDimension(
                    name="requests_per_day",
                    unit="requests",
                    limit=800,
                    remaining=763,
                    consumed=37,
                    reset_at=None,
                ),
            ),
        ),
    )

    async def fake_chain(*args, **kwargs):
        return [SimpleNamespace(provider_name="twelve_data")]

    async def fake_execute(*args, **kwargs):
        return execution

    monkeypatch.setattr(provider_account_usage, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(provider_account_usage, "execute_provider_call", fake_execute)

    result = await provider_account_usage.refresh_provider_account_usage(
        AsyncSessionAdapter(db), provider_name="twelve_data"
    )

    assert result["status"] == "refreshed"
    assert {item["dimension"] for item in result["observations"]} == {
        "credits_per_minute",
        "requests_per_minute",
        "requests_per_day",
    }
    rows = (
        db.execute(
            select(ProviderAccountUsageObservation).where(
                ProviderAccountUsageObservation.data_source_id == source.id
            )
        )
        .scalars()
        .all()
    )
    assert {row.dimension for row in rows} == {
        "credits_per_minute",
        "requests_per_minute",
        "requests_per_day",
    }
    assert {row.account_plan for row in rows} == {"Basic"}


@pytest.mark.asyncio
async def test_twelve_data_native_minute_usage_reconciles_exact_coordinator_baseline(
    db, monkeypatch, tmp_path
):
    source = DataSource(name="twelve_data", base_url="https://api.twelvedata.com")
    db.add(source)
    db.flush()
    observed_at = datetime.now(UTC).replace(microsecond=0)
    reset_at = observed_at.replace(second=0) + timedelta(minutes=1)
    execution = SimpleNamespace(
        provider_name="twelve_data",
        data_source=source,
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "credits_per_minute",
                        "limit": 8,
                        "window_seconds": 60,
                        "unit": "credits",
                        "scope": "api_key",
                        "quota_group": "api_key",
                    }
                ],
                "reset": "fixed_minute",
            },
            quota_scope="api_key",
        ),
        result=ProviderAccountUsage(
            provider="twelve_data",
            observed_at=observed_at,
            unit="credits",
            account_plan="Basic",
            dimensions=(
                ProviderAccountUsageDimension(
                    name="credits_per_minute",
                    unit="credits",
                    limit=8,
                    remaining=5,
                    consumed=3,
                    reset_at=reset_at,
                ),
                ProviderAccountUsageDimension(
                    name="requests_per_minute",
                    unit="requests",
                    limit=8,
                    remaining=5,
                    consumed=3,
                    reset_at=None,
                ),
                ProviderAccountUsageDimension(
                    name="requests_per_day",
                    unit="requests",
                    limit=800,
                    remaining=763,
                    consumed=37,
                    reset_at=None,
                ),
            ),
        ),
    )

    async def fake_chain(*args, **kwargs):
        return [SimpleNamespace(provider_name="twelve_data")]

    async def fake_execute(*args, **kwargs):
        return execution

    monkeypatch.setattr(provider_account_usage, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(provider_account_usage, "execute_provider_call", fake_execute)
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_PATH",
        str(tmp_path / "quota.sqlite3"),
    )

    result = await provider_account_usage.refresh_provider_account_usage(
        AsyncSessionAdapter(db), provider_name="twelve_data"
    )

    assert len(result["baseline_reconciliations"]) == 1
    assert result["baseline_reconciliations"][0]["dimension"] == "credits_per_minute"
    assert result["baseline_reconciliations"][0]["used_units"] == 3
    assert result["baseline_reconciliations"][0]["source"] == ("provider_account_observation")
    assert {item["dimension"] for item in result["observations"]} >= {
        "requests_per_minute",
        "requests_per_day",
    }


@pytest.mark.asyncio
async def test_eodhd_native_daily_usage_reconciles_exact_coordinator_baseline(
    db, monkeypatch, tmp_path
):
    source = DataSource(name="eodhd", base_url="https://eodhd.com/api")
    db.add(source)
    db.flush()
    observed_at = datetime.now(UTC).replace(microsecond=0)
    reset_at = datetime(
        observed_at.year,
        observed_at.month,
        observed_at.day,
        tzinfo=UTC,
    ) + timedelta(days=1)
    execution = SimpleNamespace(
        provider_name="eodhd",
        data_source=source,
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "calls_per_day",
                        "limit": 20,
                        "window_seconds": 86400,
                        "unit": "calls",
                        "scope": "api_key",
                        "quota_group": "api_key",
                    }
                ],
                "reset": "calendar_day_gmt",
            },
            quota_scope="api_key",
        ),
        result=ProviderAccountUsage(
            provider="eodhd",
            observed_at=observed_at,
            unit="calls",
            account_plan="monthly",
            dimensions=(
                ProviderAccountUsageDimension(
                    name="calls_per_day",
                    unit="calls",
                    limit=20,
                    remaining=13,
                    consumed=7,
                    reset_at=reset_at,
                ),
                ProviderAccountUsageDimension(
                    name="requests_per_minute",
                    unit="requests",
                    limit=20,
                    remaining=19,
                    consumed=1,
                    reset_at=None,
                ),
            ),
        ),
    )

    async def fake_chain(*args, **kwargs):
        return [SimpleNamespace(provider_name="eodhd")]

    async def fake_execute(*args, **kwargs):
        return execution

    monkeypatch.setattr(provider_account_usage, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(provider_account_usage, "execute_provider_call", fake_execute)
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_PATH",
        str(tmp_path / "quota.sqlite3"),
    )

    result = await provider_account_usage.refresh_provider_account_usage(
        AsyncSessionAdapter(db), provider_name="eodhd"
    )

    assert result["baseline_reconciliations"][0]["dimension"] == "calls_per_day"
    assert result["baseline_reconciliations"][0]["used_units"] == 7
    assert result["baseline_reconciliations"][0]["source"] == ("provider_account_observation")


@pytest.mark.asyncio
async def test_marketdata_app_native_larger_counter_seeds_only_reviewed_budget(
    db, monkeypatch, tmp_path
):
    source = DataSource(name="marketdata_app", base_url="https://api.marketdata.app/v1")
    db.add(source)
    db.flush()
    observed_at = datetime.now(UTC).replace(microsecond=0)
    execution = SimpleNamespace(
        provider_name="marketdata_app",
        data_source=source,
        policy=SimpleNamespace(
            quota_contract={
                "dimensions": [
                    {
                        "name": "credits_per_day",
                        "limit": 100,
                        "window_seconds": 86400,
                        "unit": "credits",
                        "scope": "api_key",
                        "quota_group": "account",
                    }
                ],
                "reset": "09:30 America/New_York",
            },
            quota_scope="api_key",
        ),
        result=ProviderAccountUsage(
            provider="marketdata_app",
            observed_at=observed_at,
            unit="credits",
            limit=10000,
            remaining=9975,
            consumed=25,
            reset_at=observed_at + timedelta(days=1),
        ),
    )

    async def fake_chain(*args, **kwargs):
        return [SimpleNamespace(provider_name="marketdata_app")]

    async def fake_execute(*args, **kwargs):
        return execution

    monkeypatch.setattr(provider_account_usage, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(provider_account_usage, "execute_provider_call", fake_execute)
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_LEDGER_PATH",
        str(tmp_path / "quota.sqlite3"),
    )

    result = await provider_account_usage.refresh_provider_account_usage(
        AsyncSessionAdapter(db), provider_name="marketdata_app"
    )

    assert result["baseline_reconciliations"][0]["dimension"] == "credits_per_day"
    assert result["baseline_reconciliations"][0]["used_units"] == 25
    assert result["observations"][0]["consumed"] == 25


def test_fmp_daily_usage_display_uses_documented_fixed_est_reset_boundary():
    from app.services.provider_usage import _window_end_for_reset

    winter_start = datetime(2026, 1, 15, 20, tzinfo=UTC)
    summer_start = datetime(2026, 7, 15, 19, tzinfo=UTC)
    assert _window_end_for_reset(
        winter_start,
        window_seconds=86_400,
        reset="15:00 UTC-05:00",
    ) == datetime(2026, 1, 16, 20, tzinfo=UTC)
    assert _window_end_for_reset(
        summer_start,
        window_seconds=86_400,
        reset="15:00 UTC-05:00",
    ) == datetime(2026, 7, 16, 20, tzinfo=UTC)


@pytest.mark.asyncio
async def test_refresh_is_fail_closed_when_no_provider_is_qualified(db, monkeypatch):
    async def fake_chain(*args, **kwargs):
        return []

    monkeypatch.setattr(provider_account_usage, "resolve_provider_chain", fake_chain)
    result = await provider_account_usage.refresh_provider_account_usage(AsyncSessionAdapter(db))
    assert result == {"status": "no_qualified_provider", "providers": [], "observations": []}


@pytest.mark.asyncio
async def test_refresh_rejects_malformed_native_counters_without_persisting(db, monkeypatch):
    source = DataSource(name="marketdata_app")
    db.add(source)
    db.flush()
    resolved = SimpleNamespace(provider_name="marketdata_app")
    execution = SimpleNamespace(
        provider_name="marketdata_app",
        data_source=source,
        result=ProviderAccountUsage(
            provider="marketdata_app",
            observed_at=datetime.now(UTC),
            unit="credits",
            limit=10,
            remaining=11,
        ),
    )

    async def fake_chain(*args, **kwargs):
        return [resolved]

    async def fake_execute(*args, **kwargs):
        return execution

    monkeypatch.setattr(provider_account_usage, "resolve_provider_chain", fake_chain)
    monkeypatch.setattr(provider_account_usage, "execute_provider_call", fake_execute)
    result = await provider_account_usage.refresh_provider_account_usage(AsyncSessionAdapter(db))

    assert result["status"] == "failed"
    assert result["observations"] == []
    assert db.execute(select(ProviderAccountUsageObservation)).scalars().all() == []


@pytest.mark.asyncio
async def test_list_returns_latest_durable_observations(db):
    source = DataSource(name="marketdata_app", base_url="https://api.marketdata.app/v1")
    db.add(source)
    db.flush()
    db.add_all(
        [
            ProviderAccountUsageObservation(
                data_source_id=source.id,
                observed_at=datetime(2026, 9, 11, tzinfo=UTC),
                unit="credits",
                limit=100,
                remaining=90,
            ),
            ProviderAccountUsageObservation(
                data_source_id=source.id,
                observed_at=datetime(2026, 9, 12, tzinfo=UTC),
                unit="credits",
                limit=100,
                remaining=80,
            ),
        ]
    )
    db.flush()

    rows = await provider_account_usage.list_provider_account_usage(
        AsyncSessionAdapter(db), provider_name="marketdata_app", limit=1
    )
    assert len(rows) == 1
    assert rows[0]["remaining"] == 80
