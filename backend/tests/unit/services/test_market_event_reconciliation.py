from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.models.market_data_foundation import MarketEvent, MarketEventConsensus
from app.services.market_event_reconciliation import reconcile_market_events
from tests.unit.conftest import AsyncSessionAdapter


def _event(*, source: str, key: str, instrument_id: int | None, payload: dict) -> MarketEvent:
    return MarketEvent(
        event_type="earnings",
        event_key=key,
        event_time=datetime(2026, 9, 15, 20, tzinfo=UTC),
        effective_date=date(2026, 9, 15),
        source=source,
        instrument_id=instrument_id,
        payload=payload,
    )


@pytest.mark.asyncio
async def test_reconciliation_corroborates_exact_target_and_date(db, instrument):
    db.add_all(
        [
            _event(
                source="massive",
                key="massive:earnings:aapl:2026-09-15",
                instrument_id=instrument.id,
                payload={"title": "Earnings", "eps_estimate": "1.25"},
            ),
            _event(
                source="fmp",
                key="fmp:earnings:aapl:2026-09-15",
                instrument_id=instrument.id,
                payload={"name": "Earnings", "epsEstimate": 1.25},
            ),
        ]
    )
    db.flush()

    result = await reconcile_market_events(AsyncSessionAdapter(db))

    assert result["status"] == "complete"
    assert result["groups"] == 1
    assert result["status_counts"] == {"corroborated": 1}
    consensus = db.execute(select(MarketEventConsensus)).scalar_one()
    assert consensus.source_count == 2
    assert consensus.observation_count == 2
    assert consensus.conflict_fields == []
    assert len(db.execute(select(MarketEvent).where(MarketEvent.consensus_id == consensus.id)).scalars().all()) == 2

    rerun = await reconcile_market_events(AsyncSessionAdapter(db))
    assert rerun["groups_created"] == 0
    assert rerun["groups_updated"] == 1


@pytest.mark.asyncio
async def test_reconciliation_retains_provider_disagreement_as_conflict(db, instrument):
    db.add_all(
        [
            _event(
                source="massive",
                key="massive:earnings:aapl:conflict",
                instrument_id=instrument.id,
                payload={"title": "Earnings", "eps_estimate": "1.25"},
            ),
            _event(
                source="fmp",
                key="fmp:earnings:aapl:conflict",
                instrument_id=instrument.id,
                payload={"title": "Earnings", "eps_estimate": "1.40"},
            ),
        ]
    )
    db.flush()

    result = await reconcile_market_events(AsyncSessionAdapter(db))

    assert result["status_counts"] == {"conflicted": 1}
    consensus = db.execute(select(MarketEventConsensus)).scalar_one()
    assert consensus.status == "conflicted"
    assert [item["field"] for item in consensus.conflict_fields] == ["eps_estimate"]
    assert consensus.canonical_payload["fields"]["title"] == "Earnings"
    assert consensus.canonical_payload["fields"].get("eps_estimate") is None


@pytest.mark.asyncio
async def test_reconciliation_does_not_group_unresolved_or_cross_date_events(db, instrument):
    unresolved = _event(
        source="massive",
        key="massive:earnings:unresolved",
        instrument_id=None,
        payload={"symbol": "AAPL"},
    )
    other_date = _event(
        source="fmp",
        key="fmp:earnings:other-date",
        instrument_id=instrument.id,
        payload={"report_date": "2026-09-16"},
    )
    other_date.effective_date = date(2026, 9, 16)
    other_date.event_time = datetime(2026, 9, 16, 20, tzinfo=UTC)
    db.add_all([unresolved, other_date])
    db.flush()

    result = await reconcile_market_events(AsyncSessionAdapter(db))

    assert result["groups"] == 1
    assert result["unresolved"] == 1
    assert unresolved.consensus_id is None
    assert db.execute(select(MarketEventConsensus)).scalar_one().effective_date == date(2026, 9, 16)


@pytest.mark.asyncio
async def test_reconciliation_reports_bounded_partial_window(db, instrument):
    db.add_all(
        [
            _event(
                source="massive",
                key=f"massive:earnings:{index}",
                instrument_id=instrument.id,
                payload={"title": f"Event {index}"},
            )
            for index in range(3)
        ]
    )
    db.flush()

    result = await reconcile_market_events(AsyncSessionAdapter(db), max_events=2)

    assert result["status"] == "partial"
    assert result["events_considered"] == 2
    assert result["truncated"] is True


@pytest.mark.asyncio
async def test_reconciliation_rejects_reversed_window(db):
    with pytest.raises(ValueError, match="on or after"):
        await reconcile_market_events(
            AsyncSessionAdapter(db),
            start=date(2026, 9, 16),
            end=date(2026, 9, 15),
        )
