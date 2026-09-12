from datetime import UTC, datetime

import pytest

from app.models.data_source import DataSource
from app.models.market_data_foundation import ProviderQuotaWindow, ProviderWorkloadLease
from app.services.provider_routing import reserve_provider_quota, settle_workload_lease
from app.services.provider_runtime import ProviderQuotaUnknownError
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
        window_seconds=60,
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
        window_seconds=60,
        now=now,
    )
    assert second is None
    row = db.query(ProviderQuotaWindow).one()
    assert row.reserved_units == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("units", 0),
        ("units", -1),
        ("units", True),
        ("units", 1.5),
        ("limit_units", 0),
        ("limit_units", True),
        ("limit_units", 1.5),
        ("window_seconds", 0),
        ("window_seconds", None),
        ("window_seconds", True),
        ("window_seconds", 1.5),
    ],
)
async def test_durable_quota_reservation_rejects_malformed_contract_values(db, field, value):
    async_db = AsyncSessionAdapter(db)
    source = DataSource(name=f"invalid-quota-{field}", is_active=True)
    db.add(source)
    db.flush()
    arguments = {
        "data_source_id": source.id,
        "capability": "price_history",
        "units": 1,
        "limit_units": 3,
        "window_seconds": 60,
    }
    arguments[field] = value

    assert await reserve_provider_quota(async_db, **arguments) is None
    assert db.query(ProviderQuotaWindow).count() == 0


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
        window_seconds=60,
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
    concurrent = await reserve_provider_quota(
        async_db,
        data_source_id=source.id,
        capability="price_history",
        dimension="concurrent_requests",
        units=1,
        limit_units=2,
        window_seconds=1,
        now=now,
        rolling=True,
        release_only=True,
    )
    assert minute is not None and month is not None and concurrent is not None
    lease = ProviderWorkloadLease(
        workload_key="calendar-lease",
        capability="price_history",
        data_source_id=source.id,
        units=1,
        status="reserved",
        lease_expires_at=now,
        request_metadata={
            "quota_window_ids": [minute.id, concurrent.id],
            "release_only_dimensions": ["concurrent_requests"],
        },
    )
    db.add(lease)
    db.flush()
    minute.reserved_units = 1
    month.reserved_units = 1
    concurrent.reserved_units = 1
    await settle_workload_lease(async_db, lease, success=True)
    assert minute.reserved_units == 0
    assert minute.consumed_units == 1
    assert month.reserved_units == 1
    assert month.consumed_units == 0
    assert concurrent.reserved_units == 0
    assert concurrent.consumed_units == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("lease_units", "consumed_units"),
    [
        (True, None),
        (1.5, None),
        ("1", None),
        (-1, None),
        (1, True),
        (1, 1.5),
        (1, "1"),
        (1, -1),
    ],
)
async def test_settle_workload_lease_rejects_malformed_units(
    db, lease_units, consumed_units
):
    async_db = AsyncSessionAdapter(db)
    lease = ProviderWorkloadLease(
        workload_key="invalid-settlement-units",
        capability="price_history",
        units=lease_units,
        status="reserved",
        lease_expires_at=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
        request_metadata={"quota_window_ids": []},
    )

    with pytest.raises(ProviderQuotaUnknownError):
        await settle_workload_lease(async_db, lease, consumed_units=consumed_units)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {"quota_window_ids": "1"},
        {"quota_window_ids": [True]},
        {"quota_window_ids": ["1"]},
        {"quota_window_ids": [-1]},
        {"quota_window_ids": [1, 1]},
    ],
)
async def test_settle_workload_lease_rejects_malformed_window_metadata(db, metadata):
    async_db = AsyncSessionAdapter(db)
    lease = ProviderWorkloadLease(
        workload_key="invalid-settlement-window-metadata",
        capability="price_history",
        units=1,
        status="reserved",
        lease_expires_at=datetime(2026, 9, 5, 12, 0, tzinfo=UTC),
        request_metadata=metadata,
    )

    with pytest.raises(ProviderQuotaUnknownError):
        await settle_workload_lease(async_db, lease)
