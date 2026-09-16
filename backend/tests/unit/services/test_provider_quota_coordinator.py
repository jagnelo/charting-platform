from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from multiprocessing import get_context
from types import SimpleNamespace

import pytest

from app.config import settings
from app.services.provider_quota_coordinator import (
    ProviderQuotaAdmissionError,
    ProviderQuotaCoordinatorError,
    _current_contract_limit,
    _engine_for,
    _reservation_plan_for_live_probe,
    _safe_stored_evidence_reference,
    _validate_engine_url,
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
        reserved = reserve_provider_quota(
            provider_name="fixture",
            capability="price_history",
            operation="fetch_ohlcv",
            policy=policy,
            dimension_units={"requests_per_minute": 1},
            now=datetime(2026, 9, 15, 12, 0, tzinfo=UTC),
        ) is not None
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
    assert reserve_provider_quota(
        provider_name="fixture",
        capability="price_history",
        operation="fetch_ohlcv",
        policy=policy,
        dimension_units={"requests_per_minute": 1},
        now=now,
    ) is None

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
    assert reserve_provider_quota(
        provider_name="fixture",
        capability="price_history",
        operation="fetch_ohlcv",
        policy=policy,
        dimension_units={"requests_per_minute": 1},
        now=now,
    ) is None


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
    assert {
        row["dimension"]: row["consumed_units"] for row in summary["windows"]
    } == {"concurrent_requests": 0}
    assert all(row["dimension"] != "credits_per_day" for row in summary["windows"])


def test_fixed_window_baseline_never_moves_down_on_stale_or_lower_snapshot(
    tmp_path, monkeypatch
):
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


def test_reconciliation_preserves_settled_local_debits_beyond_lower_snapshot(
    tmp_path, monkeypatch
):
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


def test_newer_rolling_snapshot_can_decrease_as_provider_usage_ages_out(
    tmp_path, monkeypatch
):
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
    policy_a = _policy(
        _dimension("requests_per_minute", limit=5, quota_group="shared-account")
    )
    policy_b = _policy(
        _dimension("requests_per_minute", limit=10, quota_group="shared-account")
    )
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
    assert _safe_stored_evidence_reference(
        "dashboard:marketdata-app:2026-10-11"
    ) == "dashboard:marketdata-app:2026-10-11"
    assert (
        _safe_stored_evidence_reference(
            "dashboard:alpaca:AbCdEf0123456789"
        )
        is None
    )
    assert (
        _safe_stored_evidence_reference(
            "dashboard:alpaca:access-token-example"
        )
        is None
    )


def test_existing_private_sqlite_baseline_schema_fails_closed_after_upgrade(
    tmp_path, monkeypatch
):
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


def test_rolling_baseline_expires_only_after_the_full_provider_window(
    tmp_path, monkeypatch
):
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
    assert reserve_provider_quota(
        **arguments,
        now=now + timedelta(seconds=59),
    ) is None
    assert reserve_provider_quota(
        **arguments,
        now=now + timedelta(seconds=61),
    ) is None


def test_settlement_moves_reserved_units_to_consumed_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    policy = _policy(_dimension(limit=3))
    _register_summary_policy(monkeypatch, "fixture", policy)
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)
    reservation = _reserve(policy, {"requests_per_minute": 2}, now=now)
    assert reservation is not None

    settle_provider_quota(
        reservation, observed_dimension_units={"requests_per_minute": 1}, now=now
    )
    settle_provider_quota(
        reservation, observed_dimension_units={"requests_per_minute": 1}, now=now
    )

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
    monkeypatch.setattr(
        "app.config._marketdata_app_policy_now_utc", lambda: policy_clock[0]
    )
    seed = provider_rate_limit_seed("marketdata_app")
    policy = SimpleNamespace(
        quota_scope=seed["quota_scope"], quota_contract=seed["quota_contract"]
    )
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

    before = provider_quota_coordinator_summary(
        provider_name="marketdata_app", now=policy_clock[0]
    )
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
        row
        for row in plan_changed["baselines"]
        if row["dimension"] == "credits_per_day"
    )
    assert changed_baseline["limit_units"] == 100
    assert changed_baseline["remaining_units"] == 0

    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_PLAN", "starter_trial")
    monkeypatch.setattr(settings, "MARKETDATA_APP_REVIEWED_DAILY_CREDIT_LIMIT", 10_000)

    policy_clock[0] = expiry
    after = provider_quota_coordinator_summary(
        provider_name="marketdata_app", now=expiry
    )
    after_baseline = next(
        row for row in after["baselines"] if row["dimension"] == "credits_per_day"
    )
    after_window = next(
        row for row in after["windows"] if row["dimension"] == "credits_per_day"
    )
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
    policy = _policy(_dimension("unique_symbols_per_month", limit=1, unit="unique_symbols"), reset="calendar_month_utc")
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
    assert _reserve(
        policy,
        {"requests_per_day": 1, "ip_requests_rolling": 1},
        now=now + timedelta(seconds=1),
    ) is None


def test_shared_ip_account_pool_is_not_split_by_provider_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    # FINRA Query API and the OTC adapter use the same FINRA host/egress IP.
    policy = _policy(_dimension(limit=1, scope="ip", quota_group="ip"), scope="ip")
    now = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)

    assert account_scope_for_provider("finra", "ip") == account_scope_for_provider(
        "finra_otc_directory", "ip"
    )
    assert _reserve(policy, {"requests_per_minute": 1}, now=now, provider="finra")
    assert _reserve(
        policy,
        {"requests_per_minute": 1},
        now=now,
        provider="finra_otc_directory",
    ) is None


def test_rolling_distinct_identity_claims_count_once_for_full_active_window(
    tmp_path, monkeypatch
):
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
    assert _reserve(
        policy,
        {"unique_symbols_per_rolling_window": 1},
        now=now + timedelta(seconds=2),
        identity="MSFT",
    ) is None
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
    assert _reserve(
        policy,
        {"rolling_requests": 1},
        now=first_at + timedelta(seconds=1),
    ) is None
    assert len(provider_quota_coordinator_summary(now=first_at)["windows"]) == 1


def test_github_persistent_store_requirement_applies_only_when_requested(
    tmp_path, monkeypatch
):
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
    assert reserve_live_provider_operation(
        "alpha_vantage", "fetch_earnings_calendar"
    ) is not None
    with pytest.raises(ProviderQuotaCoordinatorError, match="persistent PostgreSQL"):
        reserve_live_provider_operation(
            "alpha_vantage",
            "fetch_earnings_calendar",
            require_persistent_coordinator=True,
        )


def test_only_supported_coordinator_dialects_are_accepted():
    with pytest.raises(ProviderQuotaCoordinatorError, match="SQLite or PostgreSQL"):
        _validate_engine_url("mysql+pymysql://host/database")


def test_private_sqlite_initialization_does_not_require_redundant_chmod(
    tmp_path, monkeypatch
):
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
                "dimension_costs": {
                    "response_bytes_rolling": {"fetch_earnings_calendar": 1000}
                },
            }
        },
    )

    _seed_live_test_baseline("alpha_vantage")
    reservation = reserve_live_provider_operation(
        "alpha_vantage", "fetch_earnings_calendar"
    )
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

    # The free-plan Fundamentals probe receives one HTTP 403 but is charged
    # ten EODHD credits. Transport count must not overwrite provider pricing.
    settle_live_provider_operation(reservation, http_requests=1, response_bytes=128)
    settled = {
        row["dimension"]: row
        for row in provider_quota_coordinator_summary(provider_name="eodhd")["windows"]
    }
    assert settled["requests_per_minute"]["reserved_units"] == 0
    assert settled["requests_per_minute"]["consumed_units"] == 1
    assert settled["calls_per_day"]["reserved_units"] == 0
    assert settled["calls_per_day"]["consumed_units"] == 10


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
        _reservation_plan_for_live_probe(
            "fixture", "fetch_bad", "identity", datetime.now(UTC)
        )


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


def test_live_account_usage_bootstrap_excludes_only_unknown_pools(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "quota.sqlite3"))
    monkeypatch.setattr(
        settings,
        "PROVIDER_RATE_LIMIT_SEEDS",
        {
            "fixture": {
                "quota_contract": {
                    "reset": "per_dimension",
                    "account_usage_bootstrap": {"enabled": True},
                    "dimensions": [
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

    _reset, dimension_units, specs = _reservation_plan_for_live_probe(
        "fixture", "fetch_account_usage", "identity", datetime.now(UTC)
    )

    assert dimension_units == {"account_usage_probe_concurrency": 1}
    assert [spec["dimension"] for spec in specs] == ["account_usage_probe_concurrency"]


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
    assert _reserve(
        policy,
        {"requests_per_day": 3},
        now=datetime.now(UTC),
        provider="alpha_vantage",
        operation="fetch_earnings_calendar",
    ) is None
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

    assert _reserve(
        policy,
        {"unique_symbols_per_month": 1},
        now=now,
        identity="AAPL",
    ) is not None


def test_retention_prunes_only_old_settled_windows(tmp_path, monkeypatch):
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
    assert len(windows) == 2
    uncertain_window = next(row for row in windows if row["uncertain_reservations"])
    assert uncertain_window["uncertain_reservations"] == 1
    assert uncertain_window["window_started_at"].startswith("2026-01-01T12:01:00")
