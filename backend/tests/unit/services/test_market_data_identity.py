import pytest
from sqlalchemy import select

from app.models.market_data_foundation import InstrumentIdentityQuarantineObservation
from app.services.market_data_identity import _record_quarantine
from tests.unit.conftest import AsyncSessionAdapter


@pytest.mark.asyncio
async def test_identity_quarantine_retains_repeated_provider_payloads(db, instrument):
    session = AsyncSessionAdapter(db)

    first = await _record_quarantine(
        session,
        instrument=instrument,
        proposed_domain_key="figi:BBG000B9XRY4",
        provider_name="fixture-provider",
        provider_symbol="ABC",
        exchange_mic="XNAS",
        reason="ambiguous owner",
        candidate_payload={"symbol": "ABC", "venue": "XNAS", "version": 1},
    )
    second = await _record_quarantine(
        session,
        instrument=instrument,
        proposed_domain_key="figi:BBG000B9XRY4",
        provider_name="fixture-provider",
        provider_symbol="ABC",
        exchange_mic="XNAS",
        reason="ambiguous owner updated",
        candidate_payload={"symbol": "ABC", "venue": "XNAS", "version": 2},
    )

    assert first.id == second.id
    observations = db.execute(
        select(InstrumentIdentityQuarantineObservation).order_by(
            InstrumentIdentityQuarantineObservation.id
        )
    ).scalars().all()
    assert [row.candidate_payload["version"] for row in observations] == [1, 2]
