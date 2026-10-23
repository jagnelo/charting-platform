from datetime import date
from types import SimpleNamespace

import pytest

from app.routers import etf_holdings
from app.schemas.etf_holdings import ETFHoldingsCSVIngestRequest, ETFHoldingsIngestRequest


@pytest.mark.asyncio
async def test_admin_manual_ingest_routes_are_manual_and_disable_provider_enrichment(monkeypatch):
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
    monkeypatch.setattr(etf_holdings, "parse_holdings_csv", lambda _csv: [])

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
