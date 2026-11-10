from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import TimeoutError as RedisTimeoutError
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


@pytest.fixture
def fresh_wake_pool(monkeypatch):
    """Start each test with no shared wake pool, and clear any left behind."""

    monkeypatch.setattr(data_preparation, "_wake_pool", None)
    monkeypatch.setattr(data_preparation, "_wake_tasks", set())
    yield
    monkeypatch.setattr(data_preparation, "_wake_pool", None)


@pytest.mark.asyncio
async def test_committed_preparation_wakeup_targets_registered_worker(monkeypatch, fresh_wake_pool):
    redis = AsyncMock()
    pool_factory = AsyncMock(return_value=redis)
    monkeypatch.setattr(data_preparation, "create_pool", pool_factory)

    await data_preparation._wake_refresh_worker()

    pool_factory.assert_awaited_once()
    args, kwargs = redis.enqueue_job.await_args
    assert args[0] == "task_process_refresh_jobs"
    assert kwargs["_expires"] == 600
    assert kwargs["_job_id"].startswith("data-preparation-wakeup:")


@pytest.mark.asyncio
async def test_wakeup_failure_does_not_replace_durable_database_queue(monkeypatch, fresh_wake_pool):
    pool_factory = AsyncMock(side_effect=RuntimeError("redis unavailable"))
    monkeypatch.setattr(data_preparation, "create_pool", pool_factory)

    await data_preparation._wake_refresh_worker()

    pool_factory.assert_awaited_once()


@pytest.mark.asyncio
async def test_wake_pool_is_created_once_and_reused(monkeypatch, fresh_wake_pool):
    redis = AsyncMock()
    pool_factory = AsyncMock(return_value=redis)
    monkeypatch.setattr(data_preparation, "create_pool", pool_factory)

    await data_preparation._wake_refresh_worker()
    await data_preparation._wake_refresh_worker()

    pool_factory.assert_awaited_once()
    assert redis.enqueue_job.await_count == 2
    redis.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_wake_enqueue_is_bounded_and_never_raises(monkeypatch, fresh_wake_pool):
    import asyncio
    import time

    async def hung_enqueue(*_args, **_kwargs):
        await asyncio.sleep(30)

    redis = AsyncMock()
    redis.enqueue_job = hung_enqueue
    monkeypatch.setattr(data_preparation, "create_pool", AsyncMock(return_value=redis))
    monkeypatch.setattr(data_preparation, "_WAKE_TIMEOUT_SECONDS", 0.05)

    started = time.monotonic()
    await data_preparation._wake_refresh_worker()

    assert time.monotonic() - started < 2


@pytest.mark.asyncio
async def test_close_worker_wake_pool_closes_once_and_swallows_close_errors(
    monkeypatch, fresh_wake_pool
):
    redis = AsyncMock()
    redis.aclose = AsyncMock(side_effect=RedisTimeoutError("Timed out closing connection after 1"))
    monkeypatch.setattr(data_preparation, "create_pool", AsyncMock(return_value=redis))
    await data_preparation._wake_refresh_worker()

    await data_preparation.close_worker_wake_pool()
    await data_preparation.close_worker_wake_pool()

    redis.aclose.assert_awaited_once()
    assert data_preparation._wake_pool is None


class _RecordingDB:
    def __init__(self, events):
        self.events = events

    async def commit(self):
        self.events.append("commit")


@pytest.mark.asyncio
async def test_ensure_closes_read_transaction_before_scheduling_the_wake(monkeypatch):
    from types import SimpleNamespace

    events: list[str] = []

    async def fake_create(_db, **_kwargs):
        events.append("create")
        return SimpleNamespace(id=1)

    async def fake_response(_db, *, parent, owner_user_id):
        events.append("response")
        return SimpleNamespace(status="queued")

    monkeypatch.setattr(data_preparation, "create_data_preparation_request", fake_create)
    monkeypatch.setattr(data_preparation, "get_data_preparation_response", fake_response)
    monkeypatch.setattr(data_preparation, "_schedule_worker_wake", lambda: events.append("wake"))

    response = await data_preparation.ensure_data(
        SimpleNamespace(),
        idempotency_key=None,
        db=_RecordingDB(events),
        current_user=SimpleNamespace(id=7),
    )

    assert response.status == "queued"
    assert events == ["create", "commit", "response", "commit", "wake"]


@pytest.mark.asyncio
async def test_slow_or_failing_wake_does_not_delay_or_fail_the_accepted_response(
    monkeypatch, fresh_wake_pool
):
    import asyncio
    import time
    from types import SimpleNamespace

    async def slow_pool(*_args, **_kwargs):
        await asyncio.sleep(30)

    async def fake_create(_db, **_kwargs):
        return SimpleNamespace(id=1)

    async def fake_response(_db, *, parent, owner_user_id):
        return SimpleNamespace(status="queued")

    monkeypatch.setattr(data_preparation, "create_data_preparation_request", fake_create)
    monkeypatch.setattr(data_preparation, "get_data_preparation_response", fake_response)
    monkeypatch.setattr(data_preparation, "create_pool", slow_pool)
    monkeypatch.setattr(data_preparation, "_WAKE_TIMEOUT_SECONDS", 0.05)

    started = time.monotonic()
    response = await data_preparation.ensure_data(
        SimpleNamespace(),
        idempotency_key=None,
        db=_RecordingDB([]),
        current_user=SimpleNamespace(id=7),
    )

    assert time.monotonic() - started < 1
    assert response.status == "queued"
    await asyncio.wait_for(asyncio.gather(*data_preparation._wake_tasks), timeout=5)


def test_ensure_returns_accepted_and_keeps_request_when_wake_is_unavailable(
    client, auth_headers, db, monkeypatch
):
    scheduled = []
    monkeypatch.setattr(data_preparation, "_schedule_worker_wake", lambda: scheduled.append(1))

    response = client.post(
        "/api/v1/data/ensure",
        headers=auth_headers,
        json={
            "target": {"kind": "instrument", "symbol": "WAKECLOSE"},
            "datasets": ["identity"],
        },
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["has_pending_work"] is True
    assert scheduled == [1]

    persisted = db.scalars(
        select(MarketRefreshJob).where(
            MarketRefreshJob.capability == "data_preparation_request",
            MarketRefreshJob.metadata_payload["data_preparation"]["request_id"].as_string()
            == body["request_id"],
        )
    ).one()
    assert persisted.status == "tracking"
    readback = client.get(f"/api/v1/data/requests/{body['request_id']}", headers=auth_headers)
    assert readback.status_code == 200, readback.text
    assert readback.json()["request_id"] == body["request_id"]
    assert readback.json()["status"] == "queued"


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
