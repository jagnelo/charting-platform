from datetime import UTC, datetime

import pytest

from app.models.data_source import DataSource
from app.models.market_data_foundation import ProviderQuotaWindow, ProviderWorkloadLease
from app.services.provider_routing import reserve_provider_quota, settle_workload_lease
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_durable_quota_reservation_rejects_over_limit(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="quota-test", is_active=True)
    db.add(source)
    db.flush()
    now = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
    first = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="price_history",
        units=2,
        limit_units=3,
        now=now,
    )
    assert first is not None
    assert first.reserved_units == 2
    second = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="price_history",
        units=2,
        limit_units=3,
        now=now,
    )
    assert second is None
    row = db.query(ProviderQuotaWindow).one()
    assert row.reserved_units == 2


@pytest.mark.asyncio
async def test_settle_workload_lease_debits_only_its_reserved_windows(db):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name="calendar-quota-test", is_active=True)
    db.add(source)
    db.flush()
    now = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
    minute = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="price_history",
        dimension="per_minute",
        units=1,
        limit_units=10,
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
        window_started_at=datetime(2026, 9, 1, tzinfo=UTC),
        now=now,
    )
    assert minute is not None and month is not None
    lease = ProviderWorkloadLease(
        workload_key="calendar-lease",
        capability="price_history",
        data_source_id=source.id,
        units=1,
        status="reserved",
        lease_expires_at=now,
        request_metadata={"quota_window_ids": [minute.id]},
    )
    db.add(lease)
    db.flush()
    minute.reserved_units = 1
    month.reserved_units = 1
    await settle_workload_lease(async_db, lease, success=True)
    assert minute.reserved_units == 0
    assert minute.consumed_units == 1
    assert month.reserved_units == 1
    assert month.consumed_units == 0
