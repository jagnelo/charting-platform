from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.services import etf_holdings_edgar as edgar
from app.services.etf_holdings_edgar import (
    SEC_ARCHIVES_BASE_URL,
    EdgarHoldingsFiling,
    _acceptance_datetime,
    _accession_path,
    _archive_cik,
    _date_or_none,
    _headers,
    _job_summary,
    _known_at,
    _sec_filing_identity_for_profile,
    backfill_sec_nport_holdings,
    discover_holdings_filings,
    normalize_cik,
    parse_holdings_filings_from_submissions,
    parse_legacy_holdings_filings_from_submissions,
    parse_nport_filings_from_submissions,
)
from app.services.etf_holdings_provider_bridge import (
    ETFHoldingsRouteHeldError,
    bind_etf_holdings_request_context,
)


class DummyJob:
    id = 7
    discovered_count = 5
    ingested_count = 3
    skipped_count = 1
    failed_count = 1


@pytest.mark.asyncio
async def test_sec_discovery_and_backfill_cannot_borrow_ambient_issuer_binding(monkeypatch):
    transport_calls = []
    database_writes = []
    monkeypatch.setattr(
        edgar.httpx,
        "AsyncClient",
        lambda *_args, **_kwargs: transport_calls.append("constructed"),
    )
    adapter = SimpleNamespace(adapter_key="spdr", source_provider="spdr")

    with bind_etf_holdings_request_context(
        db=object(),
        adapter=adapter,
        profile_id=17,
        instrument_id=23,
        provider_symbol="SPY",
        operation="fetch_etf_holdings_latest",
    ):
        with pytest.raises(
            ETFHoldingsRouteHeldError, match="explicit committed ETF request identity"
        ):
            await discover_holdings_filings(cik="1234567", forms={"NPORT-P"})

        class NoWriteDB:
            def add(self, _row):
                database_writes.append("add")

        with pytest.raises(ETFHoldingsRouteHeldError, match="cannot reuse an ambient"):
            await backfill_sec_nport_holdings(
                NoWriteDB(),
                profile=object(),
                max_filings=1,
            )

    assert transport_calls == []
    assert database_writes == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidate_kind, expected_status", [("none", "failed"), ("wrong_series", "partial")]
)
async def test_sec_backfill_without_qualifying_filing_is_not_completed_empty(
    monkeypatch, candidate_kind, expected_status
):
    class NoopDB:
        def add(self, _row):
            pass

        async def flush(self):
            pass

    profile = SimpleNamespace(
        id=41,
        sec_cik="0001100663",
        sec_series_id="S000058757",
        sec_class_id="C000192803",
        instrument=SimpleNamespace(id=9),
    )
    candidate = EdgarHoldingsFiling(
        accession_number="0001100663-26-000001",
        form="NPORT-P",
        filing_date=date(2026, 10, 20),
        report_date=date(2026, 9, 30),
        acceptance_datetime=None,
        primary_document="primary.xml",
        filing_url="https://www.sec.gov/Archives/edgar/data/1100663/candidate.xml",
    )
    wrong_identity = """<table><tr><td>Series ID</td><td>S000000001</td></tr>
      <tr><td>Class (Contract) ID</td><td>C000192803</td></tr></table>"""

    async def resolve_identity(**_kwargs):
        return SimpleNamespace()

    async def discover(**_kwargs):
        return [candidate] if candidate_kind == "wrong_series" else []

    async def filing_state(*_args, **_kwargs):
        return SimpleNamespace(
            snapshot_id=None,
            ingested_at=None,
            status="discovered",
            failure_reason=None,
            extra_data={},
        )

    async def sec_get(*_args, **_kwargs):
        return SimpleNamespace(
            text=wrong_identity,
            extensions={},
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr(edgar, "_resolve_request_identity", resolve_identity)
    monkeypatch.setattr(edgar, "discover_nport_filings", discover)
    monkeypatch.setattr(edgar, "_filing_state_for_accession", filing_state)
    monkeypatch.setattr(edgar, "_sec_get", sec_get)
    summary = await backfill_sec_nport_holdings(
        NoopDB(),
        profile=profile,
        max_filings=1,
    )

    assert summary["status"] == expected_status
    assert summary["ingested"] == 0
    assert summary["failures"][-1]["reason"] == "no_qualifying_filing_within_reviewed_budget"
    if candidate_kind == "wrong_series":
        assert summary["skipped"] == 1
        assert summary["failed"] == 0
    else:
        assert summary["discovered"] == 0


def test_edgar_header_and_cik_helpers():
    headers = _headers()
    assert "User-Agent" in headers
    assert headers["Accept-Encoding"] == "gzip, deflate"
    assert normalize_cik("12345") == "0000012345"
    assert _archive_cik("0000012345") == "12345"
    assert _accession_path("0001234567-24-000001") == "000123456724000001"
    with pytest.raises(ValueError):
        normalize_cik("abc")


def test_date_helpers_and_known_at():
    assert _date_or_none("2026-05-31") == date(2026, 5, 31)
    assert _date_or_none("bad") is None
    accepted = _acceptance_datetime("2026-06-01T13:45:30Z")
    assert accepted == datetime(2026, 6, 1, 13, 45, 30, tzinfo=UTC)
    filing = EdgarHoldingsFiling(
        accession_number="0001234567-24-000001",
        form="NPORT-P",
        filing_date=date(2026, 6, 1),
        report_date=date(2026, 5, 31),
        acceptance_datetime=accepted,
        primary_document="primary.xml",
        filing_url="https://sec.example/primary.xml",
    )
    observed_at = datetime(2026, 6, 2, 4, 5, tzinfo=UTC)
    assert _known_at(filing, observed_at=observed_at) == observed_at

    date_only_filing = EdgarHoldingsFiling(
        accession_number="0001234567-24-000002",
        form="NPORT-P",
        filing_date=date(2026, 6, 1),
        report_date=date(2026, 5, 31),
        acceptance_datetime=None,
        primary_document="primary.xml",
        filing_url="https://sec.example/primary.xml",
    )
    observed_at = datetime(2026, 6, 2, 4, 5, tzinfo=UTC)
    assert _known_at(date_only_filing, observed_at=observed_at) == observed_at
    assert _known_at(filing, observed_at=observed_at) == observed_at


def test_sec_backfill_requires_committed_series_and_class_identity():
    raw = """<!DOCTYPE html><html><body>
      <table><tr><td>Series ID</td><td>S000058757</td></tr>
      <tr><td>Class (Contract) ID</td><td>C000192803</td></tr></table>
    </body></html>"""
    profile = SimpleNamespace(
        sec_series_id="S000058757",
        sec_class_id="C000192803",
    )

    assert _sec_filing_identity_for_profile(profile, raw) == (
        True,
        {"series_id": "S000058757", "class_id": "C000192803"},
        "verified",
    )
    series_mismatch = _sec_filing_identity_for_profile(
        SimpleNamespace(sec_series_id="S000000000", sec_class_id="C000192803"),
        raw,
    )
    assert series_mismatch[0] is False
    assert series_mismatch[2] == "mismatch_series_id:S000058757!=S000000000"
    class_mismatch = _sec_filing_identity_for_profile(
        SimpleNamespace(sec_series_id="S000058757", sec_class_id="C000000000"),
        raw,
    )
    assert class_mismatch[0] is False
    assert class_mismatch[2] == "mismatch_class_id:C000192803!=C000000000"
    missing_filing_identity = _sec_filing_identity_for_profile(
        profile,
        "<edgarSubmission><formData><invstOrSecs /></formData></edgarSubmission>",
    )
    assert missing_filing_identity[0] is False
    assert missing_filing_identity[2] == "missing_series_id"
    assert (
        _sec_filing_identity_for_profile(
            SimpleNamespace(sec_series_id=None, sec_class_id=None),
            raw,
        )[0]
        is False
    )


def test_job_summary_uses_job_counters():
    summary = _job_summary(DummyJob(), status="completed", failures=[{"x": 1}])
    assert summary == {
        "job_id": 7,
        "status": "completed",
        "discovered": 5,
        "ingested": 3,
        "skipped": 1,
        "failed": 1,
        "failures": [{"x": 1}],
    }


def test_parse_holdings_filings_from_submissions_filters_and_builds_urls():
    submissions = {
        "filings": {
            "recent": {
                "form": ["NPORT-P", "8-K", "N-CSR"],
                "accessionNumber": [
                    "0001234567-24-000001",
                    "0001234567-24-000002",
                    "0001234567-24-000003",
                ],
                "filingDate": ["2026-06-01", "2026-05-15", "2026-04-01"],
                "reportDate": ["2026-05-31", "2026-05-14", "2026-03-31"],
                "acceptanceDateTime": [
                    "2026-06-01T13:45:30Z",
                    "2026-05-15T10:00:00Z",
                    "2026-04-01T09:00:00Z",
                ],
                "primaryDocument": ["nport.xml", "ignore.htm", "ncsr.htm"],
            }
        }
    }

    nport = parse_nport_filings_from_submissions(
        submissions,
        cik="1234567",
        start_date=date(2026, 5, 1),
    )
    legacy = parse_legacy_holdings_filings_from_submissions(submissions, cik="1234567")
    direct = parse_holdings_filings_from_submissions(
        submissions,
        cik="1234567",
        forms={"NPORT-P", "N-CSR"},
        max_filings=5,
    )

    assert len(nport) == 1
    assert nport[0].primary_document == "nport.xml"
    assert nport[0].filing_url == SEC_ARCHIVES_BASE_URL.format(
        cik="1234567",
        accession="000123456724000001",
        document="nport.xml",
    )
    assert len(legacy) == 1
    assert legacy[0].form == "N-CSR"
    assert [filing.form for filing in direct] == ["NPORT-P", "N-CSR"]
