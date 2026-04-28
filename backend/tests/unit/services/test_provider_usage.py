from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.data_source import DataSource
from app.models.provider_runtime import ProviderCapability, ProviderRequestLog
from app.services.provider_usage import summarize_provider_usage
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_summarize_provider_usage_tracks_plain_request_counts(db):
    async_db = AsyncSessionAdapter(db)
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
                latency_ms=250,
                error_type="TimeoutError",
            ),
        ]
    )
    db.commit()

    rows = await summarize_provider_usage(async_db)
    summary = next(row for row in rows if row["provider"] == "yfinance")

    assert summary["usage_mode"] == "call_count"
    assert summary["usage_unit_label"] == "requests"
    assert summary["requests_24h"] == 2
    assert summary["units_24h"] == pytest.approx(2.0)
    assert summary["failure_rate_24h"] == pytest.approx(50.0)
    assert summary["timeout_rate_24h"] == pytest.approx(50.0)
    assert summary["top_operations"][0]["operation_family"] == "search_instruments"


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
    assert summary["quota_limit"] == 100
