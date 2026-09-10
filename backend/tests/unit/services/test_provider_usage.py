from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.config import settings
from app.models.data_source import DataSource
from app.models.market_data_foundation import ProviderQuotaIdentity, ProviderQuotaWindow
from app.models.provider_runtime import ProviderCapability, ProviderRequestLog
from app.services.provider_usage import read_live_usage_ledger, summarize_provider_usage
from tests.unit.conftest import AsyncSessionAdapter


def test_read_live_usage_ledger_aggregates_redacted_rows(tmp_path, monkeypatch):
    now = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    ledger = tmp_path / "provider-live-usage.jsonl"
    ledger.write_text(
        '\n'.join(
            [
                '{"at":"2026-09-10T11:00:00+00:00","provider":"fred","operations":2,"http_requests":3,"response_bytes":100,"exit_status":0}',
                '{"at":"2026-09-08T12:00:00+00:00","provider":"fred","operations":1,"http_requests":1,"response_bytes":50,"exit_status":2}',
                '{"at":"2026-09-10T11:30:00+00:00","provider":"coinbase","operations":1,"http_requests":1,"response_bytes":25,"exit_status":0}',
                '{"at":"2026-09-10T11:45:00+00:00","provider":"fractional","operations":1.5,"http_requests":1,"response_bytes":25,"exit_status":0}',
                'not-json',
            ]
        )
        + '\n'
    )
    monkeypatch.setattr(settings, "PROVIDER_LIVE_USAGE_LEDGER", str(ledger))

    result = read_live_usage_ledger(now=now)

    assert result["status"] == "available"
    assert result["rows"] == 3
    assert result["invalid_rows"] == 2
    assert result["providers"]["fred"]["http_requests"] == 4
    assert result["providers"]["fred"]["http_requests_24h"] == 3
    assert result["providers"]["fred"]["runs_7d"] == 2
    assert result["providers"]["fred"]["failed_runs"] == 1


def test_read_live_usage_ledger_reports_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_LIVE_USAGE_LEDGER", str(tmp_path / "missing.jsonl"))

    result = read_live_usage_ledger(now=datetime.now(UTC))

    assert result["status"] == "unavailable"
    assert result["reason"] == "ledger_missing"


@pytest.mark.asyncio
async def test_summarize_provider_usage_tracks_plain_request_counts(db, monkeypatch, tmp_path):
    async_db = AsyncSessionAdapter(db)
    ledger = tmp_path / "provider-live-usage.jsonl"
    monkeypatch.setattr(settings, "PROVIDER_LIVE_USAGE_LEDGER", str(ledger))
    source = DataSource(
        name="yfinance",
        is_active=True,
        config={
            "usage_tracking": {
                "mode": "call_count",
                "unit_label": "requests",
                "limit_kind": "unknown",
            }
        },
    )
    db.add(source)
    db.flush()
    now = datetime.now(UTC)
    db.add_all(
        [
            ProviderRequestLog(
                data_source_id=source.id,
                capability=ProviderCapability.INSTRUMENT_SEARCH,
                operation="search_instruments",
                operation_family="search_instruments",
                requested_at=now - timedelta(hours=2),
                completed_at=now - timedelta(hours=2),
                success=True,
                usage_mode="call_count",
                usage_unit_label="requests",
                usage_units=Decimal("1"),
                http_requests=1,
                response_bytes=1200,
                latency_ms=120,
            ),
            ProviderRequestLog(
                data_source_id=source.id,
                capability=ProviderCapability.INSTRUMENT_SEARCH,
                operation="search_instruments",
                operation_family="search_instruments",
                requested_at=now - timedelta(hours=1),
                completed_at=now - timedelta(hours=1),
                success=False,
                usage_mode="call_count",
                usage_unit_label="requests",
                usage_units=Decimal("1"),
                http_requests=1,
                response_bytes=800,
                response_headers={"x-ratelimit-remaining": "17"},
                latency_ms=250,
                error_type="TimeoutError",
            ),
        ]
    )
    db.add(
        ProviderQuotaWindow(
            data_source_id=source.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            dimension="requests_per_hour",
            window_started_at=now - timedelta(minutes=10),
            window_seconds=3600,
            limit_units=100,
            reserved_units=3,
            consumed_units=20,
        )
    )
    db.add(
        ProviderQuotaIdentity(
            data_source_id=source.id,
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            dimension="requests_per_hour",
            window_started_at=now - timedelta(minutes=10),
            window_seconds=3600,
            identity_key="AAPL",
        )
    )
    db.commit()
    ledger.write_text(
        json.dumps(
            {
                "at": now.isoformat(),
                "provider": "yfinance",
                "operations": 2,
                "http_requests": 3,
                "response_bytes": 512,
                "exit_status": 0,
            }
        )
        + "\n"
    )

    rows = await summarize_provider_usage(async_db)
    summary = next(row for row in rows if row["provider"] == "yfinance")

    assert summary["usage_mode"] == "call_count"
    assert summary["usage_unit_label"] == "requests"
    assert summary["requests_24h"] == 2
    assert summary["units_24h"] == pytest.approx(2.0)
    assert summary["response_bytes_24h"] == 2000
    assert summary["top_operations"][0]["response_bytes"] == 2000
    assert summary["failure_rate_24h"] == pytest.approx(50.0)
    assert summary["timeout_rate_24h"] == pytest.approx(50.0)
    assert summary["top_operations"][0]["operation_family"] == "search_instruments"
    assert summary["last_response_headers"] == {"x-ratelimit-remaining": "17"}
    assert summary["active_quota_windows"][0]["available_units"] == 77
    assert summary["active_quota_windows"][0]["reserved_units"] == 3
    assert summary["active_quota_windows"][0]["distinct_identity_count"] == 1
    # Direct live probes consume the same provider account outside the runtime
    # reservation path; their redacted totals must be visible without changing
    # application request counts or the durable available quota.
    assert summary["requests_24h"] == 2
    assert summary["active_quota_windows"][0]["available_units"] == 77
    assert summary["live_usage_ledger"]["status"] == "available"
    assert summary["live_usage_ledger"]["rows"] == 1
    assert summary["live_test_usage"]["operations"] == 2
    assert summary["live_test_usage"]["http_requests"] == 3
    assert summary["live_test_usage"]["response_bytes"] == 512


@pytest.mark.asyncio
async def test_summarize_provider_usage_tracks_weighted_budget_windows(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(
        name="weighted-provider",
        is_active=True,
        config={
            "usage_tracking": {
                "mode": "weighted_budget",
                "unit_label": "credits",
                "limit_kind": "exact",
                "quota_limit": 100,
                "quota_window_seconds": 3600,
            }
        },
    )
    db.add(source)
    db.flush()
    now = datetime.now(UTC)
    db.add_all(
        [
            ProviderRequestLog(
                data_source_id=source.id,
                capability=ProviderCapability.PRICE_HISTORY,
                operation="fetch_latest_ohlcv:D1",
                operation_family="fetch_latest_ohlcv",
                requested_at=now - timedelta(minutes=30),
                completed_at=now - timedelta(minutes=30),
                success=True,
                usage_mode="weighted_budget",
                usage_unit_label="credits",
                usage_units=Decimal("15"),
                http_requests=1,
                response_bytes=4096,
                latency_ms=100,
            ),
            ProviderRequestLog(
                data_source_id=source.id,
                capability=ProviderCapability.PRICE_HISTORY,
                operation="fetch_latest_ohlcv:D1",
                operation_family="fetch_latest_ohlcv",
                requested_at=now - timedelta(hours=2),
                completed_at=now - timedelta(hours=2),
                success=True,
                usage_mode="weighted_budget",
                usage_unit_label="credits",
                usage_units=Decimal("40"),
                latency_ms=120,
            ),
        ]
    )
    db.commit()

    rows = await summarize_provider_usage(async_db)
    summary = next(row for row in rows if row["provider"] == "weighted-provider")

    assert summary["usage_mode"] == "weighted_budget"
    assert summary["usage_unit_label"] == "credits"
    assert summary["current_window_requests"] == 1
    assert summary["current_window_units"] == pytest.approx(15.0)
    assert summary["current_window_utilization_pct"] == pytest.approx(15.0)
    assert summary["current_window_response_bytes"] == 4096
    assert summary["quota_limit"] == 100
