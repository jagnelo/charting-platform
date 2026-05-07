from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.provider_observation import (
    DatasetStatus,
    InstrumentDatasetState,
    InstrumentSearchSnapshot,
    LatestPriceSnapshot,
)
from app.models.provider_runtime import ProviderCapability, ProviderHealthState
from app.services.provider_maintenance import (
    list_stale_dataset_states,
    prune_provider_observations,
    reset_provider_health_state,
    summarize_provider_observations,
)
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_summarize_and_prune_provider_observations(db, instrument, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    data_source = DataSource(name="yfinance", is_active=True)
    db.add(data_source)
    db.flush()
    db.add(
        LatestPriceSnapshot(
            instrument_id=instrument.id,
            data_source_id=data_source.id,
            provider_symbol="AAPL",
            observed_at=datetime.now(UTC) - timedelta(days=31),
            fetched_at=datetime.now(UTC) - timedelta(days=31),
            price=100,
            payload={"price": 100},
        )
    )
    db.add(
        InstrumentSearchSnapshot(
            data_source_id=data_source.id,
            query="aapl",
            observed_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
            result_hash="hash",
            payload={"query": "aapl", "results": []},
        )
    )
    db.commit()

    summary = await summarize_provider_observations(async_db)
    latest_prices = next(row for row in summary if row["dataset"] == "latest_price_snapshot")
    assert latest_prices["rows"] == 1

    monkeypatch.setattr(
        "app.services.provider_maintenance.settings.LATEST_PRICE_SNAPSHOT_RETENTION_DAYS", 30
    )
    deleted = await prune_provider_observations(async_db)

    remaining = db.execute(select(LatestPriceSnapshot)).scalars().all()
    assert deleted["latest_price_snapshot"] == 1
    assert remaining == []


@pytest.mark.asyncio
async def test_list_stale_states_and_reset_health(db, instrument):
    async_db = AsyncSessionAdapter(db)
    data_source = DataSource(name="yfinance", is_active=True)
    db.add(data_source)
    db.flush()
    db.add(
        InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=data_source.id,
            dataset_type="price_history",
            dataset_key="D1:adj",
            status=DatasetStatus.FRESH,
            stale_after=datetime.now(UTC) - timedelta(minutes=10),
            observed_at=datetime.now(UTC) - timedelta(hours=2),
            fetched_at=datetime.now(UTC) - timedelta(hours=2),
        )
    )
    db.add(
        ProviderHealthState(
            data_source_id=data_source.id,
            capability=ProviderCapability.PRICE_HISTORY,
            failure_streak=2,
            last_error_type="TimeoutError",
            last_error_message="timeout",
            circuit_open_until=datetime.now(UTC) + timedelta(minutes=5),
        )
    )
    db.commit()

    stale = await list_stale_dataset_states(async_db)
    assert len(stale) == 1
    assert stale[0]["symbol"] == "AAPL"

    reset = await reset_provider_health_state(
        async_db,
        provider_name="yfinance",
        capability=ProviderCapability.PRICE_HISTORY,
    )
    health = db.execute(select(ProviderHealthState)).scalar_one()
    assert reset is True
    assert health.failure_streak == 0
    assert health.circuit_open_until is None
