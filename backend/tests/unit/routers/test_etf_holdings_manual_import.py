from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.routers import etf_holdings
from app.schemas.etf_holdings import (
    ETFHoldingsCSVIngestRequest,
    ETFHoldingsIngestRequest,
    ETFHoldingsSECIngestRequest,
    ETFHoldingsSECLegacyIngestRequest,
)


def test_manual_ingest_schemas_default_quality_to_unknown_and_keep_explicit_evidence():
    rows_default = ETFHoldingsIngestRequest(composition_date=date(2026, 10, 23), rows=[])
    csv_default = ETFHoldingsCSVIngestRequest(
        composition_date=date(2026, 10, 23), raw_csv="Ticker,Weight\nAAPL,100%\n"
    )
    rows_evidenced = ETFHoldingsIngestRequest(
        composition_date=date(2026, 10, 23),
        rows=[],
        provenance="sec_filing",
        source_quality="issuer_reported_dated_holdings",
        completeness_status="partial",
    )

    assert rows_default.provenance == "manual_import"
    assert csv_default.provenance == "manual_import"
    assert (rows_default.source_quality, rows_default.completeness_status) == (
        "unknown",
        "unknown",
    )
    assert (csv_default.source_quality, csv_default.completeness_status) == (
        "unknown",
        "unknown",
    )
    assert (
        rows_evidenced.source_quality,
        rows_evidenced.completeness_status,
        rows_evidenced.provenance,
    ) == ("issuer_reported_dated_holdings", "partial", "sec_filing")


@pytest.mark.asyncio
async def test_admin_manual_ingest_routes_are_manual_and_disable_provider_enrichment(monkeypatch):
    imported = []
    parsed = []
    instrument = SimpleNamespace(id=17)
    snapshot = SimpleNamespace(id=23)

    async def fake_ensure_instrument(*_args, **_kwargs):
        return instrument

    async def capture_ingest(_db, **kwargs):
        imported.append(kwargs)

    async def fake_latest(_db, instrument_id):
        assert instrument_id == instrument.id
        return snapshot

    monkeypatch.setattr(etf_holdings, "ensure_lightweight_etf_instrument", fake_ensure_instrument)
    monkeypatch.setattr(etf_holdings, "_ingest_snapshot_or_400", capture_ingest)
    monkeypatch.setattr(etf_holdings, "get_latest_snapshot", fake_latest)

    def parse_manual_csv(raw_csv, **kwargs):
        parsed.append((raw_csv, kwargs))
        return []

    monkeypatch.setattr(etf_holdings, "parse_holdings_csv", parse_manual_csv)

    rows_response = await etf_holdings.ingest_holdings_rows(
        "SPY",
        ETFHoldingsIngestRequest(composition_date=date(2026, 10, 23), rows=[]),
        db=object(),
        current_user=SimpleNamespace(id=1),
    )
    csv_response = await etf_holdings.ingest_holdings_csv(
        "SPY",
        ETFHoldingsCSVIngestRequest(
            composition_date=date(2026, 10, 23),
            raw_csv="Ticker,Weight\nAAPL,100%\n",
        ),
        db=object(),
        current_user=SimpleNamespace(id=1),
    )

    assert rows_response is snapshot
    assert csv_response is snapshot
    assert len(imported) == 2
    assert all(kwargs["manual_import"] is True for kwargs in imported)
    assert all(kwargs["allow_provider_enrichment"] is False for kwargs in imported)
    assert all(kwargs["provenance"] == "manual_import" for kwargs in imported)
    assert all(kwargs["source_quality"] == "unknown" for kwargs in imported)
    assert all(kwargs["completeness_status"] == "unknown" for kwargs in imported)
    assert parsed == [
        (
            "Ticker,Weight\nAAPL,100%\n",
            {"untyped_holding_type": "unknown"},
        )
    ]


@pytest.mark.asyncio
async def test_admin_sec_xml_ingest_routes_are_historical_manual_imports(monkeypatch):
    imported = []
    instrument = SimpleNamespace(id=17)
    snapshot = SimpleNamespace(id=23)

    async def fake_ensure_instrument(*_args, **_kwargs):
        return instrument

    async def capture_ingest(_db, **kwargs):
        imported.append(kwargs)

    async def fake_latest(_db, instrument_id):
        assert instrument_id == instrument.id
        return snapshot

    monkeypatch.setattr(etf_holdings, "ensure_lightweight_etf_instrument", fake_ensure_instrument)
    monkeypatch.setattr(etf_holdings, "_ingest_snapshot_or_400", capture_ingest)
    monkeypatch.setattr(etf_holdings, "get_latest_snapshot", fake_latest)
    monkeypatch.setattr(
        etf_holdings,
        "parse_sec_nport_xml",
        lambda raw_xml: (date(2026, 6, 30), [SimpleNamespace(symbol="ABC")]),
    )
    monkeypatch.setattr(
        etf_holdings,
        "parse_sec_legacy_holdings_xml",
        lambda raw_xml: (date(2026, 6, 30), [SimpleNamespace(symbol="ABC")]),
    )

    nport_response = await etf_holdings.ingest_sec_nport_holdings(
        "SECA",
        ETFHoldingsSECIngestRequest(
            raw_xml="<nport/>",
            published_at=datetime(2026, 7, 31, tzinfo=UTC),
            accession_number="0000000000-26-000001",
            filing_url="https://www.sec.gov/Archives/filing.xml",
        ),
        db=object(),
        current_user=SimpleNamespace(id=1),
    )
    legacy_response = await etf_holdings.ingest_sec_legacy_holdings(
        "SECB",
        ETFHoldingsSECLegacyIngestRequest(
            raw_xml="<legacy/>",
            published_at=datetime(2026, 8, 1, tzinfo=UTC),
            accession_number="0000000000-26-000002",
            filing_url="https://www.sec.gov/Archives/legacy.xml",
        ),
        db=object(),
        current_user=SimpleNamespace(id=1),
    )

    assert nport_response is legacy_response is snapshot
    assert len(imported) == 2
    assert all(kwargs["allow_provider_enrichment"] is False for kwargs in imported)
    assert all(kwargs["manual_import"] is True for kwargs in imported)
    assert all(kwargs["known_at"] is None for kwargs in imported)
    assert imported[0]["published_at"] == datetime(2026, 7, 31, tzinfo=UTC)
    assert imported[1]["published_at"] == datetime(2026, 8, 1, tzinfo=UTC)
    assert all(kwargs["source_provider"] == "sec" for kwargs in imported)
    assert all(kwargs["source_quality"] == "filing_reconstructed_holdings" for kwargs in imported)
    assert imported[0]["provenance"] == "sec_nport_reconstructed_holdings"
    assert imported[0]["source_identifier"] == "0000000000-26-000001"
    assert imported[0]["raw_payload_text"] == "<nport/>"
    assert imported[0]["legal_metadata"]["source_access"] == "sec_filing"
    assert imported[1]["provenance"] == "sec_legacy_reconstructed_holdings"
    assert imported[1]["source_identifier"] == "0000000000-26-000002"
    assert imported[1]["raw_payload_text"] == "<legacy/>"
    assert imported[1]["legal_metadata"]["source_format"] == "legacy_xml_table"
