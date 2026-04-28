from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.data_source import DataSource
from app.models.instrument import Instrument, OptionDetail, OptionRight, OptionStyle
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState
from app.services.options_data import list_option_expirations
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_list_option_expirations_prefers_fresh_dataset_state(db, instrument, instrument_type):
    async_db = AsyncSessionAdapter(db)

    option_instrument = Instrument(
        symbol="AAPL 2026-06-19 C 100",
        name="AAPL Option",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    db.add(option_instrument)
    db.flush()

    db.add(
        OptionDetail(
            instrument_id=option_instrument.id,
            underlying_instrument_id=instrument.id,
            right=OptionRight.CALL,
            style=OptionStyle.AMERICAN,
            contract_key="aapl|2026-06-19|100|call",
            strike=Decimal("100"),
            expiry_date=datetime(2026, 6, 19, tzinfo=UTC).date(),
            contract_size=Decimal("100"),
        )
    )

    source = DataSource(name="yfinance", is_active=True)
    db.add(source)
    db.flush()

    db.add(
        InstrumentDatasetState(
            instrument_id=instrument.id,
            data_source_id=source.id,
            dataset_type="option_expirations",
            dataset_key="all",
            status=DatasetStatus.FRESH,
            observed_at=datetime.now(UTC),
            fetched_at=datetime.now(UTC),
            stale_after=datetime.now(UTC) + timedelta(hours=1),
            extra_data={"expirations": ["2026-06-19", "2026-09-18", "2027-01-15"]},
        )
    )
    db.commit()

    expirations = await list_option_expirations(async_db, instrument)

    assert [item.isoformat() for item in expirations] == ["2026-06-19", "2026-09-18", "2027-01-15"]
