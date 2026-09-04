from datetime import UTC, datetime

import pytest

from app.models.data_source import DataSource
from app.models.market_data_foundation import ProviderQuotaWindow
from app.services.provider_routing import reserve_provider_quota
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
