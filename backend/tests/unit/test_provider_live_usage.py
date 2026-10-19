from __future__ import annotations

import asyncio
import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from _pytest.outcomes import Exit as PytestExit

from app.config import provider_rate_limit_seed, settings
from app.providers.base import ProviderAccountUsage, ProviderAccountUsageDimension
from app.services.provider_quota_coordinator import (
    provider_quota_baseline_status,
    reconcile_provider_quota_baseline,
)
from tests.live import live_usage
from tests.live import test_tokenized_providers_live as tokenized_live


def test_alpha_vantage_live_probe_paces_rolling_minute_quota(monkeypatch):
    live_usage._reset_for_test()
    ticks = iter((10.0, 10.5, 11.0, 12.0))
    sleeps = []
    monkeypatch.setattr(live_usage.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(live_usage.time, "sleep", sleeps.append)

    assert live_usage.wait_for_provider_start_window("alpha_vantage") == 0.0
    assert live_usage.wait_for_provider_start_window("alpha_vantage") == 12.5
    assert sleeps == [12.5]
    assert live_usage.wait_for_provider_start_window("unmetered_fixture") == 0.0


def test_kraken_live_probe_paces_public_ip_calls(monkeypatch):
    live_usage._reset_for_test()
    now = [20.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(live_usage.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(live_usage.time, "sleep", sleep)

    assert live_usage.wait_for_provider_start_window("kraken") == 0.0
    assert live_usage.wait_for_provider_start_window("kraken") == pytest.approx(1.1)
    assert sleeps == [pytest.approx(1.1)]


def test_massive_live_probe_paces_below_five_requests_per_minute(monkeypatch):
    live_usage._reset_for_test()
    now = [20.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(live_usage.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(live_usage.time, "sleep", sleep)

    assert live_usage.wait_for_provider_start_window("massive") == 0.0
    assert live_usage.wait_for_provider_start_window("massive") == pytest.approx(20.0)
    assert sleeps == [pytest.approx(20.0)]


def test_eodhd_live_usage_reconciliation_uses_exact_native_daily_counter(
    tmp_path: Path, monkeypatch
):
    ledger_path = tmp_path / "provider-quota.sqlite3"
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(ledger_path))
    now = datetime.now(UTC)
    seed = provider_rate_limit_seed("eodhd")
    policy = SimpleNamespace(
        quota_scope=seed["quota_scope"],
        quota_contract=seed["quota_contract"],
    )
    reconcile_provider_quota_baseline(
        provider_name="eodhd",
        capability="account_usage",
        policy=policy,
        dimension_name="calls_per_day",
        used_units=15,
        observed_at=now - timedelta(minutes=5),
        evidence_reference="test-fixture:eodhd:previous-overcount",
        source="provider_account_observation",
        now=now,
    )
    usage = ProviderAccountUsage(
        provider="eodhd",
        observed_at=now,
        unit="calls",
        account_plan="free-20-calls-day",
        dimensions=(
            ProviderAccountUsageDimension(
                name="calls_per_day",
                unit="calls",
                limit=20,
                remaining=15,
                consumed=5,
                reset_at=now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1),
            ),
        ),
    )

    result = live_usage.reconcile_native_account_usage("eodhd", usage)

    assert result[0]["used_units"] == 5
    status = provider_quota_baseline_status(
        provider_name="eodhd",
        capability="account_usage",
        policy=policy,
        dimension_name="calls_per_day",
        now=now,
    )
    assert status["effective_used_units"] == 5
    assert status["remaining_units"] == 15


def test_marketdata_app_current_account_snapshot_replaces_stale_local_overcount(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(
        settings, "PROVIDER_QUOTA_LEDGER_PATH", str(tmp_path / "provider-quota.sqlite3")
    )
    now = datetime.now(UTC)
    seed = provider_rate_limit_seed("marketdata_app")
    policy = SimpleNamespace(
        quota_scope=seed["quota_scope"],
        quota_contract=seed["quota_contract"],
    )
    reconcile_provider_quota_baseline(
        provider_name="marketdata_app",
        capability="account_usage",
        policy=policy,
        dimension_name="credits_per_day",
        used_units=58,
        observed_at=now - timedelta(minutes=5),
        evidence_reference="test-fixture:marketdata-app:previous-counter",
        source="provider_account_observation",
        now=now,
    )
    usage = ProviderAccountUsage(
        provider="marketdata_app",
        observed_at=now,
        unit="credits",
        limit=100,
        remaining=100,
        consumed=0,
        reset_at=now + timedelta(hours=18),
        dimensions=(
            ProviderAccountUsageDimension(
                name="credits_per_day",
                unit="credits",
                limit=100,
                remaining=100,
                consumed=0,
                reset_at=now + timedelta(hours=18),
            ),
        ),
        response_headers={
            "x-api-ratelimit-limit": "100",
            "x-api-ratelimit-remaining": "100",
            "x-api-ratelimit-consumed": "0",
        },
    )

    result = live_usage.reconcile_native_account_usage("marketdata_app", usage)

    assert result[0]["used_units"] == 0
    status = provider_quota_baseline_status(
        provider_name="marketdata_app",
        capability="account_usage",
        policy=policy,
        dimension_name="credits_per_day",
        now=now,
    )
    assert status["effective_used_units"] == 0
    assert status["remaining_units"] == 100


_MERGER_SPEC = importlib.util.spec_from_file_location(
    "merge_provider_live_usage",
    Path(__file__).resolve().parents[3] / "scripts/merge-provider-live-usage.py",
)
assert _MERGER_SPEC and _MERGER_SPEC.loader
_MERGER = importlib.util.module_from_spec(_MERGER_SPEC)
_MERGER_SPEC.loader.exec_module(_MERGER)


def test_live_usage_ledger_aggregates_observed_counts_without_payloads(tmp_path: Path, monkeypatch):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("PROVIDER_LIVE_RUN_ID", "run-test")
    live_usage._reset_for_test()
    live_usage.record_observation(
        "fred",
        operation="fetch_series",
        http_requests=2,
        response_bytes=100,
        response_headers={
            "X-RateLimit-Remaining": "17",
            "X-Api-Ratelimit-Remaining": "87",
            "Total-Records-On-Page": "2",
            "Authorization": "secret",
        },
    )
    live_usage.record_observation(
        "fred", operation="fetch_series", http_requests=1, response_bytes=50
    )
    live_usage.record_observation(
        "coinbase", operation="get_current_price", http_requests=1, response_bytes=25
    )

    assert live_usage.flush_observations(0) == ledger
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert rows == [
        {
            "at": rows[0]["at"],
            "exit_status": 0,
            "failed_operations": 0,
            "http_requests": 1,
            "operations": 1,
            "process_exit_status": 0,
            "provider": "coinbase",
            "response_bytes": 25,
            "run_id": "run-test",
            "response_headers": {},
            "operation_usage": {
                "get_current_price": {
                    "dispositions": {"observed": 1},
                    "failed_operations": 0,
                    "http_requests": 1,
                    "operations": 1,
                    "response_statuses": {},
                    "response_bytes": 25,
                }
            },
            "usage_scope": "unspecified",
        },
        {
            "at": rows[1]["at"],
            "exit_status": 0,
            "failed_operations": 0,
            "http_requests": 3,
            "operations": 2,
            "process_exit_status": 0,
            "provider": "fred",
            "response_bytes": 150,
            "run_id": "run-test",
            "response_headers": {
                "x-api-ratelimit-remaining": "87",
                "x-ratelimit-remaining": "17",
                "total-records-on-page": "2",
            },
            "operation_usage": {
                "fetch_series": {
                    "dispositions": {"observed": 2},
                    "failed_operations": 0,
                    "http_requests": 3,
                    "operations": 2,
                    "response_statuses": {},
                    "response_bytes": 150,
                }
            },
            "usage_scope": "unspecified",
        },
    ]
    assert live_usage.flush_observations(0) is None


def test_dinari_sandbox_canary_process_cap_is_exactly_one(monkeypatch):
    live_usage._reset_for_test()
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_RUN", "1")
    monkeypatch.delenv("DINARI_SANDBOX_CANARY_MAX_REQUESTS", raising=False)
    with pytest.raises(RuntimeError, match="MAX_REQUESTS must be exactly 1"):
        live_usage.reserve_dinari_sandbox_canary_request()

    monkeypatch.setenv("DINARI_SANDBOX_CANARY_MAX_REQUESTS", "1")
    assert live_usage.reserve_dinari_sandbox_canary_request() == 1
    from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError

    with pytest.raises(ProviderQuotaAdmissionError, match="canary request cap exhausted"):
        live_usage.reserve_dinari_sandbox_canary_request()


def test_dinari_canary_receipt_is_explicitly_marked(tmp_path: Path, monkeypatch):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("PROVIDER_LIVE_RUN_ID", "dinari-canary-run")
    monkeypatch.setenv("PROVIDER_LIVE_ADMISSION_MODE", "dinari_sandbox_canary")
    live_usage._reset_for_test()
    live_usage.record_observation(
        "dinari",
        operation="get_tokenized_price",
        http_requests=1,
        response_bytes=12,
    )

    live_usage.flush_observations(0)
    row = json.loads(ledger.read_text(encoding="utf-8").splitlines()[0])
    assert row["admission_mode"] == "dinari_sandbox_canary"


def test_dinari_canary_cap_is_consumed_per_transport_request(monkeypatch):
    import httpx

    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_RUN", "1")
    monkeypatch.setenv("DINARI_SANDBOX_CANARY_MAX_REQUESTS", "1")
    live_usage._reset_for_test()
    live_usage.install_httpx_quota_admission_guard(patcher=monkeypatch)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=b"ok"))
    token = live_usage.activate_request_admission()
    try:
        with httpx.Client(transport=transport) as client:
            assert client.get("https://provider.example.test/one").status_code == 200
            from app.services.provider_quota_coordinator import ProviderQuotaAdmissionError

            with pytest.raises(ProviderQuotaAdmissionError, match="canary request cap exhausted"):
                client.get("https://provider.example.test/three")
    finally:
        live_usage.deactivate_request_admission(token)


def test_dinari_canary_archives_successful_response_payload(monkeypatch):
    from app.services import provider_quota_coordinator

    monkeypatch.setenv("DINARI_SANDBOX_CANARY_RUN", "1")
    measurement = SimpleNamespace(
        http_requests=1,
        response_bytes=7,
        response_payloads=[{"id": "sandbox-stock"}],
        response_metadata=[{"status_code": 200, "headers": {}}],
        response_headers={},
    )
    archived = []
    monkeypatch.setattr(
        provider_quota_coordinator,
        "reserve_live_provider_operation",
        lambda *args, **kwargs: SimpleNamespace(reservation_id="dinari-test-reservation"),
    )
    monkeypatch.setattr(
        provider_quota_coordinator,
        "settle_live_provider_operation",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        tokenized_live,
        "activate_provider_telemetry",
        lambda **kwargs: (measurement, object()),
    )
    monkeypatch.setattr(tokenized_live, "deactivate_provider_telemetry", lambda token: None)
    monkeypatch.setattr(tokenized_live, "activate_request_admission", lambda: object())
    monkeypatch.setattr(tokenized_live, "deactivate_request_admission", lambda token: None)
    monkeypatch.setattr(
        tokenized_live,
        "archive_response_payloads",
        lambda provider, operation, payloads, **kwargs: archived.extend(payloads),
    )
    monkeypatch.setattr(tokenized_live, "record_observation", lambda *args, **kwargs: None)

    result, observed = tokenized_live._observed_read(
        lambda: {"id": "sandbox-stock"}, "dinari", "discover_tokenized_assets"
    )

    assert result == {"id": "sandbox-stock"}
    assert observed is measurement
    assert archived == [{"id": "sandbox-stock"}]


def test_live_usage_tracks_provider_status_separately_from_process_exit(tmp_path, monkeypatch):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("PROVIDER_LIVE_RUN_ID", "mixed-run")
    live_usage._reset_for_test()
    live_usage.record_observation(
        "alpaca",
        operation="get_current_price",
        http_requests=1,
        response_bytes=10,
        success=True,
    )
    live_usage.record_observation(
        "alpha_vantage",
        operation="fetch_ohlcv",
        http_requests=1,
        response_bytes=20,
        success=False,
    )

    assert live_usage.flush_observations(1) == ledger
    rows = {row["provider"]: row for row in map(json.loads, ledger.read_text().splitlines())}
    assert rows["alpaca"]["exit_status"] == 0
    assert rows["alpaca"]["failed_operations"] == 0
    assert rows["alpaca"]["process_exit_status"] == 1
    assert rows["alpha_vantage"]["exit_status"] == 1
    assert rows["alpha_vantage"]["failed_operations"] == 1
    assert rows["alpha_vantage"]["process_exit_status"] == 1


def test_live_usage_correlates_provider_observations_to_exact_pytest_case(tmp_path, monkeypatch):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("PROVIDER_LIVE_RUN_ID", "case-run")
    live_usage._reset_for_test()
    token = live_usage.activate_case(
        "tests/live/test_market_data_providers_live.py::test_alpaca_credentialed_profile"
    )
    try:
        live_usage.record_observation(
            "alpaca",
            operation="get_instrument_profile",
            http_requests=2,
            response_bytes=40,
            response_status_code=200,
        )
    finally:
        live_usage.deactivate_case(token)

    assert live_usage.flush_observations(0) == ledger
    row = json.loads(ledger.read_text())
    case_id = "tests/live/test_market_data_providers_live.py::test_alpaca_credentialed_profile"
    assert row["case_usage"][case_id] == {
        "http_requests": 2,
        "operations": {
            "get_instrument_profile": {
                "dispositions": {"observed": 1},
                "failed_operations": 0,
                "http_requests": 2,
                "response_bytes": 40,
                "response_statuses": {"200": 1},
            }
        },
        "response_bytes": 40,
    }


def test_live_usage_records_expected_entitlement_denial_separately(tmp_path, monkeypatch):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("PROVIDER_LIVE_RUN_ID", "denial-run")
    live_usage._reset_for_test()
    live_usage.record_observation(
        "eodhd",
        operation="get_instrument_profile",
        http_requests=1,
        response_bytes=12,
        success=True,
        disposition="expected_entitlement_denial",
        response_status_code=403,
        case_id="tests/live/test_market_data_providers_live.py::test_eodhd_free_plan_profile_entitlement_is_explicit",
    )

    assert live_usage.flush_observations(0) == ledger
    row = json.loads(ledger.read_text())
    operation = row["operation_usage"]["get_instrument_profile"]
    assert operation["failed_operations"] == 0
    assert operation["dispositions"] == {"expected_entitlement_denial": 1}
    assert operation["response_statuses"] == {"403": 1}


def test_live_matrix_continues_after_an_explicit_expected_entitlement_denial(
    tmp_path, monkeypatch
):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("PROVIDER_LIVE_RUN_ID", "challenge-run")
    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    monkeypatch.setenv("PROVIDER_LIVE_MATRIX_RUN", "1")
    live_usage._reset_for_test()

    assert (
        live_usage.challenge_status_code(
            [{"status_code": 200}, {"status_code": 403}], fallback_status_code=200
        )
        == 403
    )
    live_usage.record_observation(
        "eodhd",
        operation="get_instrument_profile",
        http_requests=1,
        response_bytes=12,
        success=True,
        disposition="expected_entitlement_denial",
        response_status_code=403,
        case_id="tests/live/test_market_data_providers_live.py::"
        "test_eodhd_free_plan_profile_entitlement_is_explicit",
    )

    assert live_usage.flush_observations(0) == ledger
    row = json.loads(ledger.read_text())
    assert row["process_exit_status"] == 0
    assert row["operation_usage"]["get_instrument_profile"]["response_statuses"] == {"403": 1}


@pytest.mark.parametrize("status_code", [401, 403, 429])
def test_live_matrix_stops_after_an_unexpected_access_or_rate_limit_challenge(
    tmp_path, monkeypatch, status_code
):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("PROVIDER_LIVE_RUN_ID", f"challenge-run-{status_code}")
    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    monkeypatch.setenv("PROVIDER_LIVE_MATRIX_RUN", "1")
    live_usage._reset_for_test()

    with pytest.raises(PytestExit, match=f"HTTP {status_code}"):
        live_usage.record_observation(
            "eodhd",
            operation="get_instrument_profile",
            http_requests=1,
            response_bytes=12,
            success=False,
            disposition="provider_error",
            response_status_code=status_code,
            case_id="tests/live/test_market_data_providers_live.py::unexpected_challenge",
        )

    assert live_usage.flush_observations(2) == ledger
    row = json.loads(ledger.read_text())
    assert row["process_exit_status"] == 2
    assert row["operation_usage"]["get_instrument_profile"]["response_statuses"] == {
        str(status_code): 1
    }


def test_live_usage_blank_ledger_override_uses_private_default(monkeypatch):
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", "  ")

    assert live_usage.ledger_path() == live_usage.DEFAULT_LEDGER


def test_live_usage_generates_fresh_uuid_when_run_id_is_not_supplied(tmp_path, monkeypatch):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.delenv("PROVIDER_LIVE_RUN_ID", raising=False)
    live_usage._reset_for_test()
    live_usage.record_observation(
        "fred", operation="fetch_series", http_requests=1, response_bytes=10
    )

    assert live_usage.flush_observations(0) == ledger
    row = json.loads(ledger.read_text())
    generated = UUID(row["run_id"])
    assert str(generated) == row["run_id"]
    assert not row["run_id"].startswith("pid-")


def test_live_usage_preflight_opens_configured_ledger(tmp_path, monkeypatch):
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_SCOPE", "unit-test")

    assert live_usage.ensure_usage_scope_configured() == "unit-test"
    assert live_usage.ensure_ledger_writable() == ledger
    assert ledger.exists()
    assert ledger.read_text() == ""
    assert ledger.stat().st_mode & 0o077 == 0


def test_live_usage_preflight_hardens_existing_ledger(tmp_path, monkeypatch):
    ledger = tmp_path / "provider-live-usage.jsonl"
    ledger.write_text("existing receipt\n")
    ledger.chmod(0o644)
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))

    assert live_usage.ensure_ledger_writable() == ledger
    assert ledger.stat().st_mode & 0o077 == 0
    assert ledger.read_text() == "existing receipt\n"


def test_live_usage_preflight_fails_before_provider_calls_when_ledger_unwritable(
    tmp_path, monkeypatch
):
    parent_file = tmp_path / "not-a-directory"
    parent_file.write_text("blocker")
    ledger = parent_file / "provider-live-usage.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_LEDGER", str(ledger))

    with pytest.raises(RuntimeError, match="ledger is not writable"):
        live_usage.ensure_ledger_writable()


def test_live_response_archive_preflights_private_path_and_preserves_redacted_payloads(
    tmp_path, monkeypatch
):
    archive = tmp_path / "provider-live-responses.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_RESPONSE_ARCHIVE", str(archive))
    monkeypatch.setenv("PROVIDER_LIVE_RUN_ID", "archive-run")
    assert live_usage.ensure_response_archive_writable() == archive
    assert archive.stat().st_mode & 0o077 == 0

    assert (
        live_usage.archive_response_payloads(
            "example",
            "fetch_history",
            [
                {
                    "access_token": "private-token",
                    "rows": [{"symbol": "ABC", "price": 12.5}],
                },
                "complete|raw|CSV",
            ],
            response_bytes=72,
            response_metadata=[
                {"status_code": 200, "headers": {"x-api-ratelimit-remaining": "96"}},
                {"status_code": 200, "headers": {"record-offset": "2"}},
            ],
        )
        == archive
    )
    rows = [json.loads(line) for line in archive.read_text().splitlines()]
    assert [row["payload"] for row in rows] == [
        {"access_token": "<redacted>", "rows": [{"symbol": "ABC", "price": 12.5}]},
        "complete|raw|CSV",
    ]
    assert [row["response_index"] for row in rows] == [0, 1]
    assert [row["response_metadata"] for row in rows] == [
        {"status_code": 200, "headers": {"x-api-ratelimit-remaining": "96"}},
        {"status_code": 200, "headers": {"record-offset": "2"}},
    ]
    assert all(row["response_count"] == 2 for row in rows)
    assert all(row["run_id"] == "archive-run" for row in rows)
    assert archive.stat().st_mode & 0o077 == 0


def test_live_response_archive_preflight_fails_before_provider_calls_when_unwritable(
    tmp_path, monkeypatch
):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("blocker")
    monkeypatch.setenv("PROVIDER_LIVE_RESPONSE_ARCHIVE", str(blocker / "responses.jsonl"))
    with pytest.raises(RuntimeError, match="response archive is not writable"):
        live_usage.ensure_response_archive_writable()


def test_live_response_archive_refuses_symlink_without_touching_target(tmp_path, monkeypatch):
    target = tmp_path / "unrelated.txt"
    target.write_text("leave intact")
    archive = tmp_path / "responses.jsonl"
    archive.symlink_to(target)
    monkeypatch.setenv("PROVIDER_LIVE_RESPONSE_ARCHIVE", str(archive))

    with pytest.raises(RuntimeError, match="response archive is not writable"):
        live_usage.ensure_response_archive_writable()
    with pytest.raises(RuntimeError, match="response archive write failed"):
        live_usage.archive_response_payloads(
            "example", "fetch_history", [{"symbol": "AAPL"}], response_bytes=12
        )
    assert target.read_text() == "leave intact"


def test_live_response_archive_refuses_repository_destination_without_creating_it(monkeypatch):
    repository_root = Path(__file__).resolve().parents[3]
    archive = repository_root / ".ai" / "provider-live-responses-test.jsonl"
    monkeypatch.setenv("PROVIDER_LIVE_RESPONSE_ARCHIVE", str(archive))

    with pytest.raises(RuntimeError, match="must be outside the repository"):
        live_usage.ensure_response_archive_writable()
    assert not archive.exists()


def test_native_account_usage_reconciliation_uses_exact_production_candidate(monkeypatch):
    contract = {
        "dimensions": [
            {
                "name": "credits_per_minute",
                "limit": 8,
                "window_seconds": 60,
                "unit": "credits",
                "scope": "api_key",
            }
        ],
        "reset": "calendar_minute_utc",
    }
    monkeypatch.setattr(
        "app.config.provider_rate_limit_seed",
        lambda _provider: {"quota_contract": contract, "quota_scope": "api_key"},
    )
    monkeypatch.setattr(
        "app.services.provider_account_usage._native_baseline_candidate",
        lambda *_args: (
            "credits_per_minute",
            "account_usage",
            3,
            datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
            "account-usage:test-provider:2026-09-16",
        ),
    )
    calls = []
    monkeypatch.setattr(
        "app.services.provider_quota_coordinator.reconcile_provider_quota_baseline",
        lambda **kwargs: calls.append(kwargs) or {"window_started_at": "2026-09-16T12:00:00+00:00"},
    )

    usage = SimpleNamespace(
        observed_at=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        dimensions=(
            SimpleNamespace(
                name="credits_per_minute",
                unit="credits",
                limit=8,
                remaining=5,
                consumed=3,
                reset_at=datetime(2026, 9, 16, 12, 1, tzinfo=UTC),
            ),
        ),
    )
    result = live_usage.reconcile_native_account_usage("test_provider", usage)

    assert result == [
        {
            "status": "reconciled",
            "dimension": "credits_per_minute",
            "used_units": 3,
            "window_started_at": "2026-09-16T12:00:00+00:00",
        }
    ]
    assert calls[0]["source"] == "provider_account_observation"
    assert calls[0]["evidence_reference"] == "account-usage:test-provider:2026-09-16"


def test_native_account_usage_reconciliation_keeps_unproven_snapshot_observational(
    monkeypatch,
):
    contract = {
        "dimensions": [
            {
                "name": "calls_per_day",
                "limit": 20,
                "window_seconds": 86400,
                "unit": "calls",
                "scope": "api_key",
            }
        ],
        "reset": "00:00 UTC",
    }
    monkeypatch.setattr(
        "app.config.provider_rate_limit_seed",
        lambda _provider: {"quota_contract": contract, "quota_scope": "api_key"},
    )
    monkeypatch.setattr(
        "app.services.provider_account_usage._native_baseline_candidate",
        lambda *_args: None,
    )
    reconcile = monkeypatch.setattr(
        "app.services.provider_quota_coordinator.reconcile_provider_quota_baseline",
        lambda **_kwargs: pytest.fail("unproven native snapshot must not reconcile"),
    )
    del reconcile

    usage = SimpleNamespace(
        observed_at=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        dimensions=(
            SimpleNamespace(
                name="calls_per_day",
                unit="calls",
                limit=20,
                remaining=20,
                consumed=0,
                reset_at=None,
            ),
        ),
    )
    assert live_usage.reconcile_native_account_usage("test_provider", usage) == [
        {
            "status": "not_reconciled",
            "dimension": "calls_per_day",
            "reason": "provider snapshot did not prove the reviewed active window",
        }
    ]


def test_openfigi_native_usage_reconciles_the_environment_specific_dimension(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "OPENFIGI_API_KEY", "")
    calls = []
    monkeypatch.setattr(
        "app.services.provider_quota_coordinator.reconcile_provider_quota_baseline",
        lambda **kwargs: calls.append(kwargs) or {"window_started_at": "2026-09-16T12:00:00+00:00"},
    )
    usage = SimpleNamespace(
        observed_at=datetime(2026, 9, 16, 12, 0, tzinfo=UTC),
        dimensions=(
            SimpleNamespace(
                name="mapping_requests_per_minute",
                unit="requests",
                limit=25,
                remaining=24,
                consumed=1,
                reset_at=datetime(2026, 9, 16, 12, 1, tzinfo=UTC),
            ),
        ),
    )

    result = live_usage.reconcile_native_account_usage("openfigi", usage)

    assert result == [
        {
            "status": "reconciled",
            "dimension": "mapping_requests_per_minute",
            "used_units": 1,
            "window_started_at": "2026-09-16T12:00:00+00:00",
        }
    ]
    assert calls[0]["dimension_name"] == "mapping_requests_per_minute"


@pytest.mark.parametrize("is_async", [False, True])
def test_httpx_live_transport_requires_active_durable_quota_admission(monkeypatch, is_async):
    import httpx

    monkeypatch.setenv("RUN_LIVE_PROVIDER_TESTS", "1")
    live_usage.install_httpx_quota_admission_guard(patcher=monkeypatch)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"ok": True}))

    if is_async:

        async def send():
            async with httpx.AsyncClient(transport=transport) as client:
                with pytest.raises(RuntimeError, match="no active durable quota reservation"):
                    await client.get("https://provider.example.test/quote")
                token = live_usage.activate_request_admission()
                try:
                    response = await client.get("https://provider.example.test/quote")
                finally:
                    live_usage.deactivate_request_admission(token)
                assert response.json() == {"ok": True}

        asyncio.run(send())
    else:
        with httpx.Client(transport=transport) as client:
            with pytest.raises(RuntimeError, match="no active durable quota reservation"):
                client.get("https://provider.example.test/quote")
            token = live_usage.activate_request_admission()
            try:
                response = client.get("https://provider.example.test/quote")
            finally:
                live_usage.deactivate_request_admission(token)
            assert response.json() == {"ok": True}


@pytest.mark.parametrize("scope", ["", "x" * 129, "x\nlabel"])
def test_live_usage_preflight_rejects_missing_or_invalid_scope(monkeypatch, scope):
    monkeypatch.setenv("PROVIDER_LIVE_USAGE_SCOPE", scope)

    with pytest.raises(RuntimeError, match="scope is missing or invalid"):
        live_usage.ensure_usage_scope_configured()


def test_merge_provider_live_usage_sanitizes_and_deduplicates_receipts(tmp_path: Path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    destination = tmp_path / "owner" / "provider-live-usage.jsonl"
    first.write_text(
        json.dumps(
            {
                "at": "2026-09-10T05:00:00+00:00",
                "run_id": "github-1",
                "provider": "fred",
                "operations": 1,
                "http_requests": 2,
                "response_bytes": 100,
                "exit_status": 0,
                "response_headers": {
                    "x-api-ratelimit-limit": "100",
                    "x-api-ratelimit-remaining": "96",
                    "x-api-ratelimit-reset": "1700000000",
                    "x-api-ratelimit-consumed": "4",
                },
                "operation_usage": {
                    "fetch_series": {
                        "operations": 1,
                        "http_requests": 2,
                        "response_bytes": 100,
                        "failed_operations": 0,
                    }
                },
                "payload": "must-not-be-copied",
            }
        )
        + "\n"
    )
    second.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "at": "2026-09-10T05:00:01+00:00",
                        "run_id": "github-1",
                        "provider": "fred",
                        "operations": 9,
                        "http_requests": 9,
                        "response_bytes": 9,
                        "exit_status": 0,
                    }
                ),
                json.dumps(
                    {
                        "at": "2026-09-10T05:00:02+00:00",
                        "run_id": "github-1",
                        "provider": "coinbase",
                        "operations": 1,
                        "http_requests": 1,
                        "response_bytes": 20,
                        "exit_status": 0,
                    }
                ),
                json.dumps(
                    {
                        "at": "2026-09-10T05:00:03+00:00",
                        "provider": "invalid-fraction",
                        "operations": 1.5,
                        "http_requests": 1,
                        "response_bytes": 20,
                        "exit_status": 0,
                    }
                ),
            ]
        )
        + "\n"
    )

    result = _MERGER.merge_receipts([first, second], destination)

    assert result["accepted"] == 2
    assert result["duplicates"] == 1
    assert result["rejected"] == 1
    rows = [json.loads(line) for line in destination.read_text().splitlines()]
    assert len(rows) == 2
    assert all("payload" not in row for row in rows)
    assert {row["provider"] for row in rows} == {"fred", "coinbase"}
    fred_row = next(row for row in rows if row["provider"] == "fred")
    assert fred_row["failed_operations"] == 0
    assert fred_row["process_exit_status"] == 0
    assert fred_row["response_headers"] == {
        "x-api-ratelimit-consumed": "4",
        "x-api-ratelimit-limit": "100",
        "x-api-ratelimit-remaining": "96",
        "x-api-ratelimit-reset": "1700000000",
    }
    assert fred_row["operation_usage"]["fetch_series"]["http_requests"] == 2
    assert destination.stat().st_mode & 0o077 == 0


def test_merge_provider_live_usage_keeps_same_run_separate_by_usage_scope(tmp_path: Path):
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    destination = tmp_path / "provider-live-usage.jsonl"
    base = {
        "at": "2026-09-10T05:00:00+00:00",
        "run_id": "shared-run-id",
        "provider": "fred",
        "operations": 1,
        "http_requests": 1,
        "response_bytes": 10,
        "exit_status": 0,
    }
    first.write_text(json.dumps({**base, "usage_scope": "local-dev"}) + "\n")
    second.write_text(json.dumps({**base, "usage_scope": "github-provider-live"}) + "\n")

    result = _MERGER.merge_receipts([first, second], destination)

    assert result["accepted"] == 2
    assert result["duplicates"] == 0
    rows = [json.loads(line) for line in destination.read_text().splitlines()]
    assert {row["usage_scope"] for row in rows} == {
        "local-dev",
        "github-provider-live",
    }


def test_merge_provider_live_usage_rejects_malformed_rows_without_exposing_values(
    tmp_path: Path,
):
    source = tmp_path / "receipt.jsonl"
    destination = tmp_path / "provider-live-usage.jsonl"
    source.write_text(
        "not-json\n"
        + json.dumps(
            {
                "at": "2026-09-10T05:00:00+00:00",
                "provider": "fred",
                "operations": 1,
                "http_requests": 1,
                "response_bytes": 10,
                "exit_status": 0,
            }
        )
        + "\n"
    )

    result = _MERGER.merge_receipts([source], destination)

    assert result["accepted"] == 1
    assert result["rejected"] == 1
    assert len(destination.read_text().splitlines()) == 1


def test_merge_provider_live_usage_rejects_non_capacity_headers(tmp_path: Path):
    source = tmp_path / "receipt.jsonl"
    destination = tmp_path / "provider-live-usage.jsonl"
    source.write_text(
        json.dumps(
            {
                "at": "2026-09-10T05:00:00+00:00",
                "provider": "fred",
                "operations": 1,
                "http_requests": 1,
                "response_bytes": 10,
                "exit_status": 0,
                "response_headers": {"authorization": "secret"},
            }
        )
        + "\n"
    )

    result = _MERGER.merge_receipts([source], destination)

    assert result["accepted"] == 0
    assert result["rejected"] == 1
    assert not destination.read_text()


def test_merge_provider_live_usage_rejects_failed_operations_above_operation_count(
    tmp_path: Path,
):
    source = tmp_path / "receipt.jsonl"
    destination = tmp_path / "provider-live-usage.jsonl"
    source.write_text(
        json.dumps(
            {
                "at": "2026-09-10T05:00:00+00:00",
                "provider": "fred",
                "operations": 1,
                "failed_operations": 2,
                "http_requests": 1,
                "response_bytes": 10,
                "exit_status": 1,
                "process_exit_status": 1,
            }
        )
        + "\n"
    )

    result = _MERGER.merge_receipts([source], destination)

    assert result["accepted"] == 0
    assert result["rejected"] == 1
    assert not destination.read_text()


def test_merge_provider_live_usage_rejects_operation_totals_above_provider_totals(
    tmp_path: Path,
):
    source = tmp_path / "receipt.jsonl"
    destination = tmp_path / "provider-live-usage.jsonl"
    source.write_text(
        json.dumps(
            {
                "at": "2026-09-10T05:00:00+00:00",
                "provider": "fred",
                "operations": 1,
                "http_requests": 1,
                "response_bytes": 10,
                "exit_status": 0,
                "operation_usage": {
                    "fetch_series": {
                        "operations": 2,
                        "http_requests": 2,
                        "response_bytes": 20,
                        "failed_operations": 0,
                    }
                },
            }
        )
        + "\n"
    )

    result = _MERGER.merge_receipts([source], destination)

    assert result["accepted"] == 0
    assert result["rejected"] == 1
    assert not destination.read_text()
