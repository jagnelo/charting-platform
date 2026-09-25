from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.models.instrument import Instrument
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import (
    Issuer,
    MarketEventScanState,
    SecIssuerDirectoryCandidate,
)
from app.services import market_event_edgar_scan
from tests.unit.conftest import AsyncSessionAdapter

_DIRECTORY_FINGERPRINT = "a" * 64


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
            "source_fingerprint": _DIRECTORY_FINGERPRINT,
            "issuers": [
                {"cik": "0000000001", "name": "One", "tickers": ["ONE"]},
                {"cik": "0000000002", "name": "Two", "tickers": ["TWO"]},
            ],
        },
        2: {
            "total": 3,
            "offset": 2,
            "limit": 2,
            "source_fingerprint": _DIRECTORY_FINGERPRINT,
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
    blocked_materialization = await (
        market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
            AsyncSessionAdapter(db),
            max_issuers=2,
            max_submissions_requests=2,
            issuer_materialization_mode="create_missing",
            issuer_materialization_reviewed_cycle_count=0,
        )
    )
    assert blocked_materialization["status"] == "blocked"
    assert page_calls == [(0, 2)]
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
    assert first["missing_issuer_candidates"] == 2
    assert first["cycle_missing_issuer_candidates"] == 2
    assert db.execute(select(Issuer)).scalars().all() == []
    assert second["cycle_complete"] is True
    assert second["cycle_clean"] is True
    assert second["cycle_missing_issuer_candidates"] == 3
    assert second["completed_cycle_count"] == 1
    assert second["directory_offset"] == 0
    assert third["wrapped"] is True
    assert state.status == "partial"
    assert state.provenance["directory_offset"] == 2


@pytest.mark.asyncio
async def test_edgar_directory_scan_requires_reviewed_dry_cycle_before_materialization(
    db, monkeypatch
):
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
                "source_fingerprint": _DIRECTORY_FINGERPRINT,
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

    dry_result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db),
        max_issuers=1,
        max_submissions_requests=1,
    )

    assert dry_result["status"] == "no_events"
    assert dry_result["cycle_complete"] is True
    assert dry_result["cycle_clean"] is True
    assert dry_result["missing_issuer_candidates"] == 1
    assert db.execute(select(Issuer)).scalars().all() == []
    dry_candidate = db.execute(select(SecIssuerDirectoryCandidate)).scalar_one()
    assert dry_candidate.cycle_number == 1
    assert dry_candidate.directory_total == 1
    assert dry_candidate.source_fingerprint == _DIRECTORY_FINGERPRINT
    assert dry_candidate.materialization_mode == "disabled"
    assert dry_candidate.cik == "0000000042"
    assert dry_candidate.conformed_name == "Example Holdings, Inc."
    assert dry_candidate.tickers == ["EXM"]
    assert dry_candidate.source_payload == {
        "cik": "0000000042",
        "name": "Example Holdings, Inc.",
        "tickers": ["EXM"],
    }
    assert dry_candidate.admission_decision == "would_create"
    assert dry_candidate.matched_issuer_id is None
    assert dry_candidate.cycle_status == "complete"
    assert dry_candidate.cycle_complete is True
    assert dry_candidate.cycle_clean is True
    assert db.execute(select(Instrument)).scalars().all() == []
    assert db.execute(select(InstrumentListing)).scalars().all() == []

    wrong_review = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db),
        max_issuers=1,
        max_submissions_requests=1,
        issuer_materialization_mode="create_missing",
        issuer_materialization_reviewed_cycle_count=0,
    )
    assert wrong_review["status"] == "blocked"
    assert db.execute(select(Issuer)).scalars().all() == []

    result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db),
        max_issuers=1,
        max_submissions_requests=1,
        issuer_materialization_mode="create_missing",
        issuer_materialization_reviewed_cycle_count=1,
    )
    issuer = db.execute(select(Issuer).where(Issuer.cik == "0000000042")).scalar_one()
    assert page_calls == [(0, 1), (0, 1)]
    assert result["issuers_materialized"] == 1
    assert result["existing_issuers"] == 0
    assert issuer.domain_key == "cik:0000000042"
    assert issuer.legal_name == "Example Holdings, Inc."
    assert issuer.country_code is None
    assert issuer.provenance["materialization_policy"] == "create_missing"
    assert issuer.provenance["name_source"].startswith("SEC directory conformed")
    create_candidate = db.execute(
        select(SecIssuerDirectoryCandidate).where(SecIssuerDirectoryCandidate.cycle_number == 2)
    ).scalar_one()
    assert create_candidate.admission_decision == "created"
    assert create_candidate.matched_issuer_id == issuer.id
    assert db.execute(select(Issuer)).scalars().all()
    assert db.execute(select(Instrument)).scalars().all() == []


@pytest.mark.asyncio
async def test_sec_directory_dry_report_classifies_existing_new_and_conflicted_rows(
    db, monkeypatch
):
    existing = _issuer(42)
    db.add(existing)
    db.flush()

    async def fake_execute(_db, _capability, _operation, **kwargs):
        provider = SimpleNamespace(
            discover_issuer_ciks_page=lambda offset, *, limit: {
                "total": 3,
                "offset": offset,
                "limit": limit,
                "source_fingerprint": _DIRECTORY_FINGERPRINT,
                "issuers": [
                    {
                        "cik": "0000000042",
                        "name": "Directory Name",
                        "name_candidates": ["Directory Name"],
                        "tickers": ["OLD"],
                    },
                    {
                        "cik": "0000000043",
                        "name": "New Issuer",
                        "name_candidates": ["New Issuer"],
                        "tickers": ["NEW"],
                    },
                    {
                        "cik": "0000000044",
                        "name": "Conflict A",
                        "name_candidates": ["Conflict A", "Conflict B"],
                        "tickers": ["CONFLICT"],
                    },
                ][offset : offset + limit],
            }
        )
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    async def fake_refresh(_db, ciks, **_kwargs):
        return {"status": "no_events", "events": 0, "failures": 0, "issuers": []}

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_event_edgar_scan, "refresh_edgar_ipo_pipeline", fake_refresh)

    result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db),
        max_issuers=3,
        max_submissions_requests=3,
    )

    candidates = (
        db.execute(
            select(SecIssuerDirectoryCandidate).order_by(
                SecIssuerDirectoryCandidate.directory_offset
            )
        )
        .scalars()
        .all()
    )
    assert result["cycle_complete"] is True
    assert result["cycle_clean"] is False
    assert [row.admission_decision for row in candidates] == [
        "already_exists",
        "would_create",
        "blocked_conflicting_names",
    ]
    assert candidates[0].matched_issuer_id == existing.id
    assert candidates[0].matched_issuer_legal_name == "Issuer 42"
    assert candidates[1].matched_issuer_id is None
    assert candidates[2].name_candidates == ["Conflict A", "Conflict B"]
    assert all(row.cycle_status == "complete" for row in candidates)
    assert all(row.cycle_clean is False for row in candidates)
    assert db.execute(select(Issuer).where(Issuer.cik == "0000000043")).scalar_one_or_none() is None
    assert db.execute(select(Instrument)).scalars().all() == []
    assert db.execute(select(InstrumentListing)).scalars().all() == []


@pytest.mark.asyncio
async def test_sec_directory_report_retains_all_scan_cycles(db, monkeypatch):
    async def fake_execute(_db, _capability, _operation, **kwargs):
        provider = SimpleNamespace(
            discover_issuer_ciks_page=lambda offset, *, limit: {
                "total": 1,
                "offset": offset,
                "limit": limit,
                "source_fingerprint": _DIRECTORY_FINGERPRINT,
                "issuers": [{"cik": "0000000081", "name": "Retention Test", "tickers": ["KEEP"]}],
            }
        )
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    async def fake_refresh(_db, _ciks, **_kwargs):
        return {"status": "no_events", "events": 0, "failures": 0}

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_event_edgar_scan, "refresh_edgar_ipo_pipeline", fake_refresh)

    for _ in range(4):
        result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
            AsyncSessionAdapter(db), max_issuers=1, max_submissions_requests=1
        )
        assert result["cycle_complete"] is True

    rows = (
        db.execute(
            select(SecIssuerDirectoryCandidate.cycle_number)
            .distinct()
            .order_by(SecIssuerDirectoryCandidate.cycle_number)
        )
        .scalars()
        .all()
    )
    assert rows == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_edgar_directory_scan_does_not_mutate_existing_issuer_name(db, monkeypatch):
    existing = _issuer(42)
    existing.legal_name = "Historical Legal Name"
    db.add(existing)
    db.flush()

    async def fake_execute(_db, _capability, _operation, **kwargs):
        provider = SimpleNamespace(
            discover_issuer_ciks_page=lambda offset, *, limit: {
                "total": 1,
                "offset": offset,
                "limit": limit,
                "source_fingerprint": _DIRECTORY_FINGERPRINT,
                "issuers": [
                    {"cik": "0000000042", "name": "New Directory Name", "tickers": ["EXM"]}
                ],
            }
        )
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    async def fake_refresh(_db, _ciks, **_kwargs):
        return {"status": "no_events", "events": 0, "failures": 0, "issuers": []}

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_event_edgar_scan, "refresh_edgar_ipo_pipeline", fake_refresh)

    dry_result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db), max_issuers=1, max_submissions_requests=1
    )
    assert dry_result["cycle_clean"] is True
    result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db),
        max_issuers=1,
        max_submissions_requests=1,
        issuer_materialization_mode="create_missing",
        issuer_materialization_reviewed_cycle_count=1,
    )

    issuer = db.execute(select(Issuer).where(Issuer.cik == "0000000042")).scalar_one()
    assert result["issuers_materialized"] == 0
    assert result["existing_issuers"] == 1
    assert issuer.legal_name == "Historical Legal Name"


@pytest.mark.asyncio
async def test_edgar_directory_scan_dry_scan_rejects_missing_name(db, monkeypatch):
    async def fake_execute(_db, _capability, _operation, **kwargs):
        provider = SimpleNamespace(
            discover_issuer_ciks_page=lambda offset, *, limit: {
                "total": 1,
                "offset": 0,
                "limit": limit,
                "source_fingerprint": _DIRECTORY_FINGERPRINT,
                "issuers": [{"cik": "0000000042", "tickers": ["EXM"]}],
            }
        )
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db),
        max_issuers=1,
        max_submissions_requests=1,
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
                "source_fingerprint": _DIRECTORY_FINGERPRINT,
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
async def test_edgar_directory_scan_rejects_page_larger_than_remaining_total(db, monkeypatch):
    async def fake_execute(_db, _capability, _operation, **kwargs):
        provider = SimpleNamespace(
            discover_issuer_ciks_page=lambda offset, *, limit: {
                "total": 1,
                "offset": offset,
                "limit": limit,
                "source_fingerprint": _DIRECTORY_FINGERPRINT,
                "issuers": [
                    {"cik": "0000000001", "name": "One", "tickers": ["ONE"]},
                    {"cik": "0000000002", "name": "Two", "tickers": ["TWO"]},
                ],
            }
        )
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

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
    assert "exceeds the remaining directory total" in state.last_error
    assert db.execute(select(Issuer)).scalars().all() == []


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


@pytest.mark.asyncio
async def test_edgar_directory_scan_dirty_dry_cycle_cannot_authorize_materialization(
    db, monkeypatch
):
    async def fake_execute(_db, _capability, _operation, **kwargs):
        provider = SimpleNamespace(
            discover_issuer_ciks_page=lambda offset, *, limit: {
                "total": 1,
                "offset": offset,
                "limit": limit,
                "source_fingerprint": _DIRECTORY_FINGERPRINT,
                "issuers": [{"cik": "0000000051", "name": "Dirty Issuer", "tickers": ["DIRT"]}],
            }
        )
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    async def failed_refresh(_db, _ciks, **_kwargs):
        return {"status": "partial", "events": 0, "failures": 1}

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_event_edgar_scan, "refresh_edgar_ipo_pipeline", failed_refresh)
    dry_result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db), max_issuers=1, max_submissions_requests=1
    )
    assert dry_result["cycle_complete"] is True
    assert dry_result["cycle_clean"] is False

    create_result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db),
        max_issuers=1,
        max_submissions_requests=1,
        issuer_materialization_mode="create_missing",
        issuer_materialization_reviewed_cycle_count=1,
    )
    assert create_result["status"] == "blocked"
    assert db.execute(select(Issuer)).scalars().all() == []


@pytest.mark.asyncio
async def test_edgar_directory_scan_rejects_source_drift_mid_cycle(db, monkeypatch):
    current_fingerprint = [_DIRECTORY_FINGERPRINT]
    requested_offsets = []

    async def fake_execute(_db, _capability, _operation, **kwargs):
        def page(offset, *, limit):
            requested_offsets.append(offset)
            return {
                "total": 2,
                "offset": offset,
                "limit": limit,
                "source_fingerprint": current_fingerprint[0],
                "issuers": [
                    {
                        "cik": f"{offset + 1:010d}",
                        "name": f"Issuer {offset + 1}",
                        "tickers": [f"T{offset + 1}"],
                    }
                ],
            }

        return SimpleNamespace(
            result=kwargs["invoke"](SimpleNamespace(discover_issuer_ciks_page=page), None)
        )

    async def fake_refresh(_db, _ciks, **_kwargs):
        return {"status": "no_events", "events": 0, "failures": 0}

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_event_edgar_scan, "refresh_edgar_ipo_pipeline", fake_refresh)
    first = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db), max_issuers=1, max_submissions_requests=1
    )
    current_fingerprint[0] = "b" * 64
    drifted = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db), max_issuers=1, max_submissions_requests=1
    )

    state = db.execute(
        select(MarketEventScanState).where(
            MarketEventScanState.scan_key == "edgar:ipo_pipeline:sec_directory"
        )
    ).scalar_one()
    assert first["cycle_complete"] is False
    assert drifted["status"] == "failed"
    assert drifted["directory_offset"] == 0
    assert requested_offsets == [0, 1]
    assert state.cycle_count == 0
    assert state.provenance["active_cycle_failed"] is True
    first_cycle_candidate = db.execute(
        select(SecIssuerDirectoryCandidate).where(SecIssuerDirectoryCandidate.cycle_number == 1)
    ).scalar_one()
    assert first_cycle_candidate.cycle_status == "failed"

    restarted = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db), max_issuers=1, max_submissions_requests=1
    )
    assert restarted["cycle_complete"] is False
    assert restarted["directory_offset"] == 1
    cycle_numbers = (
        db.execute(
            select(SecIssuerDirectoryCandidate.cycle_number)
            .distinct()
            .order_by(SecIssuerDirectoryCandidate.cycle_number)
        )
        .scalars()
        .all()
    )
    assert cycle_numbers == [1, 2]


@pytest.mark.asyncio
async def test_edgar_directory_scan_quarantines_conflicting_source_names(db, monkeypatch):
    async def fake_execute(_db, _capability, _operation, **kwargs):
        provider = SimpleNamespace(
            discover_issuer_ciks_page=lambda offset, *, limit: {
                "total": 1,
                "offset": offset,
                "limit": limit,
                "source_fingerprint": _DIRECTORY_FINGERPRINT,
                "issuers": [
                    {
                        "cik": "0000000061",
                        "name": "Alpha Company",
                        "name_candidates": ["Alpha Company", "Beta Company"],
                        "tickers": ["ALP", "BET"],
                    }
                ],
            }
        )
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    async def fake_refresh(_db, _ciks, **_kwargs):
        return {"status": "no_events", "events": 0, "failures": 0}

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_event_edgar_scan, "refresh_edgar_ipo_pipeline", fake_refresh)
    result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db), max_issuers=1, max_submissions_requests=1
    )

    assert result["identity_conflicts"] == ["0000000061"]
    assert result["cycle_clean"] is False
    assert result["missing_issuer_candidates"] == 1
    assert db.execute(select(Issuer)).scalars().all() == []


@pytest.mark.asyncio
async def test_edgar_directory_scan_requires_reviewed_source_fingerprint(db, monkeypatch):
    current_fingerprint = [_DIRECTORY_FINGERPRINT]

    async def fake_execute(_db, _capability, _operation, **kwargs):
        provider = SimpleNamespace(
            discover_issuer_ciks_page=lambda offset, *, limit: {
                "total": 1,
                "offset": offset,
                "limit": limit,
                "source_fingerprint": current_fingerprint[0],
                "issuers": [{"cik": "0000000071", "name": "Reviewed", "tickers": ["RVW"]}],
            }
        )
        return SimpleNamespace(result=kwargs["invoke"](provider, None))

    async def fake_refresh(_db, _ciks, **_kwargs):
        return {"status": "no_events", "events": 0, "failures": 0}

    monkeypatch.setattr(market_event_edgar_scan, "execute_provider_call", fake_execute)
    monkeypatch.setattr(market_event_edgar_scan, "refresh_edgar_ipo_pipeline", fake_refresh)
    dry_result = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db), max_issuers=1, max_submissions_requests=1
    )
    current_fingerprint[0] = "c" * 64
    changed = await market_event_edgar_scan.refresh_edgar_ipo_pipeline_for_sec_directory(
        AsyncSessionAdapter(db),
        max_issuers=1,
        max_submissions_requests=1,
        issuer_materialization_mode="create_missing",
        issuer_materialization_reviewed_cycle_count=dry_result["completed_cycle_count"],
    )
    assert changed["status"] == "failed"
    assert "source changed since the reviewed" in changed["reason"]
    assert db.execute(select(Issuer)).scalars().all() == []
