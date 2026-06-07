from datetime import UTC, date, datetime

import pytest

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
    normalize_cik,
    parse_holdings_filings_from_submissions,
    parse_legacy_holdings_filings_from_submissions,
    parse_nport_filings_from_submissions,
)


class DummyJob:
    id = 7
    discovered_count = 5
    ingested_count = 3
    skipped_count = 1
    failed_count = 1


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
    assert _known_at(filing) == accepted


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
