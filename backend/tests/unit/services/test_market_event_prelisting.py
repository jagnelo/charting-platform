from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.models.data_source import DataSource
from app.models.instrument import Instrument
from app.models.instrument_identity import (
    InstrumentIdentifier,
    InstrumentIdentifierType,
    InstrumentProviderSymbol,
)
from app.models.market_data_foundation import (
    IdentityStatus,
    MarketEvent,
    MarketEventConsensus,
    MarketEventPrelistingCandidate,
)
from app.services.market_event_prelisting import (
    materialize_prelisting_candidates,
    promote_prelisting_candidates,
)
from tests.unit.conftest import AsyncSessionAdapter


def _event(*, source: str, key: str, payload: dict, consensus_id: int | None = None):
    return MarketEvent(
        event_type="ipo",
        event_key=key,
        source=source,
        consensus_id=consensus_id,
        event_time=datetime(2026, 9, 20, 14, tzinfo=UTC),
        effective_date=date(2026, 9, 20),
        payload=payload,
    )


def _consensus(db, *, status: str = "corroborated"):
    value = MarketEventConsensus(
        consensus_key=f"test-prelisting-{status}",
        event_type="ipo",
        status=status,
        observation_count=2,
        source_count=2,
        first_observed_at=datetime(2026, 9, 1, tzinfo=UTC),
        last_observed_at=datetime(2026, 9, 2, tzinfo=UTC),
        agreement_fields=[],
        conflict_fields=[] if status != "conflicted" else [{"field": "exchange_mic"}],
        canonical_payload={},
        provenance={},
    )
    db.add(value)
    db.flush()
    return value


@pytest.mark.asyncio
async def test_materialization_deduplicates_consensus_into_inactive_provisional_instrument(
    db, instrument_type
):
    consensus = _consensus(db)
    db.add_all(
        [
            _event(
                source="alpaca",
                key="alpaca:ipo:newco",
                consensus_id=consensus.id,
                payload={"symbol": "NEWC", "name": "New Co", "exchange_mic": "XNAS"},
            ),
            _event(
                source="edgar",
                key="edgar:ipo:newco",
                consensus_id=consensus.id,
                payload={"symbol": "NEWC", "company_name": "New Co", "mic": "XNAS"},
            ),
        ]
    )
    db.flush()

    result = await materialize_prelisting_candidates(AsyncSessionAdapter(db))

    assert result["candidates"] == 1
    assert result["instruments_created"] == 1
    candidate = db.execute(select(MarketEventPrelistingCandidate)).scalar_one()
    created = db.get(Instrument, candidate.instrument_id)
    assert candidate.provider_sources == ["alpaca", "edgar"]
    assert created is not None
    assert created.symbol == "NEWC"
    assert created.is_active is False
    assert created.identity_status == IdentityStatus.PROVISIONAL.value

    rerun = await materialize_prelisting_candidates(AsyncSessionAdapter(db))
    assert rerun["created"] == 0
    assert rerun["updated"] == 1
    assert db.execute(select(MarketEventPrelistingCandidate)).scalars().all() == [candidate]


@pytest.mark.asyncio
async def test_conflicted_consensus_is_quarantined_without_instrument(db):
    consensus = _consensus(db, status="conflicted")
    db.add(
        _event(
            source="massive",
            key="massive:ipo:conflict",
            consensus_id=consensus.id,
            payload={"symbol": "CNFL", "name": "Conflict Co"},
        )
    )
    db.flush()

    result = await materialize_prelisting_candidates(AsyncSessionAdapter(db))

    candidate = db.execute(select(MarketEventPrelistingCandidate)).scalar_one()
    assert result["quarantined"] == 1
    assert candidate.status == "quarantined"
    assert candidate.instrument_id is None
    assert db.execute(select(Instrument).where(Instrument.symbol == "CNFL")).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_malformed_symbol_is_skipped_without_guessing_identity(db):
    db.add(_event(source="fmp", key="fmp:ipo:bad", payload={"symbol": "BAD SYMBOL"}))
    db.flush()

    result = await materialize_prelisting_candidates(AsyncSessionAdapter(db))

    assert result["skipped"] == 1
    assert db.execute(select(MarketEventPrelistingCandidate)).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_promotion_requires_unique_stable_identifier_and_updates_event(db, instrument):
    event = _event(source="edgar", key="edgar:ipo:promote", payload={"symbol": "NEWC"})
    db.add(event)
    db.flush()
    candidate = MarketEventPrelistingCandidate(
        candidate_key="event:promote",
        anchor_event_id=event.id,
        proposed_symbol="NEWC",
        proposed_name="New Co",
        status="pending",
        stable_identifiers={"figi": "BBG000000001"},
        provider_sources=["edgar"],
        first_seen_at=datetime(2026, 9, 1, tzinfo=UTC),
        last_seen_at=datetime(2026, 9, 2, tzinfo=UTC),
        provenance={},
    )
    db.add_all(
        [
            candidate,
            InstrumentIdentifier(
                instrument_id=instrument.id,
                identifier_type=InstrumentIdentifierType.FIGI,
                identifier_value="BBG000000001",
                is_active=True,
            ),
        ]
    )
    db.flush()

    result = await promote_prelisting_candidates(AsyncSessionAdapter(db))

    assert result["promoted"] == 1
    assert candidate.status == "listed"
    assert candidate.instrument_id == instrument.id
    assert event.instrument_id == instrument.id


@pytest.mark.asyncio
async def test_promotion_does_not_use_ticker_only_or_ambiguous_venue_matches(db, instrument_type):
    source = DataSource(name="venue-provider-a", base_url="https://example.test/a")
    second_source = DataSource(name="venue-provider-b", base_url="https://example.test/b")
    first = Instrument(
        instrument_type_id=instrument_type.id,
        symbol="NEWC",
        name="First Co",
        is_active=True,
    )
    second = Instrument(
        instrument_type_id=instrument_type.id,
        symbol="NEWC",
        name="Second Co",
        is_active=True,
    )
    db.add_all([source, second_source, first, second])
    db.flush()
    db.add_all(
        [
            InstrumentProviderSymbol(
                instrument_id=first.id,
                data_source_id=source.id,
                provider_symbol="NEWC",
                provider_exchange_code="XNAS",
                is_active=True,
            ),
            InstrumentProviderSymbol(
                instrument_id=second.id,
                data_source_id=second_source.id,
                provider_symbol="NEWC",
                provider_exchange_code="XNAS",
                is_active=True,
            ),
            MarketEventPrelistingCandidate(
                candidate_key="event:ticker-only",
                proposed_symbol="NEWC",
                proposed_name="Unknown Co",
                status="pending",
                provider_sources=[],
                first_seen_at=datetime(2026, 9, 1, tzinfo=UTC),
                last_seen_at=datetime(2026, 9, 2, tzinfo=UTC),
                provenance={},
            ),
            MarketEventPrelistingCandidate(
                candidate_key="event:ambiguous",
                proposed_symbol="NEWC",
                proposed_name="Unknown Co",
                exchange_mic="XNAS",
                status="pending",
                provider_sources=["venue-provider-a", "venue-provider-b"],
                first_seen_at=datetime(2026, 9, 1, tzinfo=UTC),
                last_seen_at=datetime(2026, 9, 2, tzinfo=UTC),
                provenance={},
            ),
        ]
    )
    db.flush()

    result = await promote_prelisting_candidates(AsyncSessionAdapter(db))

    assert result["promoted"] == 0
    assert result["ambiguous"] == 1
    assert db.execute(
        select(MarketEventPrelistingCandidate.status)
        .order_by(MarketEventPrelistingCandidate.candidate_key)
    ).scalars().all() == ["pending", "pending"]


@pytest.mark.asyncio
async def test_prelisting_rejects_reversed_window_and_invalid_bounds(db):
    with pytest.raises(ValueError, match="on or after"):
        await materialize_prelisting_candidates(
            AsyncSessionAdapter(db), start=date(2026, 9, 21), end=date(2026, 9, 20)
        )
    with pytest.raises(ValueError, match="between 1 and 10000"):
        await promote_prelisting_candidates(AsyncSessionAdapter(db), max_candidates=0)
