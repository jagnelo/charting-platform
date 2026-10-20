from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from multiprocessing import get_context
from types import SimpleNamespace

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.services.provider_quota_coordinator import (
    ProviderQuotaAdmissionError,
    ProviderQuotaCoordinatorError,
    _baselines,
    _current_contract_limit,
    _engine_for,
    _engine_url,
    _reservation_plan_for_live_probe,
    _safe_stored_evidence_reference,
    _utc,
    _validate_engine_url,
    _validated_live_receipt_provider,
    account_scope_for_provider,
    ensure_provider_quota_coordinator,
    provider_quota_baseline_status,
    provider_quota_coordinator_summary,
    reconcile_live_receipt_reservation,
    reconcile_pending_live_receipts,
    reconcile_provider_quota_baseline,
    register_live_receipt_reservation,
    reserve_live_provider_operation,
    reserve_provider_quota,
    settle_live_provider_operation,
    settle_provider_quota,
)


def _policy(*dimensions, reset="fixed_minute", scope="api_key"):
    return SimpleNamespace(
        quota_scope=scope,
        quota_source="test provider contract",
        quota_contract={"reset": reset, "dimensions": list(dimensions)},
    )


def test_dinari_canary_plan_is_durable_local_and_only_one_daily_catalogue_read(monkeypatch):
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_RUN", "1")
    reset, costs, specs = _reservation_plan_for_live_probe(
        "dinari",
        "discover_tokenized_assets",
        "canary-test",
        datetime(2026, 10, 10, 12, tzinfo=UTC),
        operation_cost_override=1,
    )
    assert reset == "calendar_day_utc"
    assert costs == {"local_canary_requests_per_utc_day": 1}
    assert len(specs) == 1
    assert specs[0]["dimension"] == "local_canary_requests_per_utc_day"
    assert specs[0]["window_seconds"] == 86400
    assert specs[0]["quota_group"] == "dinari_sandbox_canary"
    assert specs[0]["account_scope"] == "dinari:shared-public_api"


def test_dinari_canary_plan_rejects_other_operations(monkeypatch):
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_RUN", "1")
    with pytest.raises(
        ProviderQuotaAdmissionError,
        match="local Dinari Sandbox canary permits only discover_tokenized_assets",
    ):
        _reservation_plan_for_live_probe(
            "dinari",
            "get_tokenized_price",
            "canary-test",
            datetime(2026, 10, 10, 12, tzinfo=UTC),
            operation_cost_override=1,
        )


def test_dinari_canary_daily_limit_is_shared_and_durable(tmp_path, monkeypatch):
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_RUN", "1")
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")

    reservation = reserve_live_provider_operation(
        "dinari",
        "discover_tokenized_assets",
        operation_cost_override=1,
    )
    assert reservation is not None
    settle_live_provider_operation(reservation, http_requests=1, response_bytes=10)

    # The next session/run shares the same durable account-window ledger and
    # is denied before transport until the local UTC-day window resets.
    assert (
        reserve_live_provider_operation(
            "dinari",
            "discover_tokenized_assets",
            operation_cost_override=1,
        )
        is None
    )


def test_live_settlement_reports_safe_failure_type_and_keeps_reservation(tmp_path, monkeypatch):
    import app.services.provider_quota_coordinator as coordinator

    monkeypatch.setenv("DINARI_SANDBOX_CANARY_RUN", "1")
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")
    reservation = reserve_live_provider_operation(
        "dinari",
        "discover_tokenized_assets",
        operation_cost_override=1,
    )
    assert reservation is not None

    def fail_coordinator_open(*_args, **_kwargs):
        raise OSError("sensitive coordinator details")

    with monkeypatch.context() as patcher:
        patcher.setattr(coordinator, "_engine_for", fail_coordinator_open)
        with pytest.raises(
            ProviderQuotaCoordinatorError,
            match="settlement failed \\(OSError\\); outstanding reservation retained",
        ) as error:
            settle_live_provider_operation(reservation, http_requests=1, response_bytes=10)

    assert "sensitive coordinator details" not in str(error.value)
    window = provider_quota_coordinator_summary(provider_name="dinari")["windows"][0]
    assert window["reserved_units"] == 1


def test_marketstack_dashboard_baseline_is_reconciled_to_rolling_monthly_budget(
    tmp_path, monkeypatch
):
    from app.config import provider_rate_limit_seed

    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")
    seed = provider_rate_limit_seed("marketstack")
    policy = SimpleNamespace(
        quota_scope=seed["quota_scope"],
        quota_contract=seed["quota_contract"],
    )
    observed_at = datetime(2026, 10, 10, 18, 0, tzinfo=UTC)

    record = reconcile_provider_quota_baseline(
        provider_name="marketstack",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_month",
        used_units=37,
        observed_at=observed_at,
        evidence_reference="dashboard:marketstack:2026-10-10",
        source="operator_dashboard_attestation",
        now=observed_at,
    )
    status = provider_quota_baseline_status(
        provider_name="marketstack",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_month",
        now=observed_at,
    )

    assert record["unit"] == "requests"
    assert record["limit_units"] == 100
    assert record["used_units"] == 37
    assert record["rolling"] is True
    assert status["status"] == "verified"
    assert status["effective_used_units"] == 37
    assert status["remaining_units"] == 63


def test_tiingo_dashboard_baselines_accept_explicit_rolling_reset_safeties(tmp_path, monkeypatch):
    from app.config import provider_rate_limit_seed

    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")
    monkeypatch.setattr(settings, "TIINGO_REVIEWED_PLAN", "custom")
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_UNIQUE_SYMBOLS_PER_MONTH", 500)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_REQUESTS_PER_HOUR", 50)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_REQUESTS_PER_DAY", 1_000)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_BANDWIDTH_BYTES_PER_MONTH", 2_000_000_000)
    monkeypatch.setattr(settings, "TIINGO_CUSTOM_QUOTA_EVIDENCE", "dashboard:tiingo:2026-10-14")
    seed = provider_rate_limit_seed("tiingo")
    policy = SimpleNamespace(
        quota_scope=seed["quota_scope"],
        quota_contract=seed["quota_contract"],
    )
    observed_at = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
    expected_remaining = {
        "unique_symbols_per_month": 500,
        "requests_per_hour": 50,
        "requests_per_day": 1_000,
        "bandwidth_bytes_per_month": 2_000_000_000,
    }

    for dimension_name, remaining in expected_remaining.items():
        reconcile_provider_quota_baseline(
            provider_name="tiingo",
            capability="price_history",
            policy=policy,
            dimension_name=dimension_name,
            used_units=0,
            observed_at=observed_at,
            evidence_reference="dashboard:tiingo:2026-10-14",
            source="operator_dashboard_attestation",
            now=observed_at,
        )
        status = provider_quota_baseline_status(
            provider_name="tiingo",
            capability="price_history",
            policy=policy,
            dimension_name=dimension_name,
            now=observed_at,
        )

        assert status["status"] == "verified"
        assert status["effective_used_units"] == 0
        assert status["remaining_units"] == remaining


def _dimension(name="requests_per_minute", limit=3, unit="requests", **extra):
    return {
        "name": name,
        "limit": limit,
        "window_seconds": 60,
        "unit": unit,
        "scope": extra.pop("scope", "api_key"),
        "source": "https://provider.example/rate-limits",
        **extra,
    }


def test_utc_normalizes_iso_string_baseline_timestamps():
    assert _utc("2026-10-09T08:15:00+00:00") == datetime(2026, 10, 9, 8, 15)
    assert _utc("2026-10-09T10:15:00+02:00") == datetime(2026, 10, 9, 8, 15)


def _reserve(policy, units, *, now, provider="fixture", operation="fetch_ohlcv", identity=None):
    _seed_test_baseline(policy, now=now, provider=provider)
    return reserve_provider_quota(
        provider_name=provider,
        capability="price_history",
        operation=operation,
        policy=policy,
        dimension_units=units,
        usage_identity=identity,
        now=now,
    )


def _seed_test_baseline(policy, *, now, provider="fixture", capability="price_history"):
    for dimension in policy.quota_contract.get("dimensions", []):
        if str(dimension.get("unit") or "").lower() in {"concurrent_requests", "concurrency"}:
            continue
        dimension_name = str(dimension["name"])
        status = provider_quota_baseline_status(
            provider_name=provider,
            capability=capability,
            policy=policy,
            dimension_name=dimension_name,
            now=now,
        )
        if status["status"] != "verified":
            reconcile_provider_quota_baseline(
                provider_name=provider,
                capability=capability,
                policy=policy,
                dimension_name=dimension_name,
                used_units=0,
                observed_at=now,
                evidence_reference="test-fixture:fixture:isolated-pytest",
                now=now,
            )


def _seed_live_test_baseline(provider: str, *, now: datetime | None = None):
    from app.config import provider_rate_limit_seed

    current = now or datetime.now(UTC)
    seed = provider_rate_limit_seed(provider)
    policy = SimpleNamespace(
        quota_scope=seed.get("quota_scope", "api_key"),
        quota_contract=seed.get("quota_contract", {}),
    )
    _seed_test_baseline(policy, now=current, provider=provider)


def _register_summary_policy(monkeypatch, provider: str, policy) -> None:
    seeds = dict(settings.PROVIDER_RATE_LIMIT_SEEDS)
    seeds[provider] = {
        "quota_scope": policy.quota_scope,
        "quota_contract": policy.quota_contract,
    }
    monkeypatch.setattr(settings, "PROVIDER_RATE_LIMIT_SEEDS", seeds)


def _reserve_once_in_process(path: str, barrier, outcomes) -> None:
    """Subprocess worker proving one SQLite quota bucket is shared cross-process."""

    from app.config import settings as process_settings

    process_settings.PROVIDER_QUOTA_LEDGER_PATH = path
    process_settings.PROVIDER_QUOTA_LEDGER_DATABASE_URL = ""
    barrier.wait(timeout=15)
    policy = _policy(_dimension(limit=1))
    try:
        reserved = (
            reserve_provider_quota(
                provider_name="fixture",
                capability="price_history",
                operation="fetch_ohlcv",
                policy=policy,
                dimension_units={"requests_per_minute": 1},
                now=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
            )
            is not None
        )
        outcomes.put(("ok", reserved))
    except BaseException as exc:  # pragma: no cover - subprocess error reporting
        outcomes.put(
            (
                "error",
                type(exc).__name__,
                str(exc),
                type(exc.__context__).__name__ if exc.__context__ else "none",
                str(exc.__context__) if exc.__context__ else "",
            )
        )


def test_reservation_is_committed_and_shared_by_same_provider_account(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_ACCOUNT_SCOPES", {"fixture": "local-key-a"})
    policy = _policy(_dimension(limit=2))
    _register_summary_policy(monkeypatch, "fixture", policy)
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    first = _reserve(policy, {"requests_per_minute": 1}, now=now)
    assert first is not None
    # A separate call/process sees the un-settled committed reservation.
    assert _reserve(policy, {"requests_per_minute": 1}, now=now) is not None
    assert _reserve(policy, {"requests_per_minute": 1}, now=now) is None
    summary = provider_quota_coordinator_summary(provider_name="fixture", now=now)
    window = summary["windows"][0]
    assert window["account_scope"] == "local-key-a"
    assert window["reserved_units"] == 2
    assert window["remaining_units"] == 0, summary


def test_ten_gigabyte_quota_can_be_reserved_in_durable_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_ACCOUNT_SCOPES", {"fixture": "finra-test"})
    now = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    policy = _policy(
        _dimension(
            name="bytes_per_month",
            limit=10_000_000_000,
            unit="bytes",
            window_seconds=30 * 24 * 60 * 60,
        ),
        reset="calendar_month_utc",
    )
    reservation = _reserve(
        policy,
        {"bytes_per_month": 6_000_000_000},
        now=now,
        provider="fixture",
    )

    assert reservation is not None
    settle_provider_quota(
        reservation,
        observed_dimension_units={"bytes_per_month": 6_000_000_000},
        now=now,
    )
    status = provider_quota_baseline_status(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="bytes_per_month",
        now=now,
    )
    assert status["status"] == "verified"
    assert status["remaining_units"] == 4_000_000_000


def test_unknown_current_window_baseline_blocks_until_exact_seed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=3))
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    status = provider_quota_baseline_status(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_minute",
        now=now,
    )
    assert status["status"] == "unknown"
    assert (
        reserve_provider_quota(
            provider_name="fixture",
            capability="price_history",
            operation="fetch_ohlcv",
            policy=policy,
            dimension_units={"requests_per_minute": 1},
            now=now,
        )
        is None
    )

    seeded = reconcile_provider_quota_baseline(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_minute",
        used_units=2,
        observed_at=now,
        evidence_reference="dashboard:fixture:2026-09-15",
        now=now,
    )
    assert seeded["used_units"] == 2
    reservation = reserve_provider_quota(
        provider_name="fixture",
        capability="price_history",
        operation="fetch_ohlcv",
        policy=policy,
        dimension_units={"requests_per_minute": 1},
        now=now,
    )
    assert reservation is not None
    settle_provider_quota(
        reservation,
        observed_dimension_units={"requests_per_minute": 1},
        now=now,
    )
    assert (
        reserve_provider_quota(
            provider_name="fixture",
            capability="price_history",
            operation="fetch_ohlcv",
            policy=policy,
            dimension_units={"requests_per_minute": 1},
            now=now,
        )
        is None
    )


def test_marketstack_monthly_reset_unknown_uses_rolling_30_day_safety(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_LIMIT", 100)
    monkeypatch.setattr(settings, "MARKETSTACK_REVIEWED_MONTHLY_RESET", "")
    monkeypatch.setattr(settings, "MARKETSTACK_QUOTA_EVIDENCE", "")
    from app.config import provider_rate_limit_seed

    seed = provider_rate_limit_seed("marketstack")
    now = datetime(2026, 10, 6, 16, 0, tzinfo=UTC)
    _reset, _dimension_units, specs = _reservation_plan_for_live_probe(
        "marketstack", "get_current_price", "AAPL", now
    )

    assert seed["quota_contract"]["reset"] == "per_dimension"
    assert seed["quota_contract"]["unknown_dimensions"] == [
        "monthly_cap_reset_boundary",
        "requests_per_second_reset_boundary",
    ]
    assert len(specs) == 2
    assert specs[0]["reset"] == "provider_defined"
    assert specs[0]["rolling"] is True
    assert specs[0]["window_seconds"] == 2_592_000
    assert specs[1]["dimension"] == "requests_per_second"
    assert specs[1]["limit_units"] == 5
    assert specs[1]["reset"] == "provider_defined"
    assert specs[1]["rolling"] is True
    assert specs[1]["window_seconds"] == 1


def test_owner_attestation_can_seed_exact_quota_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=3))
    observed = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    seeded = reconcile_provider_quota_baseline(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_minute",
        used_units=0,
        observed_at=observed,
        evidence_reference="owner:fixture:2026-09-15",
        source="operator_owner_attestation",
        now=observed,
    )

    assert seeded["used_units"] == 0
    assert seeded["source"] == "operator_owner_attestation"
    assert (
        reserve_provider_quota(
            provider_name="fixture",
            capability="price_history",
            operation="fetch_ohlcv",
            policy=policy,
            dimension_units={"requests_per_minute": 1},
            now=observed,
        )
        is not None
    )


def test_explicit_local_zero_baseline_is_persisted_for_client_owned_pool(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(
        _dimension(
            "directory_requests_per_market_day",
            limit=2,
            window_seconds=86400,
            scope="deployment",
            quota_group="directory",
            baseline_mode="local_zero",
            application_usage_only=True,
        ),
        reset="calendar_day_est",
        scope="deployment",
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    status = provider_quota_baseline_status(
        provider_name="fixture",
        capability="universe",
        policy=policy,
        dimension_name="directory_requests_per_market_day",
        now=now,
    )
    assert status["status"] == "initializable"
    assert status["initial_baseline"] == "local_zero"
    assert status["remaining_units"] == 2

    reservation = reserve_provider_quota(
        provider_name="fixture",
        capability="universe",
        operation="discover_universe_page",
        policy=policy,
        dimension_units={"directory_requests_per_market_day": 1},
        now=now,
    )
    assert reservation is not None
    settled = provider_quota_baseline_status(
        provider_name="fixture",
        capability="universe",
        policy=policy,
        dimension_name="directory_requests_per_market_day",
        now=now,
    )
    assert settled["status"] == "verified"
    assert settled["baseline"]["source"] == "local_policy"
    assert settled["baseline"]["evidence_reference"] == "application-policy:fixture:local-zero"

    settle_provider_quota(
        reservation,
        observed_dimension_units={"directory_requests_per_market_day": 1},
        now=now,
    )
    second_reservation = reserve_provider_quota(
        provider_name="fixture",
        capability="universe",
        operation="discover_universe_page",
        policy=policy,
        dimension_units={"directory_requests_per_market_day": 1},
        now=now,
    )
    assert second_reservation is not None
    settle_provider_quota(
        second_reservation,
        observed_dimension_units={"directory_requests_per_market_day": 1},
        now=now,
    )


def test_local_zero_baseline_preserves_settled_debits_already_in_active_window(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")
    policy = _policy(
        _dimension(
            "requests_per_day",
            limit=1,
            window_seconds=86400,
            scope="api_key",
            quota_group="api_key",
            safety_reset="rolling",
            baseline_mode="local_zero",
            application_usage_only=True,
        ),
        reset="provider_defined",
        scope="api_key",
    )
    first_at = datetime(2026, 10, 14, 7, 42, tzinfo=UTC)
    first = reserve_provider_quota(
        provider_name="fixture",
        capability="price_history",
        operation="fetch_ohlcv",
        policy=policy,
        dimension_units={"requests_per_day": 1},
        now=first_at,
    )
    assert first is not None
    settle_provider_quota(
        first,
        observed_dimension_units={"requests_per_day": 1},
        now=first_at,
    )

    # Simulate an older coordinator deployment which recorded the request but
    # did not yet have a baseline row for this dimension.
    engine = _engine_for(_engine_url())
    with engine.begin() as connection:
        connection.execute(delete(_baselines).where(_baselines.c.source_provider_name == "fixture"))
    engine.dispose()

    next_at = first_at + timedelta(seconds=30)
    assert (
        reserve_provider_quota(
            provider_name="fixture",
            capability="price_history",
            operation="fetch_ohlcv",
            policy=policy,
            dimension_units={"requests_per_day": 1},
            now=next_at,
        )
        is None
    )
    status = provider_quota_baseline_status(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_day",
        now=next_at,
    )
    assert status["baseline"]["used_units"] == 0
    assert status["effective_used_units"] == 1
    assert status["remaining_units"] == 0

    # The old debit ages out at its own timestamp, even though the replacement
    # local-zero baseline is still within its validity window.
    aged_out_at = first_at + timedelta(seconds=86410)
    aged_status = provider_quota_baseline_status(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_day",
        now=aged_out_at,
    )
    assert aged_status["baseline"]["used_units"] == 0
    assert aged_status["effective_used_units"] == 0
    assert aged_status["remaining_units"] == 1
    aged_reservation = reserve_provider_quota(
        provider_name="fixture",
        capability="price_history",
        operation="fetch_ohlcv",
        policy=policy,
        dimension_units={"requests_per_day": 1},
        now=aged_out_at,
    )
    assert aged_reservation is not None


def test_zero_cost_dimension_does_not_require_a_starting_baseline(tmp_path, monkeypatch):
    """Unmetered provider introspection may bootstrap the durable coordinator."""

    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(
        _dimension("credits_per_day", limit=100, unit="credits"),
        _dimension("concurrent_requests", limit=50, unit="concurrent_requests"),
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    reservation = reserve_provider_quota(
        provider_name="fixture",
        capability="account_usage",
        operation="fetch_account_usage",
        policy=policy,
        dimension_units={"credits_per_day": 0, "concurrent_requests": 1},
        now=now,
    )
    assert reservation is not None

    settle_provider_quota(
        reservation,
        observed_dimension_units={"credits_per_day": 0},
        now=now,
    )
    summary = provider_quota_coordinator_summary(provider_name="fixture", now=now)
    assert {row["dimension"]: row["consumed_units"] for row in summary["windows"]} == {
        "concurrent_requests": 0
    }
    assert all(row["dimension"] != "credits_per_day" for row in summary["windows"])


def test_fixed_window_baseline_never_moves_down_on_stale_or_lower_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=20))
    # Keep the stale and newer snapshots inside the same fixed-minute bucket
    # so this exercises monotonic observation ordering, not reset rejection.
    now = datetime(2026, 9, 15, 12, 0, 10, tzinfo=UTC)
    reconcile_provider_quota_baseline(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_minute",
        used_units=8,
        observed_at=now,
        evidence_reference="dashboard:fixture:2026-09-15",
        now=now,
    )

    with pytest.raises(ProviderQuotaAdmissionError, match="older than"):
        reconcile_provider_quota_baseline(
            provider_name="fixture",
            capability="price_history",
            policy=policy,
            dimension_name="requests_per_minute",
            used_units=1,
            observed_at=now - timedelta(seconds=1),
            evidence_reference="dashboard:fixture:stale-snapshot",
            now=now,
        )
    lower = reconcile_provider_quota_baseline(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_minute",
        used_units=1,
        observed_at=now + timedelta(seconds=1),
        evidence_reference="dashboard:fixture:lower-newer",
        now=now + timedelta(seconds=1),
    )
    assert lower["used_units"] == 8


def test_reconciliation_preserves_settled_local_debits_beyond_lower_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=20))
    started = datetime(2026, 9, 15, 12, 0, 10, tzinfo=UTC)
    reconcile_provider_quota_baseline(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_minute",
        used_units=5,
        observed_at=started,
        evidence_reference="dashboard:fixture:initial-snapshot",
        now=started,
    )
    reservation = reserve_provider_quota(
        provider_name="fixture",
        capability="price_history",
        operation="fetch_ohlcv",
        policy=policy,
        dimension_units={"requests_per_minute": 1},
        now=started + timedelta(seconds=2),
    )
    assert reservation is not None
    settle_provider_quota(
        reservation,
        observed_dimension_units={"requests_per_minute": 1},
        now=started + timedelta(seconds=2),
    )

    reconciled_at = started + timedelta(seconds=4)
    reconciled = reconcile_provider_quota_baseline(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_minute",
        used_units=5,
        observed_at=reconciled_at,
        evidence_reference="dashboard:fixture:lower-snapshot",
        now=reconciled_at,
    )
    assert reconciled["used_units"] == 6
    status = provider_quota_baseline_status(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_minute",
        now=reconciled_at,
    )
    assert status["effective_used_units"] == 6
    assert status["remaining_units"] == 14


def test_exact_cumulative_native_fixed_window_snapshot_replaces_double_counted_baseline(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(
        _dimension(
            "calls_per_day",
            limit=20,
            unit="calls",
            window_seconds=86400,
            reset="calendar_day_gmt",
        ),
        reset="per_dimension",
    )
    initial_at = datetime(2026, 10, 10, 0, 4, tzinfo=UTC)
    newer_at = datetime(2026, 10, 10, 1, 24, tzinfo=UTC)
    reconcile_provider_quota_baseline(
        provider_name="eodhd",
        capability="account_usage",
        policy=policy,
        dimension_name="calls_per_day",
        used_units=15,
        observed_at=initial_at,
        evidence_reference="test-fixture:eodhd:previous-local-overcount",
        source="provider_account_observation",
        now=initial_at,
    )

    corrected = reconcile_provider_quota_baseline(
        provider_name="eodhd",
        capability="account_usage",
        policy=policy,
        dimension_name="calls_per_day",
        used_units=5,
        observed_at=newer_at,
        evidence_reference="test-fixture:eodhd:newer-cumulative-snapshot",
        source="provider_account_observation",
        native_snapshot_includes_prior_local_activity=True,
        now=newer_at,
    )
    assert corrected["used_units"] == 5
    assert (
        provider_quota_baseline_status(
            provider_name="eodhd",
            capability="account_usage",
            policy=policy,
            dimension_name="calls_per_day",
            now=newer_at,
        )["remaining_units"]
        == 15
    )

    after_snapshot = reserve_provider_quota(
        provider_name="eodhd",
        capability="account_usage",
        operation="fetch_ohlcv",
        policy=policy,
        dimension_units={"calls_per_day": 1},
        now=newer_at + timedelta(seconds=1),
    )
    assert after_snapshot is not None
    settle_provider_quota(after_snapshot, observed_dimension_units={"calls_per_day": 1})
    status = provider_quota_baseline_status(
        provider_name="eodhd",
        capability="account_usage",
        policy=policy,
        dimension_name="calls_per_day",
        now=newer_at + timedelta(seconds=2),
    )
    assert status["effective_used_units"] == 6
    assert status["remaining_units"] == 14


def test_equal_timestamp_rolling_snapshot_cannot_lower_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension("rolling_requests", limit=20), reset="rolling")
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    first = reconcile_provider_quota_baseline(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="rolling_requests",
        used_units=10,
        observed_at=now,
        evidence_reference="account-usage:fixture:first-snapshot",
        now=now,
    )
    replay = reconcile_provider_quota_baseline(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="rolling_requests",
        used_units=2,
        observed_at=now,
        evidence_reference="account-usage:fixture:replayed-lower-snapshot",
        now=now,
    )
    assert first["used_units"] == 10
    assert replay["used_units"] == 10


def test_newer_rolling_snapshot_can_decrease_as_provider_usage_ages_out(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(
        _dimension("rolling_requests", limit=20, window_seconds=60),
        reset="rolling",
    )
    first_at = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    first = reconcile_provider_quota_baseline(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="rolling_requests",
        used_units=10,
        observed_at=first_at,
        evidence_reference="account-usage:fixture:first-snapshot",
        now=first_at,
    )
    newer_at = first_at + timedelta(seconds=30)
    newer = reconcile_provider_quota_baseline(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="rolling_requests",
        used_units=4,
        observed_at=newer_at,
        evidence_reference="account-usage:fixture:aged-usage-snapshot",
        now=newer_at,
    )

    assert first["used_units"] == 10
    assert newer["used_units"] == 4
    status = provider_quota_baseline_status(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="rolling_requests",
        now=newer_at,
    )
    assert status["effective_used_units"] == 4


def test_current_shared_bucket_limit_is_unknown_when_provider_contracts_disagree(
    monkeypatch,
):
    policy_a = _policy(_dimension("requests_per_minute", limit=5, quota_group="shared-account"))
    policy_b = _policy(_dimension("requests_per_minute", limit=10, quota_group="shared-account"))
    seeds = dict(settings.PROVIDER_RATE_LIMIT_SEEDS)
    for name, policy in (("fixture-a", policy_a), ("fixture-b", policy_b)):
        seeds[name] = {
            "quota_scope": policy.quota_scope,
            "quota_contract": policy.quota_contract,
        }
    monkeypatch.setattr(settings, "PROVIDER_RATE_LIMIT_SEEDS", seeds)
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"fixture-a": "shared-account", "fixture-b": "shared-account"},
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    common = {
        "provider_names": {"fixture-a", "fixture-b"},
        "account_scope": "shared-account",
        "quota_group": "shared-account",
        "dimension_name": "requests_per_minute",
        "unit": "requests",
        "reset": "fixed_minute",
        "window_seconds": 60,
        "now": now,
    }
    assert _current_contract_limit(**common) == (None, "ambiguous")

    seeds["fixture-b"]["quota_contract"]["dimensions"][0]["limit"] = 5
    monkeypatch.setattr(settings, "PROVIDER_RATE_LIMIT_SEEDS", seeds)
    assert _current_contract_limit(**common) == (5, "verified")


def test_legacy_evidence_references_are_not_returned_if_they_look_unsafe():
    assert (
        _safe_stored_evidence_reference("dashboard:marketdata-app:2026-10-11")
        == "dashboard:marketdata-app:2026-10-11"
    )
    assert _safe_stored_evidence_reference("dashboard:alpaca:AbCdEf0123456789") is None
    assert _safe_stored_evidence_reference("dashboard:alpaca:access-token-example") is None
    assert (
        _safe_stored_evidence_reference("application-policy:alpha_vantage:local-zero")
        == "application-policy:alpha_vantage:local-zero"
    )


def test_existing_private_sqlite_baseline_schema_fails_closed_after_upgrade(tmp_path, monkeypatch):
    from sqlalchemy import create_engine, text

    path = tmp_path / "legacy-quota.sqlite3"
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(path))
    legacy_engine = create_engine(f"sqlite:///{path}")
    with legacy_engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE provider_quota_ledger_baseline ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "account_scope VARCHAR(128) NOT NULL, "
            "quota_group VARCHAR(128) NOT NULL, "
            "dimension VARCHAR(128) NOT NULL, "
            "unit VARCHAR(32) NOT NULL, "
            "window_started_at DATETIME NOT NULL, "
            "window_seconds INTEGER NOT NULL, "
            "rolling BOOLEAN NOT NULL, "
            "limit_units INTEGER NOT NULL, "
            "used_units INTEGER NOT NULL, "
            "observed_at DATETIME NOT NULL, "
            "source VARCHAR(48) NOT NULL, "
            "evidence_reference VARCHAR(256) NOT NULL, "
            "source_provider_name VARCHAR(100) NOT NULL, "
            "actor_user_id INTEGER, "
            "idempotency_key VARCHAR(64) NOT NULL UNIQUE)"
        )
        connection.exec_driver_sql(
            "INSERT INTO provider_quota_ledger_baseline ("
            "account_scope, quota_group, dimension, unit, window_started_at, "
            "window_seconds, rolling, limit_units, used_units, observed_at, "
            "source, evidence_reference, source_provider_name, actor_user_id, "
            "idempotency_key) VALUES ("
            "'fixture-account', 'price_history', 'requests_per_minute', 'requests', "
            "'2026-09-15 12:00:00', 60, 0, 10, 3, '2026-09-15 12:00:00', "
            "'operator_dashboard_attestation', 'legacy-free-text', 'fixture', NULL, "
            "'legacy-baseline')"
        )
    legacy_engine.dispose()

    engine = _engine_for(f"sqlite:///{path}")
    with engine.connect() as connection:
        columns = {
            str(row[1])
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(provider_quota_ledger_baseline)"
            )
        }
        migrated_reset = connection.execute(
            text("SELECT reset FROM provider_quota_ledger_baseline WHERE id = 1")
        ).scalar_one()
    engine.dispose()

    assert "reset" in columns
    assert migrated_reset == "unknown"


def test_rolling_baseline_expires_only_after_the_full_provider_window(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_EXCLUSIVE_ACCOUNT_SCOPES", {})
    policy = _policy(_dimension("rolling_requests", limit=10), reset="rolling")
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    reconcile_provider_quota_baseline(
        provider_name="fixture",
        capability="price_history",
        policy=policy,
        dimension_name="rolling_requests",
        used_units=10,
        observed_at=now,
        evidence_reference="account-usage:fixture:rolling-window",
        now=now,
    )
    arguments = {
        "provider_name": "fixture",
        "capability": "price_history",
        "operation": "fetch_ohlcv",
        "policy": policy,
        "dimension_units": {"rolling_requests": 1},
    }
    assert (
        reserve_provider_quota(
            **arguments,
            now=now + timedelta(seconds=59),
        )
        is None
    )
    assert (
        reserve_provider_quota(
            **arguments,
            now=now + timedelta(seconds=61),
        )
        is None
    )


def test_operator_baseline_can_use_explicit_rolling_safety_for_unknown_native_reset(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    dimension = _dimension(
        "requests_per_day",
        limit=25,
        window_seconds=86400,
        scope="api_key",
        safety_reset="rolling",
    )
    policy = _policy(dimension, reset="provider_defined", scope="api_key")
    policy.quota_contract["unknown_dimensions"] = ["requests_per_day_reset_boundary"]
    now = datetime(2026, 10, 6, 0, 24, tzinfo=UTC)

    baseline = reconcile_provider_quota_baseline(
        provider_name="alpha_vantage",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_day",
        used_units=0,
        observed_at=now,
        evidence_reference="operator-note:alpha-vantage:idle-24h-2026-10-06",
        now=now,
    )

    assert baseline["used_units"] == 0
    reservation = reserve_provider_quota(
        provider_name="alpha_vantage",
        capability="price_history",
        operation="fetch_ohlcv",
        policy=policy,
        dimension_units={"requests_per_day": 1},
        now=now,
    )
    assert reservation is not None


def test_coordinator_summary_uses_recorded_rolling_safety_for_provider_defined_reset(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    dimension = _dimension(
        "requests_per_second",
        limit=1,
        window_seconds=1,
        scope="api_key",
        safety_reset="rolling",
    )
    policy = _policy(dimension, reset="provider_defined", scope="api_key")
    policy.quota_contract["unknown_dimensions"] = ["requests_per_second_reset_boundary"]
    now = datetime(2026, 10, 6, 0, 24, tzinfo=UTC)

    reconcile_provider_quota_baseline(
        provider_name="alpha_vantage",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_second",
        used_units=0,
        observed_at=now,
        evidence_reference="owner:alpha-vantage:2026-10-06",
        source="operator_owner_attestation",
        now=now,
    )

    summary = provider_quota_coordinator_summary(
        provider_name="alpha_vantage", now=now + timedelta(milliseconds=250)
    )
    assert summary["baselines"]
    assert summary["baselines"][0]["dimension"] == "requests_per_second"
    assert summary["baselines"][0]["rolling"] is True


def test_expired_rolling_owner_baseline_is_preflight_initializable_only_for_exclusive_scope(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(
        settings, "PROVIDER_QUOTA_EXCLUSIVE_ACCOUNT_SCOPES", {"alpha_vantage": True}
    )
    dimension = _dimension(
        "requests_per_second",
        limit=1,
        window_seconds=1,
        scope="api_key",
        safety_reset="rolling",
    )
    policy = _policy(dimension, reset="provider_defined", scope="api_key")
    policy.quota_contract["unknown_dimensions"] = ["requests_per_second_reset_boundary"]
    observed_at = datetime(2026, 10, 6, 0, 24, tzinfo=UTC)
    reconcile_provider_quota_baseline(
        provider_name="alpha_vantage",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_second",
        used_units=0,
        observed_at=observed_at,
        evidence_reference="owner:alpha-vantage:2026-10-06",
        source="operator_owner_attestation",
        now=observed_at,
    )

    fresh_status = provider_quota_baseline_status(
        provider_name="alpha_vantage",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_second",
        now=observed_at + timedelta(milliseconds=500),
    )
    assert fresh_status["status"] == "verified"
    expired_status = provider_quota_baseline_status(
        provider_name="alpha_vantage",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_second",
        now=observed_at + timedelta(seconds=2),
    )
    assert expired_status["status"] == "initializable"
    assert expired_status["initial_baseline"] == "exclusive_account_reset"

    monkeypatch.setattr(settings, "PROVIDER_QUOTA_EXCLUSIVE_ACCOUNT_SCOPES", {})
    untrusted_status = provider_quota_baseline_status(
        provider_name="alpha_vantage",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_second",
        now=observed_at + timedelta(seconds=2),
    )
    assert untrusted_status["status"] == "unknown"
    monkeypatch.setattr(
        settings, "PROVIDER_QUOTA_EXCLUSIVE_ACCOUNT_SCOPES", {"alpha_vantage": True}
    )

    reservation = reserve_provider_quota(
        provider_name="alpha_vantage",
        capability="price_history",
        operation="fetch_ohlcv",
        policy=policy,
        dimension_units={"requests_per_second": 1},
        now=observed_at + timedelta(seconds=2),
    )
    assert reservation is not None


def test_operator_baseline_allows_multiple_individually_safe_rolling_resets(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    minute = _dimension(
        "requests_per_minute",
        limit=5,
        window_seconds=60,
        safety_reset="rolling",
    )
    day = _dimension(
        "requests_per_day",
        limit=25,
        window_seconds=86400,
        safety_reset="rolling",
    )
    policy = _policy(minute, day, reset="provider_defined", scope="api_key")
    policy.quota_contract["unknown_dimensions"] = [
        "requests_per_minute_reset_boundary",
        "requests_per_day_reset_boundary",
    ]
    now = datetime(2026, 10, 6, 0, 24, tzinfo=UTC)

    baseline = reconcile_provider_quota_baseline(
        provider_name="alpha_vantage",
        capability="price_history",
        policy=policy,
        dimension_name="requests_per_minute",
        used_units=0,
        observed_at=now,
        evidence_reference="operator-note:alpha-vantage:idle-24h-2026-10-06",
        now=now,
    )

    assert baseline["used_units"] == 0


def test_operator_baseline_does_not_silence_unknown_quota_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    dimension = _dimension(
        "requests_per_day",
        limit=25,
        window_seconds=86400,
        scope="api_key",
        safety_reset="rolling",
    )
    policy = _policy(dimension, reset="provider_defined", scope="api_key")
    policy.quota_contract["unknown_dimensions"] = ["requests_per_day_limit"]
    now = datetime(2026, 10, 6, 0, 24, tzinfo=UTC)

    with pytest.raises(ProviderQuotaAdmissionError, match="not uniquely reviewed"):
        reconcile_provider_quota_baseline(
            provider_name="alpha_vantage",
            capability="price_history",
            policy=policy,
            dimension_name="requests_per_day",
            used_units=0,
            observed_at=now,
            evidence_reference="operator-note:alpha-vantage:idle-24h-2026-10-06",
            now=now,
        )


def test_settlement_moves_reserved_units_to_consumed_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=3))
    _register_summary_policy(monkeypatch, "fixture", policy)
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    reservation = _reserve(policy, {"requests_per_minute": 2}, now=now)
    assert reservation is not None

    settle_provider_quota(reservation, observed_dimension_units={"requests_per_minute": 1}, now=now)
    settle_provider_quota(reservation, observed_dimension_units={"requests_per_minute": 1}, now=now)

    window = provider_quota_coordinator_summary(provider_name="fixture", now=now)["windows"][0]
    assert window["reserved_units"] == 0
    assert window["consumed_units"] == 1
    assert window["remaining_units"] == 2, window


def test_summary_uses_current_marketdata_app_plan_at_expiry(tmp_path, monkeypatch):
    from app.config import provider_rate_limit_seed

    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter_trial")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10_000)
    expiry = datetime(2026, 10, 11, 17, 9, tzinfo=UTC)
    policy_clock = [expiry - timedelta(seconds=1)]
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN_EXPIRES_AT", expiry)
    monkeypatch.setattr("app.config._marketdata_app_policy_now_utc", lambda: policy_clock[0])
    seed = provider_rate_limit_seed("marketdata_app")
    policy = SimpleNamespace(quota_scope=seed["quota_scope"], quota_contract=seed["quota_contract"])
    reconcile_provider_quota_baseline(
        provider_name="marketdata_app",
        capability="price_history",
        policy=policy,
        dimension_name="credits_per_day",
        used_units=99,
        observed_at=policy_clock[0],
        evidence_reference="account-usage:marketdata-app:2026-10-11",
        now=policy_clock[0],
    )
    reservation = reserve_provider_quota(
        provider_name="marketdata_app",
        capability="price_history",
        operation="get_current_price",
        policy=policy,
        dimension_units={"credits_per_day": 1, "concurrent_requests": 0},
        now=policy_clock[0],
    )
    assert reservation is not None

    before = provider_quota_coordinator_summary(provider_name="marketdata_app", now=policy_clock[0])
    before_baseline = next(
        row for row in before["baselines"] if row["dimension"] == "credits_per_day"
    )
    assert before_baseline["limit_units"] == 10_000
    assert before_baseline["remaining_units"] == 9_900

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "free_forever")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 100)
    plan_changed = provider_quota_coordinator_summary(
        provider_name="marketdata_app", now=policy_clock[0]
    )
    changed_baseline = next(
        row for row in plan_changed["baselines"] if row["dimension"] == "credits_per_day"
    )
    assert changed_baseline["limit_units"] == 100
    assert changed_baseline["remaining_units"] == 0

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter_trial")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10_000)

    policy_clock[0] = expiry
    after = provider_quota_coordinator_summary(provider_name="marketdata_app", now=expiry)
    after_baseline = next(
        row for row in after["baselines"] if row["dimension"] == "credits_per_day"
    )
    after_window = next(row for row in after["windows"] if row["dimension"] == "credits_per_day")
    assert after_baseline["limit_units"] == 100
    assert after_baseline["recorded_limit_units"] == 10_000
    assert after_baseline["remaining_units"] == 0
    assert after_window["limit_units"] == 100
    assert after_window["recorded_limit_units"] == 10_000
    assert after_window["remaining_units"] == 0


def test_concurrent_settlement_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=3))
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    reservation = _reserve(policy, {"requests_per_minute": 1}, now=now)
    assert reservation is not None

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                settle_provider_quota,
                reservation,
                observed_dimension_units={"requests_per_minute": 1},
                now=now,
            )
            for _ in range(2)
        ]
        for future in futures:
            future.result()

    window = provider_quota_coordinator_summary(provider_name="fixture", now=now)["windows"][0]
    assert window["reserved_units"] == 0
    assert window["consumed_units"] == 1


def test_multidimensional_admission_is_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(
        _dimension("requests_per_minute", limit=3),
        _dimension("credits_per_day", limit=1, unit="credits"),
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    _seed_test_baseline(policy, now=now)

    first = _reserve(
        policy,
        {"requests_per_minute": 1, "credits_per_day": 1},
        now=now,
    )
    assert first is not None
    second = _reserve(
        policy,
        {"requests_per_minute": 1, "credits_per_day": 1},
        now=now,
    )
    assert second is None

    windows = provider_quota_coordinator_summary(provider_name="fixture", now=now)["windows"]
    assert {row["dimension"]: row["reserved_units"] for row in windows} == {
        "requests_per_minute": 1,
        "credits_per_day": 1,
    }


def test_ambiguous_request_remains_reserved_until_provider_reset(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=1))
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    reservation = _reserve(policy, {"requests_per_minute": 1}, now=now)
    assert reservation is not None

    settle_provider_quota(
        reservation,
        unknown_dimensions={"requests_per_minute"},
        now=now,
    )

    assert _reserve(policy, {"requests_per_minute": 1}, now=now) is None
    next_window = now + timedelta(seconds=60)
    assert _reserve(policy, {"requests_per_minute": 1}, now=next_window) is not None


def test_distinct_identity_pool_is_hashed_and_account_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_ACCOUNT_SCOPES", {"fixture": "acct-one"})
    policy = _policy(
        _dimension("unique_symbols_per_month", limit=1, unit="unique_symbols"),
        reset="calendar_month_utc",
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    assert _reserve(policy, {"unique_symbols_per_month": 1}, now=now, identity="AAPL")
    # The provider meters the monthly symbol set, not repeated reads.
    assert _reserve(policy, {"unique_symbols_per_month": 1}, now=now, identity="AAPL")
    assert _reserve(policy, {"unique_symbols_per_month": 1}, now=now, identity="MSFT") is None

    monkeypatch.setattr(settings, "PROVIDER_QUOTA_ACCOUNT_SCOPES", {"fixture": "acct-two"})
    assert _reserve(policy, {"unique_symbols_per_month": 1}, now=now, identity="MSFT")
    assert account_scope_for_provider("fixture", "ip") == "fixture:shared-ip"


def test_rolling_dimensions_use_their_own_account_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"fixture": "key-scope", "fixture:ip": "shared-egress"},
    )
    policy = _policy(
        _dimension("requests_per_day", limit=10, window_seconds=86400),
        _dimension("ip_requests_rolling", limit=1, window_seconds=60, scope="ip"),
        reset="rolling",
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    assert _reserve(
        policy,
        {"requests_per_day": 1, "ip_requests_rolling": 1},
        now=now,
    )
    assert (
        _reserve(
            policy,
            {"requests_per_day": 1, "ip_requests_rolling": 1},
            now=now + timedelta(seconds=1),
        )
        is None
    )


def test_shared_ip_account_pool_is_not_split_by_provider_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    # FINRA Query API and the OTC adapter use the same FINRA host/egress IP.
    policy = _policy(_dimension(limit=1, scope="ip", quota_group="ip"), scope="ip")
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    assert account_scope_for_provider("finra", "ip") == account_scope_for_provider(
        "finra_otc_directory", "ip"
    )
    assert _reserve(policy, {"requests_per_minute": 1}, now=now, provider="finra")
    assert (
        _reserve(
            policy,
            {"requests_per_minute": 1},
            now=now,
            provider="finra_otc_directory",
        )
        is None
    )

    assert account_scope_for_provider("kraken", "ip") == account_scope_for_provider(
        "kraken_xstocks", "ip"
    )
    assert _reserve(policy, {"requests_per_minute": 1}, now=now, provider="kraken")
    assert (
        _reserve(
            policy,
            {"requests_per_minute": 1},
            now=now,
            provider="kraken_xstocks",
        )
        is None
    )


def test_finra_public_credential_bandwidth_pool_is_shared_between_adapters(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(
        _dimension(
            "download_bytes_per_calendar_month",
            limit=10,
            window_seconds=2678400,
            unit="bytes",
            scope="public_credential",
            quota_group="public_credential",
        ),
        scope="public_credential",
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    assert account_scope_for_provider("finra", "public_credential") == account_scope_for_provider(
        "finra_otc_directory", "public_credential"
    )
    assert _reserve(
        policy,
        {"download_bytes_per_calendar_month": 6},
        now=now,
        provider="finra",
    )
    assert (
        _reserve(
            policy,
            {"download_bytes_per_calendar_month": 5},
            now=now,
            provider="finra_otc_directory",
        )
        is None
    )


def test_rolling_distinct_identity_claims_count_once_for_full_active_window(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(
        _dimension(
            "unique_symbols_per_rolling_window",
            limit=1,
            window_seconds=2678400,
            unit="unique_symbols",
            quota_group="api_key",
        ),
        reset="rolling",
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    first = _reserve(
        policy,
        {"unique_symbols_per_rolling_window": 1},
        now=now,
        identity="AAPL",
    )
    assert first is not None
    settle_provider_quota(
        first,
        observed_dimension_units={"unique_symbols_per_rolling_window": 1},
        now=now,
    )
    # Repeated reads of one symbol do not count as a second unique identity.
    assert _reserve(
        policy,
        {"unique_symbols_per_rolling_window": 1},
        now=now + timedelta(seconds=1),
        identity="AAPL",
    )
    # A different symbol is still denied until the oldest distinct claim ages
    # out of the complete 31-day rolling window.
    assert (
        _reserve(
            policy,
            {"unique_symbols_per_rolling_window": 1},
            now=now + timedelta(seconds=2),
            identity="MSFT",
        )
        is None
    )
    # The denied new rolling identity must not leave an empty quota window.
    assert len(provider_quota_coordinator_summary(now=now + timedelta(seconds=2))["windows"]) == 1
    assert _reserve(
        policy,
        {"unique_symbols_per_rolling_window": 1},
        # The un-settled duplicate-identity reservation at t+1s is still in
        # the active rolling window at the exact inclusive boundary. Move
        # beyond that boundary before establishing the next fixture baseline.
        now=now + timedelta(days=31, seconds=2),
        identity="MSFT",
    )


def test_denied_rolling_reservation_does_not_persist_an_orphan_window(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension("rolling_requests", limit=1), reset="rolling")
    first_at = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    assert _reserve(policy, {"rolling_requests": 1}, now=first_at)
    assert (
        _reserve(
            policy,
            {"rolling_requests": 1},
            now=first_at + timedelta(seconds=1),
        )
        is None
    )
    assert len(provider_quota_coordinator_summary(now=first_at)["windows"]) == 1


def test_github_persistent_store_requirement_applies_only_when_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")
    monkeypatch.setattr(
        settings,
        "PROVIDER_RATE_LIMIT_SEEDS",
        {
            "alpha_vantage": {
                "quota_contract": {
                    "reset": "calendar_day_utc",
                    "dimensions": [
                        {
                            "name": "requests_per_day",
                            "limit": 5,
                            "window_seconds": 86400,
                            "unit": "requests",
                            "scope": "api_key",
                            "quota_group": "account",
                            "source": "unit-test provider contract",
                        }
                    ],
                },
                "quota_scope": "api_key",
                "quota_source": "unit-test provider contract",
            }
        },
    )
    monkeypatch.setattr(
        settings,
        "PROVIDER_USAGE_PROFILE_SEEDS",
        {"alpha_vantage": {"operation_costs": {"fetch_earnings_calendar": 1}}},
    )

    # Ordinary unit coverage uses isolated SQLite even though Actions sets its
    # global environment marker; only the actual live wrapper opts into PG.
    _seed_live_test_baseline("alpha_vantage")
    assert reserve_live_provider_operation("alpha_vantage", "fetch_earnings_calendar") is not None
    with pytest.raises(ProviderQuotaCoordinatorError, match="persistent PostgreSQL"):
        reserve_live_provider_operation(
            "alpha_vantage",
            "fetch_earnings_calendar",
            require_persistent_coordinator=True,
        )


def test_only_supported_coordinator_dialects_are_accepted():
    with pytest.raises(ProviderQuotaCoordinatorError, match="SQLite or PostgreSQL"):
        _validate_engine_url("mysql+pymysql://host/database")


def test_private_sqlite_initialization_does_not_require_redundant_chmod(tmp_path, monkeypatch):
    """An owner-only file remains usable when the filesystem denies chmod."""

    path = tmp_path / "quota.sqlite3"
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(path))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")

    def deny_chmod(*_args, **_kwargs):
        raise PermissionError("chmod denied by sandbox")

    monkeypatch.setattr("app.services.provider_quota_coordinator.os.chmod", deny_chmod)
    engine = _engine_for(f"sqlite:///{path}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    assert path.stat().st_mode & 0o777 == 0o600


def test_coordinator_health_probe_commits_write_and_lock_round_trip(tmp_path, monkeypatch):
    path = tmp_path / "quota.sqlite3"
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(path))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")

    ensure_provider_quota_coordinator()

    engine = _engine_for(f"sqlite:///{path}")
    with engine.connect() as connection:
        value = connection.exec_driver_sql(
            "SELECT last_run_at FROM provider_quota_ledger_maintenance "
            "WHERE key = 'health-probe-v1'"
        ).scalar_one_or_none()
    assert value is not None


def test_coordinator_health_probe_explains_read_only_sqlite_failure(monkeypatch):
    @contextmanager
    def readonly_transaction(_engine):
        raise OperationalError(
            "INSERT INTO provider_quota_ledger_maintenance",
            {},
            Exception("attempt to write a readonly database"),
        )
        yield  # pragma: no cover

    monkeypatch.setattr(
        "app.services.provider_quota_coordinator._write_transaction",
        readonly_transaction,
    )

    with pytest.raises(ProviderQuotaCoordinatorError, match="ledger is read-only"):
        ensure_provider_quota_coordinator()


def test_settled_live_receipt_is_idempotent_and_does_not_double_count(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=5))
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    reservation = _reserve(policy, {"requests_per_minute": 1}, now=now)
    assert reservation is not None
    settle_provider_quota(reservation, observed_dimension_units={"requests_per_minute": 1}, now=now)

    assert (
        register_live_receipt_reservation(
            reservation,
            run_id="live-run-1",
            usage_scope="github:test:staging",
            receipt_status="observed",
            now=now,
        )
        == "reconciled"
    )
    assert reconcile_live_receipt_reservation(reservation.reservation_id) == "reconciled"
    assert reconcile_pending_live_receipts() == {"scanned": 0, "reconciled": 0, "unresolved": 0}
    summary = provider_quota_coordinator_summary(provider_name="fixture", now=now)
    window = summary["windows"][0]
    assert window["consumed_units"] == 1
    assert window["reserved_units"] == 0
    assert summary["live_receipts"] == {
        "total": 1,
        "reconciled": 1,
        "pending": 0,
        "uncertain": 0,
        "unresolved": 0,
    }


def test_robinhood_tokens_provider_slug_is_valid_for_live_receipts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=5))
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    reservation = _reserve(policy, {"requests_per_minute": 1}, now=now, provider="robinhood_tokens")
    assert reservation is not None
    settle_provider_quota(reservation, observed_dimension_units={"requests_per_minute": 1}, now=now)

    assert _validated_live_receipt_provider("robinhood_tokens") == "robinhood_tokens"
    assert (
        register_live_receipt_reservation(
            reservation,
            run_id="robinhood-live-run",
            usage_scope="local:robinhood",
            receipt_status="observed",
            now=now,
        )
        == "reconciled"
    )


@pytest.mark.parametrize("provider", ["Robinhood", "robinhood tokens", "https://example.test"])
def test_live_receipt_provider_must_remain_a_safe_slug(provider):
    with pytest.raises(ProviderQuotaCoordinatorError, match="live receipt provider is invalid"):
        _validated_live_receipt_provider(provider)


def test_archive_failure_live_receipt_is_durably_recordable(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=5))
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    reservation = _reserve(policy, {"requests_per_minute": 1}, now=now)
    assert reservation is not None
    settle_provider_quota(reservation, observed_dimension_units={"requests_per_minute": 1}, now=now)

    assert (
        register_live_receipt_reservation(
            reservation,
            run_id="live-archive-failure",
            usage_scope="local:test",
            receipt_status="archive_failure",
            now=now,
        )
        == "reconciled"
    )
    summary = provider_quota_coordinator_summary(provider_name="fixture", now=now)
    assert summary["live_receipts"]["total"] == 1
    assert summary["live_receipts"]["reconciled"] == 1


def test_pending_live_receipt_recovery_settles_original_reservation_once(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=5))
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    reservation = _reserve(policy, {"requests_per_minute": 2}, now=now)
    assert reservation is not None
    assert (
        register_live_receipt_reservation(
            reservation,
            run_id="live-run-2",
            usage_scope="github:test:staging",
            receipt_status="provider_error",
            now=now,
        )
        == "pending"
    )

    assert reconcile_pending_live_receipts() == {"scanned": 1, "reconciled": 1, "unresolved": 0}
    assert reconcile_pending_live_receipts() == {"scanned": 0, "reconciled": 0, "unresolved": 0}
    summary = provider_quota_coordinator_summary(provider_name="fixture", now=now)
    window = summary["windows"][0]
    assert window["consumed_units"] == 2
    assert window["reserved_units"] == 0
    assert summary["live_receipts"]["reconciled"] == 1


def test_live_receipt_identity_mismatch_and_unknown_id_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=5))
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    reservation = _reserve(policy, {"requests_per_minute": 1}, now=now)
    assert reservation is not None
    with pytest.raises(ProviderQuotaCoordinatorError, match="not registered"):
        reconcile_live_receipt_reservation("00000000-0000-0000-0000-000000000000")
    settle_provider_quota(reservation, observed_dimension_units={"requests_per_minute": 1}, now=now)
    register_live_receipt_reservation(
        reservation,
        run_id="live-run-3",
        usage_scope="github:test:staging",
        receipt_status="observed",
        now=now,
    )
    with pytest.raises(ProviderQuotaCoordinatorError, match="conflicts"):
        register_live_receipt_reservation(
            reservation,
            run_id="different-run",
            usage_scope="github:test:staging",
            receipt_status="observed",
            now=now,
        )


def test_live_probe_settlement_uses_observed_http_and_byte_usage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(
        settings,
        "PROVIDER_RATE_LIMIT_SEEDS",
        {
            "alpha_vantage": {
                "quota_contract": {
                    "reset": "rolling",
                    "dimensions": [
                        {
                            "name": "requests_rolling",
                            "limit": 10,
                            "window_seconds": 60,
                            "unit": "requests",
                            "scope": "api_key",
                            "quota_group": "account",
                            "source": "unit-test provider contract",
                        },
                        {
                            "name": "response_bytes_rolling",
                            "limit": 10000,
                            "window_seconds": 86400,
                            "unit": "bytes",
                            "scope": "api_key",
                            "quota_group": "account",
                            "source": "unit-test byte budget",
                        },
                    ],
                },
                "quota_scope": "api_key",
                "quota_source": "unit-test provider contract",
            }
        },
    )
    monkeypatch.setattr(
        settings,
        "PROVIDER_USAGE_PROFILE_SEEDS",
        {
            "alpha_vantage": {
                "operation_costs": {"fetch_earnings_calendar": 3},
                "dimension_costs": {"response_bytes_rolling": {"fetch_earnings_calendar": 1000}},
            }
        },
    )

    _seed_live_test_baseline("alpha_vantage")
    reservation = reserve_live_provider_operation("alpha_vantage", "fetch_earnings_calendar")
    assert reservation is not None
    settle_live_provider_operation(reservation, http_requests=2, response_bytes=321)

    windows = {
        row["dimension"]: row
        for row in provider_quota_coordinator_summary(provider_name="alpha_vantage")["windows"]
    }
    assert windows["requests_rolling"]["reserved_units"] == 0
    assert windows["requests_rolling"]["consumed_units"] == 2
    assert windows["response_bytes_rolling"]["reserved_units"] == 0
    assert windows["response_bytes_rolling"]["consumed_units"] == 321


def test_eodhd_live_probe_settlement_keeps_provider_credits_separate_from_http_count(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")
    # This fixture exercises settlement mechanics, so provide an explicit
    # reviewed test contract for the otherwise fail-closed EODHD minute pool.
    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_LIMIT", 20)
    monkeypatch.setattr(settings, "EODHD_REVIEWED_MINUTE_RESET", "rolling")
    monkeypatch.setattr(
        settings,
        "EODHD_MINUTE_QUOTA_EVIDENCE",
        "unit-test:eodhd-reviewed-minute-pool",
    )

    _seed_live_test_baseline("eodhd")
    reservation = reserve_live_provider_operation("eodhd", "get_instrument_profile")
    assert reservation is not None
    pending = {
        row["dimension"]: row
        for row in provider_quota_coordinator_summary(provider_name="eodhd")["windows"]
    }
    assert pending["requests_per_minute"]["reserved_units"] == 1
    assert pending["calls_per_day"]["reserved_units"] == 10

    # A valid-key entitlement 403 consumes the minute request, but the native
    # /user counter proved it does not consume weighted daily call credits.
    settle_live_provider_operation(
        reservation,
        http_requests=1,
        response_bytes=128,
        response_status_code=403,
    )
    settled = {
        row["dimension"]: row
        for row in provider_quota_coordinator_summary(provider_name="eodhd")["windows"]
    }
    assert settled["requests_per_minute"]["reserved_units"] == 0
    assert settled["requests_per_minute"]["consumed_units"] == 1
    assert settled["calls_per_day"]["reserved_units"] == 0
    assert settled["calls_per_day"]["consumed_units"] == 0

    paid_entitlement_reservation = reserve_live_provider_operation(
        "eodhd", "get_instrument_profile"
    )
    assert paid_entitlement_reservation is not None
    settle_live_provider_operation(
        paid_entitlement_reservation,
        http_requests=1,
        response_bytes=256,
        response_status_code=200,
    )
    final_windows = provider_quota_coordinator_summary(provider_name="eodhd")["windows"]
    # Rolling windows are recorded from each reservation's own observation
    # timestamp, so requests crossing a one-second boundary can occupy two
    # adjacent ledger rows. The summary intentionally preserves those rows;
    # assert the active minute's total rather than whichever row sorts last.
    assert (
        sum(
            row["consumed_units"]
            for row in final_windows
            if row["dimension"] == "requests_per_minute"
        )
        == 2
    )
    daily_call_windows = [row for row in final_windows if row["dimension"] == "calls_per_day"]
    assert len(daily_call_windows) == 1
    assert daily_call_windows[0]["consumed_units"] == 10


def test_marketstack_live_api_error_does_not_debit_monthly_allowance(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")
    _seed_live_test_baseline("marketstack")

    reservation = reserve_live_provider_operation(
        "marketstack", "get_current_price", operation_cost_override=1
    )
    assert reservation is not None
    settle_live_provider_operation(
        reservation,
        http_requests=1,
        response_bytes=128,
        response_status_code=403,
    )

    windows = {
        row["dimension"]: row
        for row in provider_quota_coordinator_summary(provider_name="marketstack")["windows"]
    }
    assert windows["requests_per_month"]["reserved_units"] == 0
    assert windows["requests_per_month"]["consumed_units"] == 0
    assert windows["requests_per_second"]["reserved_units"] == 0
    assert windows["requests_per_second"]["consumed_units"] == 1

    # Success charges the monthly unit normally, proving the exception rule
    # does not release a legitimate debit or the separate rate-limit window.
    successful = reserve_live_provider_operation(
        "marketstack", "get_current_price", operation_cost_override=1
    )
    assert successful is not None
    settle_live_provider_operation(
        successful,
        http_requests=1,
        response_bytes=256,
        response_status_code=200,
    )
    final_windows = provider_quota_coordinator_summary(provider_name="marketstack")["windows"]
    monthly = [row for row in final_windows if row["dimension"] == "requests_per_month"]
    # The strict 30-day safety envelope is rolling, so each reservation may
    # occupy its own timestamped ledger row. Assert the aggregate allowance
    # usage instead of assuming calendar-month bucket coalescing.
    assert sum(row["consumed_units"] for row in monthly) == 1
    assert sum(row["reserved_units"] for row in monthly) == 0
    assert (
        sum(
            row["consumed_units"]
            for row in final_windows
            if row["dimension"] == "requests_per_second"
        )
        == 2
    )


def test_empty_dimension_cost_map_is_an_explicit_zero_cost_exclusion(monkeypatch):
    """A reviewed empty map must not be mistaken for an unknown cost."""

    from app.config import settings

    monkeypatch.setattr(
        settings,
        "PROVIDER_RATE_LIMIT_SEEDS",
        {
            "fixture": {
                "quota_contract": {
                    "reset": "rolling",
                    "dimensions": [
                        {
                            "name": "requests_per_minute",
                            "limit": 10,
                            "window_seconds": 60,
                            "unit": "requests",
                            "scope": "account",
                            "quota_group": "account",
                        },
                        {
                            "name": "async_requests_per_minute",
                            "limit": 5,
                            "window_seconds": 60,
                            "unit": "requests",
                            "scope": "account",
                            "quota_group": "account",
                        },
                        {
                            "name": "credits_per_day",
                            "limit": 100,
                            "window_seconds": 86400,
                            "unit": "credits",
                            "scope": "account",
                            "quota_group": "account",
                        },
                    ],
                },
                "quota_scope": "account",
            }
        },
    )
    monkeypatch.setattr(
        settings,
        "PROVIDER_USAGE_PROFILE_SEEDS",
        {
            "fixture": {
                "operation_costs": {"fetch_rows": 1},
                "dimension_costs": {
                    "async_requests_per_minute": {},
                    "credits_per_day": {"fetch_rows": {}},
                },
            }
        },
    )

    _reset, dimension_units, specs = _reservation_plan_for_live_probe(
        "fixture", "fetch_rows", "identity", datetime.now(UTC)
    )

    assert dimension_units == {"requests_per_minute": 1}
    assert [spec["dimension"] for spec in specs] == ["requests_per_minute"]
    # A partial map is allowed to carry a provider-specific zero-cost
    # exception while ordinary operations continue to use their reviewed
    # operation cost when the contract does not require maps for every
    # dimension/operation pair.
    monkeypatch.setattr(
        settings,
        "PROVIDER_USAGE_PROFILE_SEEDS",
        {
            "fixture": {
                "operation_costs": {"fetch_other": 1},
                "dimension_costs": {
                    "async_requests_per_minute": {},
                    "credits_per_day": {"fetch_rows": {}},
                },
            }
        },
    )
    _reset, other_units, other_specs = _reservation_plan_for_live_probe(
        "fixture", "fetch_other", "identity", datetime.now(UTC)
    )
    assert other_units == {"requests_per_minute": 1, "credits_per_day": 1}
    assert [spec["dimension"] for spec in other_specs] == [
        "requests_per_minute",
        "credits_per_day",
    ]

    monkeypatch.setattr(
        settings,
        "PROVIDER_USAGE_PROFILE_SEEDS",
        {
            "fixture": {
                "operation_costs": {"fetch_bad": 1},
                "dimension_costs": {
                    "async_requests_per_minute": {},
                    "credits_per_day": {"fetch_bad": 0},
                },
            }
        },
    )
    with pytest.raises(ProviderQuotaAdmissionError, match="dimension cost is unreviewed"):
        _reservation_plan_for_live_probe("fixture", "fetch_bad", "identity", datetime.now(UTC))


def test_live_probe_explicit_zero_dimension_override_is_a_reviewed_exclusion(monkeypatch):
    """A named zero override excludes only that independent provider pool."""

    monkeypatch.setattr(
        settings,
        "PROVIDER_RATE_LIMIT_SEEDS",
        {
            "fixture": {
                "quota_contract": {
                    "reset": "rolling",
                    "dimensions": [
                        {
                            "name": "sync_requests_per_minute",
                            "limit": 10,
                            "window_seconds": 60,
                            "unit": "requests",
                            "scope": "account",
                            "quota_group": "sync",
                        },
                        {
                            "name": "async_requests_per_minute",
                            "limit": 5,
                            "window_seconds": 60,
                            "unit": "requests",
                            "scope": "account",
                            "quota_group": "async",
                        },
                    ],
                },
                "quota_scope": "account",
            }
        },
    )
    monkeypatch.setattr(
        settings,
        "PROVIDER_USAGE_PROFILE_SEEDS",
        {"fixture": {"operation_costs": {"fetch_rows": 1}}},
    )

    _reset, dimension_units, specs = _reservation_plan_for_live_probe(
        "fixture",
        "fetch_rows",
        None,
        datetime.now(UTC),
        dimension_cost_overrides={"async_requests_per_minute": 0},
    )

    assert dimension_units == {"sync_requests_per_minute": 1}
    assert [spec["dimension"] for spec in specs] == ["sync_requests_per_minute"]


def test_sqlite_reservations_are_atomic_across_processes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")
    # Baseline reconciliation is intentionally not allowed while another
    # reservation is pending. Seed the shared baseline before the concurrent
    # reservation race so this test exercises atomic admission rather than
    # racing two independent baseline initializers.
    _seed_test_baseline(
        _policy(_dimension(limit=1)),
        now=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
    )
    context = get_context("spawn")
    barrier = context.Barrier(2)
    outcomes_queue = context.Queue()

    # Separate processes verify the OS-backed lock/transaction path.
    processes = [
        context.Process(
            target=_reserve_once_in_process,
            args=(str(tmp_path / "quota.sqlite3"), barrier, outcomes_queue),
        )
        for _ in range(2)
    ]
    for process in processes:
        process.start()
    outcomes = [outcomes_queue.get(timeout=30) for _ in processes]
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    assert all(item[0] == "ok" for item in outcomes), outcomes
    assert sorted(result for _, result in outcomes) == [False, True]


def test_live_account_usage_bootstrap_excludes_only_native_reconciled_pools(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(
        settings,
        "PROVIDER_RATE_LIMIT_SEEDS",
        {
            "fixture": {
                "quota_contract": {
                    "reset": "per_dimension",
                    "account_usage_bootstrap": {
                        "enabled": True,
                        "source": "unit-test provider contract",
                        "reconciled_dimensions": ["credits_per_day"],
                        "allowed_unknown_dimensions": ["provider_minute_pool"],
                    },
                    "unknown_dimensions": ["provider_minute_pool"],
                    "dimensions": [
                        {
                            "name": "provider_minute_pool",
                            "limit": 20,
                            "window_seconds": 60,
                            "unit": "requests",
                            "scope": "api_key",
                            "quota_group": "api_key",
                            "source": "unit-test provider contract",
                            "reset": "rolling",
                        },
                        {
                            "name": "credits_per_day",
                            "limit": 100,
                            "window_seconds": 86400,
                            "unit": "credits",
                            "scope": "api_key",
                            "quota_group": "api_key",
                            "source": "unit-test provider contract",
                        },
                        {
                            "name": "account_usage_probe_concurrency",
                            "limit": 1,
                            "window_seconds": 1,
                            "unit": "concurrent_requests",
                            "scope": "deployment",
                            "quota_group": "account_usage_probe",
                            "source": "application_policy:provider_native_baseline_bootstrap",
                            "reset": "rolling",
                            "applies_to_operations": ["fetch_account_usage"],
                        },
                    ],
                },
                "quota_scope": "api_key",
            }
        },
    )
    monkeypatch.setattr(
        settings,
        "PROVIDER_USAGE_PROFILE_SEEDS",
        {"fixture": {"operation_costs": {"fetch_account_usage": 1}}},
    )

    with pytest.raises(ProviderQuotaAdmissionError, match="cannot safely charge unreported"):
        _reservation_plan_for_live_probe(
            "fixture", "fetch_account_usage", "identity", datetime.now(UTC)
        )

    # Once the unreported pool is removed, the unknown daily pool can be
    # omitted only because this fixture's native response explicitly maps it.
    contract = settings.PROVIDER_RATE_LIMIT_SEEDS["fixture"]["quota_contract"]
    contract["unknown_dimensions"] = []
    contract["account_usage_bootstrap"]["allowed_unknown_dimensions"] = []
    contract["dimensions"] = [
        dimension
        for dimension in contract["dimensions"]
        if dimension["name"] != "provider_minute_pool"
    ]
    _reset, dimension_units, specs = _reservation_plan_for_live_probe(
        "fixture", "fetch_account_usage", "identity", datetime.now(UTC)
    )
    assert dimension_units == {"account_usage_probe_concurrency": 1}
    assert [spec["dimension"] for spec in specs] == ["account_usage_probe_concurrency"]

    contract["account_usage_bootstrap"]["reconciled_dimensions"] = []
    with pytest.raises(ProviderQuotaAdmissionError, match="bootstrap mapping"):
        _reservation_plan_for_live_probe(
            "fixture", "fetch_account_usage", "identity", datetime.now(UTC)
        )


def test_live_probe_operation_cost_comes_from_provider_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(
        settings,
        "PROVIDER_RATE_LIMIT_SEEDS",
        {
            "alpha_vantage": {
                "quota_contract": {
                    "reset": "calendar_day_utc",
                    "dimensions": [
                        {
                            "name": "requests_per_day",
                            "limit": 5,
                            "window_seconds": 86400,
                            "unit": "requests",
                            "scope": "api_key",
                            "quota_group": "account",
                            "source": "unit-test provider contract",
                        }
                    ],
                },
                "quota_scope": "api_key",
                "quota_source": "unit-test provider contract",
            }
        },
    )
    monkeypatch.setattr(
        settings,
        "PROVIDER_USAGE_PROFILE_SEEDS",
        {"alpha_vantage": {"operation_costs": {"fetch_earnings_calendar": 3}}},
    )
    from app.services.provider_quota_coordinator import reserve_live_provider_operation

    _seed_live_test_baseline("alpha_vantage")
    reservation = reserve_live_provider_operation("alpha_vantage", "fetch_earnings_calendar")
    assert reservation is not None
    # Direct probes and application routing reserve the same account bucket.
    seed = settings.PROVIDER_RATE_LIMIT_SEEDS["alpha_vantage"]
    policy = _policy(
        *seed["quota_contract"]["dimensions"],
        reset=seed["quota_contract"]["reset"],
        scope=seed["quota_scope"],
    )
    assert (
        _reserve(
            policy,
            {"requests_per_day": 3},
            now=datetime.now(UTC),
            provider="alpha_vantage",
            operation="fetch_earnings_calendar",
        )
        is None
    )
    window = provider_quota_coordinator_summary(provider_name="alpha_vantage")["windows"][0]
    assert window["reserved_units"] == 3

    with pytest.raises(ProviderQuotaAdmissionError, match="operation cost is unreviewed"):
        reserve_live_provider_operation("alpha_vantage", "unknown_unbounded_live_operation")


def test_live_probe_refuses_untracked_provider_bandwidth(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(
        settings,
        "PROVIDER_RATE_LIMIT_SEEDS",
        {
            "tiingo": {
                "quota_scope": "api_key",
                "quota_contract": {
                    "reset": "rolling",
                    "dimensions": [
                        {
                            "name": "requests_per_day",
                            "limit": 1000,
                            "window_seconds": 86400,
                            "unit": "requests",
                            "scope": "api_key",
                            "source": "unit-test provider contract",
                        }
                    ],
                    "untracked_constraints": [{"name": "bandwidth_bytes_per_month"}],
                },
            }
        },
    )
    monkeypatch.setattr(
        settings,
        "PROVIDER_USAGE_PROFILE_SEEDS",
        {"tiingo": {"operation_costs": {"fetch_ohlcv": 1}}},
    )

    from app.services.provider_quota_coordinator import reserve_live_provider_operation

    with pytest.raises(ProviderQuotaAdmissionError, match="contract remains incomplete"):
        reserve_live_provider_operation("tiingo", "fetch_ohlcv")


def test_not_sent_reservation_releases_monthly_symbol_claim(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(
        _dimension("unique_symbols_per_month", limit=1, unit="unique_symbols"),
        reset="calendar_month_utc",
    )
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    reservation = _reserve(policy, {"unique_symbols_per_month": 1}, now=now, identity="AAPL")
    assert reservation is not None

    settle_provider_quota(
        reservation,
        observed_dimension_units={"unique_symbols_per_month": 0},
        release_identities=True,
        now=now,
    )

    assert (
        _reserve(
            policy,
            {"unique_symbols_per_month": 1},
            now=now,
            identity="AAPL",
        )
        is not None
    )


def test_retention_never_deletes_historical_quota_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_RETENTION_DAYS", 30)
    policy = _policy(_dimension(limit=10))
    old = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    current = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    settled = _reserve(policy, {"requests_per_minute": 1}, now=old)
    uncertain = _reserve(
        policy,
        {"requests_per_minute": 1},
        now=old + timedelta(seconds=61),
    )
    assert settled is not None and uncertain is not None
    settle_provider_quota(
        settled,
        observed_dimension_units={"requests_per_minute": 1},
        now=old,
    )
    settle_provider_quota(
        uncertain,
        unknown_dimensions={"requests_per_minute"},
        now=old + timedelta(seconds=61),
    )

    assert _reserve(policy, {"requests_per_minute": 1}, now=current)
    windows = provider_quota_coordinator_summary(provider_name="fixture", now=current)["windows"]
    assert len(windows) == 3
    settled_window = next(
        row for row in windows if row["window_started_at"].startswith("2026-01-01T12:00:00")
    )
    assert settled_window["reserved_units"] == 0
    assert settled_window["consumed_units"] == 1
    uncertain_window = next(row for row in windows if row["uncertain_reservations"])
    assert uncertain_window["uncertain_reservations"] == 1
    assert uncertain_window["window_started_at"].startswith("2026-01-01T12:01:00")
