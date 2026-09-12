from datetime import date
from types import SimpleNamespace

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


@pytest.mark.asyncio
async def test_edgar_directory_scan_pages_unique_ciks_and_wraps_durably(db, monkeypatch):
    pages = {
        0: {
            "total": 3,
            "offset": 0,
            "limit": 2,
            "issuers": [
                {"cik": "0000000001", "name": "One", "tickers": ["ONE"]},
                {"cik": "0000000002", "name": "Two", "tickers": ["TWO"]},
            ],
        },
        2: {
            "total": 3,
            "offset": 2,
            "limit": 2,
            "issuers": [{"cik": "0000000003", "name": "Three", "tickers": ["THREE"]}],
        },
    }
    page_calls = []
    refresh_calls = []

    async def fake_execute(_db, capability, operation, **kwargs):
        assert capability.value == "market_events"
        assert operation == "discover_issuer_ciks_page"
        provider = SimpleNamespace(
            discover_issuer_ciks_page=lambda offset, *, limit: page_calls.append((offset, limit))
            or pages[offset]
        )
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    async def fake_refresh(_db, ciks, **kwargs):
        refresh_calls.append((list(ciks), kwargs))
        return {"status": "no_events", "events": 0, "failures": 0, "issuers": []}

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_event_edgar_scan, "refresh_edgar_ipo_pipeline", fake_refresh)

    first = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db), max_issuers=2, max_submissions_requests=2
    )
    second = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db), max_issuers=2, max_submissions_requests=2
    )
    third = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db), max_issuers=2, max_submissions_requests=2
    )

    state = db.execute(
        select(MarketEventScanState).where(
            MarketEventScanState.scan_key == "edgar:ipo_pipeline:sec_directory"
        )
    ).scalar_one()
    assert page_calls == [(0, 2), (2, 2), (0, 2)]
    assert refresh_calls == [
        (
            ["0000000001", "0000000002"],
            {
                "commit": False,
                "max_ciks": 2,
                "max_events_per_issuer": 100,
                "start": None,
                "end": None,
            },
        ),
        (
            ["0000000003"],
            {
                "commit": False,
                "max_ciks": 2,
                "max_events_per_issuer": 100,
                "start": None,
                "end": None,
            },
        ),
        (
            ["0000000001", "0000000002"],
            {
                "commit": False,
                "max_ciks": 2,
                "max_events_per_issuer": 100,
                "start": None,
                "end": None,
            },
        ),
    ]
    assert first["cycle_complete"] is False
    assert first["directory_offset"] == 2
    assert first["issuer_materialization_mode"] == "disabled"
    assert first["issuers_materialized"] == 0
    assert second["cycle_complete"] is True
    assert second["directory_offset"] == 0
    assert third["wrapped"] is True
    assert state.status == "partial"
    assert state.provenance["directory_offset"] == 2


@pytest.mark.asyncio
async def test_edgar_directory_scan_create_missing_materializes_only_issuers(db, monkeypatch):
    page_calls = []

    async def fake_execute(_db, capability, operation, **kwargs):
        assert capability.value == "market_events"
        assert operation == "discover_issuer_ciks_page"
        provider = SimpleNamespace(
            discover_issuer_ciks_page=lambda offset, *, limit: page_calls.append((offset, limit))
            or {
                "total": 1,
                "offset": 0,
                "limit": 2,
                "issuers": [
                    {"cik": "0000000042", "name": "Example Holdings, Inc.", "tickers": ["EXM"]}
                ],
            }
        )
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    async def fake_refresh(_db, ciks, **_kwargs):
        assert list(ciks) == ["0000000042"]
        return {"status": "no_events", "events": 0, "failures": 0, "issuers": []}

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_event_edgar_scan, "refresh_edgar_ipo_pipeline", fake_refresh)

    result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db),
        max_issuers=1,
        max_submissions_requests=1,
        issuer_materialization_mode="create_missing",
    )

    issuer = db.execute(select(Issuer).where(Issuer.cik == "0000000042")).scalar_one()
    assert page_calls == [(0, 1)]
    assert result["issuers_materialized"] == 1
    assert result["existing_issuers"] == 0
    assert issuer.domain_key == "cik:0000000042"
    assert issuer.legal_name == "Example Holdings, Inc."
    assert issuer.provenance["materialization_policy"] == "create_missing"
    assert db.execute(select(Issuer)).scalars().all()


@pytest.mark.asyncio
async def test_edgar_directory_scan_materialization_rejects_missing_name(db, monkeypatch):
    async def fake_execute(_db, _capability, _operation, **kwargs):
        provider = SimpleNamespace(
            discover_issuer_ciks_page=lambda offset, *, limit: {
                "total": 1,
                "offset": 0,
                "limit": limit,
                "issuers": [{"cik": "0000000042", "tickers": ["EXM"]}],
            }
        )
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db),
        max_issuers=1,
        max_submissions_requests=1,
        issuer_materialization_mode="create_missing",
    )

    state = db.execute(
        select(MarketEventScanState).where(
            MarketEventScanState.scan_key == "edgar:ipo_pipeline:sec_directory"
        )
    ).scalar_one()
    assert result["status"] == "failed"
    assert "requires a non-empty name" in state.last_error
    assert db.execute(select(Issuer)).scalars().all() == []


@pytest.mark.asyncio
async def test_edgar_directory_scan_rejects_unknown_materialization_mode(db):
    with pytest.raises(ValueError, match="issuer_materialization_mode"):
        # The provider call is never reached; this validates the policy gate.
        await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
            AsyncSessionAdapter(db),
            max_issuers=1,
            max_submissions_requests=1,
            issuer_materialization_mode="update_existing",
        )


@pytest.mark.asyncio
async def test_edgar_directory_scan_records_malformed_page_failure(db, monkeypatch):
    async def fake_execute(_db, _capability, _operation, **_kwargs):
        return SimpleNamespace(
            result={
                "total": 2,
                "offset": 0,
                "limit": 2,
                "issuers": [
                    {"cik": "0000000001"},
                    {"cik": "0000000001"},
                ],
            }
        )

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db), max_issuers=2, max_submissions_requests=2
    )
    state = db.execute(
        select(MarketEventScanState).where(
            MarketEventScanState.scan_key == "edgar:ipo_pipeline:sec_directory"
        )
    ).scalar_one()
    assert result["status"] == "failed"
    assert result["failures"] == 1
    assert state.status == "failed"
    assert state.last_failure_count == 1
    assert "duplicate CIK" in state.last_error


@pytest.mark.asyncio
async def test_edgar_directory_scan_requires_explicit_submissions_budget(db):
    with pytest.raises(ValueError, match="max_submissions_requests"):
        await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
            AsyncSessionAdapter(db), max_issuers=1
        )
    with pytest.raises(ValueError, match="cannot exceed"):
        await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
            AsyncSessionAdapter(db), max_issuers=2, max_submissions_requests=1
        )
