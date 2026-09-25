"""Regression coverage for immutable fundamental and short-interest evidence."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.market_data_foundation import (
    FundamentalFact,
    FundamentalFactObservation,
    ShortInterestObservation,
    ShortInterestProviderObservation,
)
from app.providers.base import FundamentalFactRecord, ShortInterestRecord
from app.services.market_data_persistence import persist_fundamental_facts, persist_short_interest
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_persist_fundamentals_retains_repeated_payloads(db, instrument):
    record = FundamentalFactRecord(
        namespace="us-gaap",
        key="Assets",
        unit="USD",
        value_numeric=Decimal("100"),
        value_text=None,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
        filed_at=date(2026, 8, 1),
        accepted_at=datetime.now(UTC),
        source_identifier="acc-1",
        raw_payload={"value": 100},
    )
    adapter = AsyncSessionAdapter(db)
    inserted_first = await persist_fundamental_facts(
        adapter,
        [record],
        source="edgar",
        instrument_id=instrument.id,
    )
    inserted_second = await persist_fundamental_facts(
        adapter,
        [record],
        source="edgar",
        instrument_id=instrument.id,
    )
    assert inserted_first == 1
    assert inserted_second == 0
    assert db.query(FundamentalFact).count() == 1
    observations = db.execute(
        select(FundamentalFactObservation).order_by(FundamentalFactObservation.id)
    ).scalars().all()
    assert len(observations) == 2
    assert [row.payload for row in observations] == [{"value": 100}, {"value": 100}]


@pytest.mark.asyncio
async def test_persist_short_interest_retains_repeated_payloads(db, instrument):
    record = ShortInterestRecord(
        settlement_date=date(2026, 9, 1),
        publication_date=date(2026, 9, 15),
        short_position=Decimal("1000"),
        short_percent_float=Decimal("0.1"),
        days_to_cover=Decimal("2"),
        source_identifier="si-1",
        raw_payload={"shortPosition": 1000},
    )
    adapter = AsyncSessionAdapter(db)
    inserted_first = await persist_short_interest(adapter, instrument.id, [record], source="finra")
    inserted_second = await persist_short_interest(adapter, instrument.id, [record], source="finra")
    assert inserted_first == 1
    assert inserted_second == 0
    assert db.query(ShortInterestObservation).count() == 1
    observations = db.execute(
        select(ShortInterestProviderObservation).order_by(ShortInterestProviderObservation.id)
    ).scalars().all()
    assert len(observations) == 2
    assert [row.payload for row in observations] == [
        {"shortPosition": 1000},
        {"shortPosition": 1000},
    ]
