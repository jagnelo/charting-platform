from datetime import date

import pytest
from sqlalchemy import select

from app.models.market_data_foundation import Issuer, MarketEventScanState
from app.services import market_event_edgar_scan
from tests.unit.conftest import AsyncSessionAdapter


def _issuer(index: int) -> Issuer:
    cik = f"{index:010d}"
    return Issuer(
        domain_key=f"cik:{cik}",
        legal_name=f"Issuer {index}",
        cik=cik,
        country_code="US",
        provenance={"source": "unit"},
    )


@pytest.mark.asyncio
async def test_edgar_issuer_scan_advances_durable_cursor_and_marks_cycles_complete(db, monkeypatch):
    db.add_all([_issuer(1), _issuer(2), _issuer(3)])
    db.flush()
    calls = []

    async def fake_refresh(_db, ciks, **kwargs):
        calls.append((list(ciks), kwargs))
        return {
            "status": "no_events",
            "events": 0,
            "failures": 0,
            "issuers": [],
        }

    monkeypatch.setattr(market_event_edgar_scan, "refresh_edgar_ipo_pipeline", fake_refresh)

    first = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_issuer_universe(
        AsyncSessionAdapter(db),
        start=date(2025, 9, 12),
        end=date(2026, 9, 12),
        max_issuers=2,
    )
    state = db.execute(select(MarketEventScanState)).scalar_one()
    assert first["status"] == "no_events"
    assert first["cycle_complete"] is False
    assert first["issuers_considered"] == 2
    assert first["cursor_issuer_id"] == 2
    assert state.status == "partial"
    assert calls[0][0] == ["0000000001", "0000000002"]
    assert calls[0][1]["commit"] is False

    second = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_issuer_universe(
        AsyncSessionAdapter(db), max_issuers=2
    )
    state = db.execute(select(MarketEventScanState)).scalar_one()
    assert second["cycle_complete"] is True
    assert second["cursor_issuer_id"] is None
    assert second["issuers_considered"] == 1
    assert state.status == "complete"
    assert state.cycle_count == 1
    assert calls[1][0] == ["0000000003"]


@pytest.mark.asyncio
async def test_edgar_issuer_scan_wraps_after_end_and_records_failures(db, monkeypatch):
    db.add_all([_issuer(11), _issuer(12)])
    db.flush()
    calls = []

    async def fake_refresh(_db, ciks, **_kwargs):
        calls.append(list(ciks))
        return {"status": "failed", "events": 1, "failures": 1, "issuers": []}

    monkeypatch.setattr(market_event_edgar_scan, "refresh_edgar_ipo_pipeline", fake_refresh)
    await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_issuer_universe(
        AsyncSessionAdapter(db), max_issuers=1
    )
    await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_issuer_universe(
        AsyncSessionAdapter(db), max_issuers=1
    )
    state = db.execute(select(MarketEventScanState)).scalar_one()
    assert calls == [["0000000011"], ["0000000012"]]
    assert state.status == "complete"
    assert state.last_failure_count == 1
    assert state.last_event_count == 1

    wrapped = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_issuer_universe(
        AsyncSessionAdapter(db), max_issuers=1
    )
    assert wrapped["wrapped"] is True
    assert calls[-1] == ["0000000011"]


@pytest.mark.asyncio
async def test_edgar_issuer_scan_rejects_reversed_window_and_invalid_limits(db):
    with pytest.raises(ValueError, match="on or after"):
        await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_issuer_universe(
            AsyncSessionAdapter(db),
            start=date(2026, 9, 13),
            end=date(2026, 9, 12),
        )
    with pytest.raises(ValueError, match="between 1 and 500"):
        await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_issuer_universe(
            AsyncSessionAdapter(db), max_issuers=0
        )
