from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.data_source import DataSource
from app.models.instrument import Instrument, OptionDetail, OptionRight, OptionStyle
from app.models.provider_observation import DatasetStatus, InstrumentDatasetState, OptionQuotePoint
from app.services.options_data import get_option_quote_history, list_option_expirations
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


@pytest.mark.asyncio
async def test_option_quote_history_normalizes_offset_aware_range_before_sql(
    db, instrument, instrument_type, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    option_instrument = Instrument(
        symbol="AAPL 2026-06-19 C 100",
        name="AAPL Option",
        currency="USD",
        instrument_type_id=instrument_type.id,
        is_active=True,
    )
    source = DataSource(name="yfinance-quotes", is_active=True)
    db.add_all([option_instrument, source])
    db.flush()
    db.add_all(
        [
            OptionQuotePoint(
                option_instrument_id=option_instrument.id,
                data_source_id=source.id,
                observed_at=datetime(2026, 1, 1, tzinfo=UTC),
                mark=Decimal("1.25"),
            ),
            OptionQuotePoint(
                option_instrument_id=option_instrument.id,
                data_source_id=source.id,
                observed_at=datetime(2026, 1, 2, tzinfo=UTC),
                mark=Decimal("1.50"),
            ),
        ]
    )
    db.commit()

    async def _skip_sync(*_args, **_kwargs):
        return None

    monkeypatch.setattr("app.services.options_data.sync_option_quote_history", _skip_sync)

    rows = await get_option_quote_history(
        async_db,
        option_instrument.id,
        start=datetime.fromisoformat("2026-01-01T02:00:00+02:00"),
        end=datetime.fromisoformat("2026-01-02T02:00:00+02:00"),
    )

    assert [row["mark"] for row in rows] == [1.25, 1.5]
