from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.market_data_foundation import (
    AdjustmentBasis,
    MarketRefreshJob,
    MarketSeries,
    MarketSeriesDefault,
)
from app.models.ohlcv import OHLCVBar, Timeframe
from app.routers import data_preparation


@pytest.mark.asyncio
async def test_committed_preparation_wakeup_targets_registered_worker(monkeypatch):
    redis = AsyncMock()
    redis.aclose = AsyncMock()
    pool_factory = AsyncMock(return_value=redis)
    monkeypatch.setattr(data_preparation, "create_pool", pool_factory)

    await data_preparation._wake_refresh_worker()

    pool_factory.assert_awaited_once()
    args, kwargs = redis.enqueue_job.await_args
    assert args[0] == "task_process_refresh_jobs"
    assert kwargs["_expires"] == 600
    assert kwargs["_job_id"].startswith("data-preparation-wakeup:")
    redis.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_wakeup_failure_does_not_replace_durable_database_queue(monkeypatch):
    pool_factory = AsyncMock(side_effect=RuntimeError("redis unavailable"))
    monkeypatch.setattr(data_preparation, "create_pool", pool_factory)

    await data_preparation._wake_refresh_worker()

    pool_factory.assert_awaited_once()


def test_authenticated_ensure_uses_retained_selected_history_without_provider_job(
    client, auth_headers, db, instrument
):
    instrument.currency = "EUR"
    instrument.identity_status = "resolved"
    instrument.domain_key = f"test:retained-api:{instrument.symbol}"
    instrument.primary_identifier_type = "figi"
    instrument.primary_identifier_value = "BBG000GENV001"
    source = DataSource(name="retained-api-cache")
    series = MarketSeries(
        instrument=instrument,
        data_source=source,
        feed_scope="retained-api-cache",
        session_code="regular",
        timeframe=Timeframe.D1.value,
        adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
        adjustment_version="retained-api-v1",
        is_canonical=True,
        is_active=True,
    )
    db.add_all([source, series])
    db.flush()
    db.add(
        MarketSeriesDefault(
            instrument_id=instrument.id,
            timeframe=Timeframe.D1.value,
            is_adjusted=True,
            market_series_id=series.id,
            selection_reason="retained-api-cache",
        )
    )
    db.add_all(
        [
            OHLCVBar(
                instrument_id=instrument.id,
                data_source_id=source.id,
                market_series_id=series.id,
                timeframe=Timeframe.D1,
                ts=datetime(2026, 1, day, tzinfo=UTC),
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10"),
                volume=Decimal("100"),
                is_adjusted=True,
                adjustment_basis="split_adjusted",
                adjustment_version="retained-api-v1",
                scope_key=f"series:{series.id}:regular",
            )
            for day in range(1, 6)
        ]
    )
    db.flush()

    payload = {
        "target": {"kind": "instrument", "instrument_id": instrument.id},
        "datasets": ["history"],
        "timeframe": "D1",
        "adjusted": True,
        "start_at": "2026-01-01T00:00:00Z",
        "end_at": "2026-01-05T00:00:00Z",
    }
    response = client.post("/api/v1/data/ensure", headers=auth_headers, json=payload)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "ready"
    assert body["has_pending_work"] is False
    assert body["dependencies"][0]["status"] == "ready"
    assert body["dependencies"][0]["covered_start"] == "2026-01-01T00:00:00Z"
    assert body["dependencies"][0]["covered_end"] == "2026-01-05T00:00:00Z"
    assert body["dependencies"][0]["covered_ranges"][0]["market_series_id"] == series.id
    children = db.scalars(
        select(MarketRefreshJob).where(
            MarketRefreshJob.instrument_id == instrument.id,
            MarketRefreshJob.capability == "price_history",
        )
    ).all()
    assert children == []

    readback = client.get(f"/api/v1/data/requests/{body['request_id']}", headers=auth_headers)
    assert readback.status_code == 200, readback.text
    assert readback.json()["status"] == "ready"
    assert (
        readback.json()["dependencies"][0]["covered_ranges"]
        == body["dependencies"][0]["covered_ranges"]
    )
