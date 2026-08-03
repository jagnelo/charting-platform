import json
import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

import httpx
import pytest


def _xlsx_workbook(rows: list[list[str]]) -> bytes:
    def cell_ref(column_index: int, row_index: int) -> str:
        column = ""
        value = column_index + 1
        while value:
            value, remainder = divmod(value - 1, 26)
            column = chr(ord("A") + remainder) + column
        return f"{column}{row_index}"

    sheet_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row):
            cells.append(
                f'<c r="{cell_ref(column_index, row_index)}" t="inlineStr">'
                f"<is><t>{escape(value)}</t></is></c>"
            )
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    worksheet = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w") as workbook:
        workbook.writestr("xl/worksheets/sheet1.xml", worksheet)
    return output.getvalue()


@pytest.fixture(autouse=True)
def disable_live_constituent_enrichment(monkeypatch):
    monkeypatch.setattr("app.services.etf_holdings.settings.APP_ENV", "test")


def test_admin_can_refresh_ark_provider_route(
    client, admin_headers, auth_headers, monkeypatch
):
    raw_csv = "\n".join(
        [
            "Fund Ticker,Fund Name,Ticker,Name,Weight (%),Shares,Market Value,Currency",
            "ARKK,ARK Innovation ETF,AAPL,Apple Inc.,6.1%,10,2000,USD",
            "ARKK,ARK Innovation ETF,MSFT,Microsoft Corp,5.4%,8,3200,USD",
        ]
    )

    class FakeResponse:
        text = raw_csv

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            assert url == (
                "https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
                "ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv"
            )
            assert kwargs["follow_redirects"] is True
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/ARKK/profile",
        json={
            "issuer": "ARK Invest",
            "provider_aliases": {
                "expected_fund_symbol": "ARKK",
                "holdings_composition_date": "2026-06-03",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["adapter_key"] == "ark"

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 1
    assert refresh.json()["failed"] == 0

    latest = client.get("/api/v1/etf-holdings/ARKK/latest", headers=auth_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["composition_date"] == "2026-06-03"
    assert body["provenance"] == "issuer_self_snapshotted_holdings"
    assert body["source_provider"] == "ark"
    assert body["row_count"] == 2


def test_bootstrap_endpoint_can_materialize_and_fetch_first_snapshot(
    client, auth_headers, monkeypatch
):
    async def fake_bootstrap_from_sec_filings(db, profile):
        return None

    async def fake_refresh_adapter_route(db, profile):
        from app.services.etf_holdings import ingest_holdings_snapshot
        from app.services.etf_holdings_adapters import CanonicalHoldingRow

        return await ingest_holdings_snapshot(
            db,
            etf_instrument=profile.instrument,
            rows=[
                CanonicalHoldingRow(
                    symbol="XOM",
                    name="Exxon Mobil Corp",
                    weight=Decimal("0.08000000"),
                    shares=Decimal("10"),
                    market_value=Decimal("1000"),
                    currency="USD",
                    holding_type="equity",
                    row_type="security",
                ),
                CanonicalHoldingRow(
                    symbol="CVX",
                    name="Chevron Corp",
                    weight=Decimal("0.07000000"),
                    shares=Decimal("8"),
                    market_value=Decimal("900"),
                    currency="USD",
                    holding_type="equity",
                    row_type="security",
                ),
            ],
            composition_date=date(2026, 6, 8),
            as_of_date=date(2026, 6, 8),
            known_at=None,
            provenance="issuer_self_snapshotted_holdings",
            source_provider="spdr",
            source_url="https://www.ssga.com/example/xle.xlsx",
            source_identifier="XLE",
            source_quality="self_snapshotted_holdings",
            completeness_status="unknown",
            parser_version="spdr-xlsx-v1",
            notes="Test bootstrap snapshot.",
        )

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._refresh_adapter_route",
        fake_refresh_adapter_route,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._bootstrap_from_sec_filings",
        fake_bootstrap_from_sec_filings,
    )

    response = client.post(
        "/api/v1/etf-holdings/XLE/bootstrap",
        headers=auth_headers,
        json={"name": "SPDR Select Sector Fund - Energy Select Sector"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["symbol"] == "XLE"
    assert body["profile"]["adapter_key"] == "spdr"
    assert body["refresh_attempted"] is True
    assert body["refresh_succeeded"] is True
    assert body["latest_snapshot"] is not None
    assert body["latest_snapshot"]["row_count"] == 2
    assert body["latest_snapshot"]["resolved_count"] == 2

    latest = client.get("/api/v1/etf-holdings/XLE/latest", headers=auth_headers)
    assert latest.status_code == 200
    assert latest.json()["row_count"] == 2


def test_bootstrap_endpoint_seeds_known_ishares_route_metadata(
    client, auth_headers, monkeypatch
):
    async def fake_bootstrap_from_sec_filings(db, profile):
        return None

    async def fake_refresh_adapter_route(db, profile):
        from app.services.etf_holdings import ingest_holdings_snapshot
        from app.services.etf_holdings_adapters import CanonicalHoldingRow

        assert profile.adapter_key == "ishares"
        assert profile.provider_aliases["issuer_product_id"] == "239710"

        return await ingest_holdings_snapshot(
            db,
            etf_instrument=profile.instrument,
            rows=[
                CanonicalHoldingRow(
                    symbol="AAPL",
                    name="Apple Inc.",
                    weight=Decimal("0.01000000"),
                    shares=Decimal("10"),
                    market_value=Decimal("2000"),
                    currency="USD",
                    holding_type="equity",
                    row_type="security",
                ),
            ],
            composition_date=date(2026, 6, 8),
            as_of_date=date(2026, 6, 8),
            known_at=None,
            provenance="issuer_self_snapshotted_holdings",
            source_provider="ishares",
            source_url=(
                "https://www.ishares.com/us/products/239710/"
                "?fileType=csv&fileName=IWM_holdings&dataType=fund"
            ),
            source_identifier="IWM",
            source_quality="self_snapshotted_holdings",
            completeness_status="unknown",
            parser_version="ishares-csv-v1",
            notes="Test bootstrap snapshot.",
        )

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._refresh_adapter_route",
        fake_refresh_adapter_route,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._bootstrap_from_sec_filings",
        fake_bootstrap_from_sec_filings,
    )

    response = client.post(
        "/api/v1/etf-holdings/IWM/bootstrap",
        headers=auth_headers,
        json={"name": "iShares Russell 2000 ETF"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["symbol"] == "IWM"
    assert body["profile"]["issuer"] == "iShares"
    assert body["profile"]["adapter_key"] == "ishares"
    assert body["profile"]["provider_aliases"]["issuer_product_id"] == "239710"
    assert body["probe"]["status"] == "ready"
    assert body["refresh_attempted"] is True
    assert body["refresh_succeeded"] is True
    assert body["latest_snapshot"]["row_count"] == 1


def test_bootstrap_endpoint_seeds_known_eem_ishares_route_metadata(
    client, auth_headers, monkeypatch
):
    async def fake_bootstrap_from_sec_filings(db, profile):
        return None

    async def fake_refresh_adapter_route(db, profile):
        from app.services.etf_holdings import ingest_holdings_snapshot
        from app.services.etf_holdings_adapters import CanonicalHoldingRow

        assert profile.adapter_key == "ishares"
        assert profile.provider_aliases["issuer_product_id"] == "239637"

        return await ingest_holdings_snapshot(
            db,
            etf_instrument=profile.instrument,
            rows=[
                CanonicalHoldingRow(
                    symbol="TSM",
                    name="Taiwan Semiconductor Manufacturing Co Ltd",
                    weight=Decimal("0.09000000"),
                    shares=Decimal("12"),
                    market_value=Decimal("3000"),
                    currency="USD",
                    holding_type="equity",
                    row_type="security",
                ),
            ],
            composition_date=date(2026, 6, 8),
            as_of_date=date(2026, 6, 8),
            known_at=None,
            provenance="issuer_self_snapshotted_holdings",
            source_provider="ishares",
            source_url=(
                "https://www.ishares.com/us/products/239637/"
                "?fileType=csv&fileName=EEM_holdings&dataType=fund"
            ),
            source_identifier="EEM",
            source_quality="self_snapshotted_holdings",
            completeness_status="unknown",
            parser_version="ishares-csv-v1",
            notes="Test bootstrap snapshot.",
        )

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._refresh_adapter_route",
        fake_refresh_adapter_route,
    )
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._bootstrap_from_sec_filings",
        fake_bootstrap_from_sec_filings,
    )

    response = client.post(
        "/api/v1/etf-holdings/EEM/bootstrap",
        headers=auth_headers,
        json={"name": "iShares MSCI Emerging Markets ETF"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["symbol"] == "EEM"
    assert body["profile"]["issuer"] == "iShares"
    assert body["profile"]["adapter_key"] == "ishares"
    assert body["profile"]["provider_aliases"]["issuer_product_id"] == "239637"
    assert body["profile"]["sec_cik"] == "0000930667"
    assert body["profile"]["sec_series_id"] == "S000004266"
    assert body["profile"]["sec_class_id"] == "C000011970"
    assert body["probe"]["status"] == "ready"
    assert body["refresh_attempted"] is True
    assert body["refresh_succeeded"] is True
    assert body["latest_snapshot"]["row_count"] == 1


def test_bootstrap_endpoint_falls_back_to_sec_when_invesco_refresh_route_fails(
    client, auth_headers, monkeypatch
):
    async def fake_sec_fallback(db, profile):
        from app.services.etf_holdings import ingest_holdings_snapshot
        from app.services.etf_holdings_adapters import CanonicalHoldingRow
        from app.services.etf_holdings_refresh import (
            ETFHoldingsBootstrapResult,
            probe_etf_holdings_adapter_route,
        )

        assert profile.adapter_key == "invesco"
        profile.sec_cik = "0001067839"

        await ingest_holdings_snapshot(
            db,
            etf_instrument=profile.instrument,
            rows=[
                CanonicalHoldingRow(
                    symbol="NVDA",
                    name="NVIDIA Corp",
                    weight=Decimal("0.08305722"),
                    shares=Decimal("190601606"),
                    market_value=Decimal("25000000"),
                    currency="USD",
                    holding_type="equity",
                    row_type="security",
                ),
            ],
            composition_date=date(2026, 6, 8),
            as_of_date=date(2026, 6, 8),
            known_at=None,
            provenance="issuer_self_snapshotted_holdings",
            source_provider="invesco",
            source_url="https://www.sec.gov/Archives/test/qqq-latest.xml",
            source_identifier="0001067839-test-accession",
            source_quality="filing_reconstructed_holdings",
            completeness_status="filing_reconstructed",
            parser_version="sec-nport-v1",
            notes="Test SEC bootstrap snapshot.",
        )
        probe = await probe_etf_holdings_adapter_route(db, profile)
        return ETFHoldingsBootstrapResult(
            profile=profile,
            probe=probe,
            refresh_attempted=True,
            refresh_succeeded=True,
            message="Fetched ETF holdings from the latest available SEC N-PORT filing.",
        )

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._bootstrap_from_sec_filings",
        fake_sec_fallback,
    )
    async def fake_refresh_adapter_route(*args, **kwargs):
        raise ValueError("Issuer route intentionally failed in test.")

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._refresh_adapter_route",
        fake_refresh_adapter_route,
    )
    async def fake_enrich(*args, **kwargs):
        return False
    monkeypatch.setattr(
        "app.services.etf_holdings_refresh.enrich_etf_profile_from_sec_fund_tickers",
        fake_enrich,
    )

    response = client.post(
        "/api/v1/etf-holdings/QQQ/bootstrap",
        headers=auth_headers,
        json={"name": "Invesco QQQ Trust"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["symbol"] == "QQQ"
    assert body["profile"]["issuer"] == "Invesco"
    assert body["profile"]["adapter_key"] == "invesco"
    assert body["profile"]["sec_cik"] == "0001067839"
    assert body["profile"]["sec_series_id"] == "S000101292"
    assert body["profile"]["sec_class_id"] == "C000271435"
    assert body["probe"]["status"] == "ready"
    assert body["refresh_attempted"] is True
    assert body["refresh_succeeded"] is True
    assert "SEC N-PORT" in body["message"]
    assert body["latest_snapshot"]["row_count"] == 1


def test_bootstrap_endpoint_overrides_stale_known_standard_etf_metadata(
    client, admin_headers, auth_headers, monkeypatch
):
    profile = client.patch(
        "/api/v1/etf-holdings/EEM/profile",
        headers=admin_headers,
        json={
            "issuer": "Wrong Issuer",
            "provider_aliases": {
                "issuer_product_id": "stale-product-id",
                "sec_cik": "0000000001",
            },
        },
    )
    assert profile.status_code == 200

    async def fake_refresh_adapter_route(db, profile):
        from app.services.etf_holdings import ingest_holdings_snapshot
        from app.services.etf_holdings_adapters import CanonicalHoldingRow

        assert profile.issuer == "iShares"
        assert profile.adapter_key == "ishares"
        assert profile.provider_aliases["issuer_product_id"] == "239637"
        assert profile.sec_cik == "0000930667"
        assert profile.sec_series_id == "S000004266"
        assert profile.sec_class_id == "C000011970"

        return await ingest_holdings_snapshot(
            db,
            etf_instrument=profile.instrument,
            rows=[
                CanonicalHoldingRow(
                    symbol="TSM",
                    name="Taiwan Semiconductor Manufacturing Co Ltd",
                    weight=Decimal("0.09000000"),
                    shares=Decimal("12"),
                    market_value=Decimal("3000"),
                    currency="USD",
                    holding_type="equity",
                    row_type="security",
                ),
            ],
            composition_date=date(2026, 6, 8),
            as_of_date=date(2026, 6, 8),
            known_at=None,
            provenance="issuer_self_snapshotted_holdings",
            source_provider="ishares",
            source_url="https://example.com/eem.json",
            source_identifier="EEM",
            source_quality="self_snapshotted_holdings",
            completeness_status="unknown",
            parser_version="ishares-json-v1",
            notes="Test bootstrap snapshot.",
        )

    monkeypatch.setattr(
        "app.services.etf_holdings_refresh._refresh_adapter_route",
        fake_refresh_adapter_route,
    )

    response = client.post(
        "/api/v1/etf-holdings/EEM/bootstrap",
        headers=auth_headers,
        json={"name": "iShares MSCI Emerging Markets ETF"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["issuer"] == "iShares"
    assert body["profile"]["provider_aliases"]["issuer_product_id"] == "239637"
    assert body["profile"]["sec_cik"] == "0000930667"


def test_bootstrap_endpoint_persists_profile_when_no_route_can_be_resolved(
    client, auth_headers
):
    response = client.post(
        "/api/v1/etf-holdings/MYST/bootstrap",
        headers=auth_headers,
        json={"name": "Mystery ETF"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["symbol"] == "MYST"
    assert body["profile"]["latest_snapshot_id"] is None
    assert body["refresh_attempted"] is False
    assert body["refresh_succeeded"] is False
    assert body["probe"]["status"] == "holdings_adapter_unresolved"
    assert "No configured free issuer adapter matched this ETF identity" in body["message"]

    search = client.get("/api/v1/etf-holdings?q=MYST", headers=auth_headers)
    assert search.status_code == 200
    assert search.json()[0]["symbol"] == "MYST"


def test_holdings_page_supports_server_side_paging_sorting_and_search(
    client, admin_headers, auth_headers
):
    ingest = client.post(
        "/api/v1/etf-holdings/PAGE/ingest",
        json={
            "composition_date": "2026-06-07",
            "source_provider": "manual-test",
            "rows": [
                {
                    "symbol": "LOWW",
                    "name": "Lower Weight Co",
                    "weight": "0.01000000",
                    "shares": "5",
                    "market_value": "500",
                    "currency": "USD",
                    "holding_type": "equity",
                    "row_type": "security",
                },
                {
                    "symbol": "MSFT",
                    "name": "Microsoft Corp",
                    "cusip": "594918104",
                    "weight": "0.07000000",
                    "shares": "10",
                    "market_value": "4000",
                    "currency": "USD",
                    "holding_type": "equity",
                    "row_type": "security",
                },
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "isin": "US0378331005",
                    "weight": "0.05000000",
                    "shares": "8",
                    "market_value": "2000",
                    "currency": "USD",
                    "holding_type": "equity",
                    "row_type": "security",
                },
            ],
        },
        headers=admin_headers,
    )
    assert ingest.status_code == 200

    page = client.get(
        "/api/v1/etf-holdings/PAGE/holdings?sort=weight&direction=desc&limit=2",
        headers=auth_headers,
    )
    assert page.status_code == 200
    body = page.json()
    assert body["snapshot"]["etf_symbol"] == "PAGE"
    assert body["snapshot"]["holdings"] == []
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert body["has_next"] is True
    assert [row["reported_symbol"] for row in body["holdings"]] == ["MSFT", "AAPL"]

    search = client.get(
        "/api/v1/etf-holdings/PAGE/holdings?q=594918&limit=10",
        headers=auth_headers,
    )
    assert search.status_code == 200
    search_body = search.json()
    assert search_body["total"] == 1
    assert search_body["holdings"][0]["reported_symbol"] == "MSFT"


def test_holdings_diff_reports_added_removed_and_changed_rows(
    client, admin_headers, auth_headers
):
    first = client.post(
        "/api/v1/etf-holdings/DIFF/ingest",
        json={
            "composition_date": "2026-05-31",
            "source_provider": "manual-test",
            "rows": [
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "weight": "0.04000000",
                    "shares": "10",
                    "market_value": "1000",
                    "currency": "USD",
                },
                {
                    "symbol": "MSFT",
                    "name": "Microsoft Corp",
                    "weight": "0.03000000",
                    "shares": "8",
                    "market_value": "900",
                    "currency": "USD",
                },
            ],
        },
        headers=admin_headers,
    )
    assert first.status_code == 200
    left_id = first.json()["id"]

    second = client.post(
        "/api/v1/etf-holdings/DIFF/ingest",
        json={
            "composition_date": "2026-06-01",
            "source_provider": "manual-test",
            "rows": [
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "weight": "0.06000000",
                    "shares": "12",
                    "market_value": "1300",
                    "currency": "USD",
                },
                {
                    "symbol": "NVDA",
                    "name": "NVIDIA Corp",
                    "weight": "0.02000000",
                    "shares": "5",
                    "market_value": "700",
                    "currency": "USD",
                },
            ],
        },
        headers=admin_headers,
    )
    assert second.status_code == 200
    right_id = second.json()["id"]

    diff = client.get(
        f"/api/v1/etf-holdings/DIFF/diff?left_snapshot_id={left_id}&right_snapshot_id={right_id}",
        headers=auth_headers,
    )
    assert diff.status_code == 200
    body = diff.json()
    assert body["added"] == 1
    assert body["removed"] == 1
    assert body["changed"] == 1
    assert body["unchanged"] == 0
    assert body["summary"]["gross_weight_churn"] == "0.07000000"
    assert body["summary"]["total_added_weight"] == "0.02000000"
    assert body["summary"]["total_removed_weight"] == "0.03000000"
    assert body["summary"]["total_increased_weight"] == "0.02000000"
    assert body["summary"]["total_decreased_weight"] == "0"
    assert body["summary"]["largest_additions"][0]["symbol"] == "NVDA"
    assert body["summary"]["largest_removals"][0]["symbol"] == "MSFT"
    assert body["summary"]["largest_reweights"][0]["symbol"] == "AAPL"

    rows = {row["symbol"]: row for row in body["rows"]}
    assert rows["NVDA"]["status"] == "added"
    assert rows["MSFT"]["status"] == "removed"
    assert rows["AAPL"]["status"] == "changed"
    assert rows["AAPL"]["weight_before"] == "0.04000000"
    assert rows["AAPL"]["weight_after"] == "0.06000000"
    assert rows["AAPL"]["weight_delta"] == "0.02000000"


def test_weight_evolution_reports_top_historical_weight_movers(
    client, admin_headers, auth_headers
):
    snapshots = [
        (
            "2026-05-01",
            [
                {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.04000000"},
                {"symbol": "MSFT", "name": "Microsoft Corp", "weight": "0.06000000"},
                {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": "0.02000000"},
            ],
        ),
        (
            "2026-05-15",
            [
                {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.05000000"},
                {"symbol": "MSFT", "name": "Microsoft Corp", "weight": "0.05000000"},
                {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": "0.04000000"},
            ],
        ),
        (
            "2026-06-01",
            [
                {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.07000000"},
                {"symbol": "MSFT", "name": "Microsoft Corp", "weight": "0.03000000"},
                {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": "0.03000000"},
            ],
        ),
    ]

    for composition_date, rows in snapshots:
        response = client.post(
            "/api/v1/etf-holdings/EVOL/ingest",
            json={
                "composition_date": composition_date,
                "source_provider": "manual-test",
                "rows": rows,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200

    evolution = client.get(
        "/api/v1/etf-holdings/EVOL/weight-evolution?limit=2",
        headers=auth_headers,
    )
    assert evolution.status_code == 200
    body = evolution.json()
    assert body["etf_symbol"] == "EVOL"
    assert body["snapshot_count"] == 3
    assert body["from_date"] == "2026-05-01"
    assert body["to_date"] == "2026-06-01"
    assert [row["symbol"] for row in body["series"]] == ["AAPL", "MSFT"]
    assert body["series"][0]["first_weight"] == "0.04000000"
    assert body["series"][0]["last_weight"] == "0.07000000"
    assert body["series"][0]["weight_delta"] == "0.03000000"
    assert len(body["series"][0]["points"]) == 3

    latest = client.get("/api/v1/etf-holdings/EVOL/latest", headers=auth_headers)
    assert latest.status_code == 200
    aapl_holding = next(row for row in latest.json()["holdings"] if row["reported_symbol"] == "AAPL")
    timeline = client.get(
        f"/api/v1/etf-holdings/EVOL/constituents/{aapl_holding['constituent_instrument_id']}/timeline",
        headers=auth_headers,
    )
    assert timeline.status_code == 200
    points = timeline.json()
    assert [point["composition_date"] for point in points] == [
        "2026-05-01",
        "2026-05-15",
        "2026-06-01",
    ]
    assert points[0]["weight_delta_from_previous"] is None
    assert points[1]["weight_delta_from_previous"] == "0.01000000"
    assert points[2]["weight_delta_from_previous"] == "0.02000000"


def test_transition_timeline_reports_adjacent_snapshot_churn(
    client, admin_headers, auth_headers
):
    snapshots = [
        (
            "2026-05-01",
            [
                {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.04000000"},
                {"symbol": "MSFT", "name": "Microsoft Corp", "weight": "0.06000000"},
            ],
        ),
        (
            "2026-05-15",
            [
                {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.05000000"},
            ],
        ),
        (
            "2026-06-01",
            [
                {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.03000000"},
                {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": "0.02000000"},
            ],
        ),
    ]

    for composition_date, rows in snapshots:
        response = client.post(
            "/api/v1/etf-holdings/TURN/ingest",
            json={
                "composition_date": composition_date,
                "source_provider": "manual-test",
                "rows": rows,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200

    timeline = client.get(
        "/api/v1/etf-holdings/TURN/transitions",
        headers=auth_headers,
    )
    assert timeline.status_code == 200
    body = timeline.json()
    assert body["etf_symbol"] == "TURN"
    assert body["snapshot_count"] == 3
    assert body["transition_count"] == 2
    assert body["from_date"] == "2026-05-01"
    assert body["to_date"] == "2026-06-01"
    assert len(body["transitions"]) == 2

    first = body["transitions"][0]
    assert first["left_snapshot"]["composition_date"] == "2026-05-01"
    assert first["right_snapshot"]["composition_date"] == "2026-05-15"
    assert first["added"] == 0
    assert first["removed"] == 1
    assert first["changed"] == 1
    assert first["gross_weight_churn"] == "0.07000000"
    assert first["largest_removals"][0]["symbol"] == "MSFT"
    assert first["largest_reweights"][0]["symbol"] == "AAPL"

    second = body["transitions"][1]
    assert second["left_snapshot"]["composition_date"] == "2026-05-15"
    assert second["right_snapshot"]["composition_date"] == "2026-06-01"
    assert second["added"] == 1
    assert second["removed"] == 0
    assert second["changed"] == 1
    assert second["largest_additions"][0]["symbol"] == "NVDA"
    assert second["largest_reweights"][0]["weight_delta"] == "-0.02000000"

    latest_only = client.get(
        "/api/v1/etf-holdings/TURN/transitions?limit=1",
        headers=auth_headers,
    )
    assert latest_only.status_code == 200
    latest_body = latest_only.json()
    assert latest_body["transition_count"] == 2
    assert len(latest_body["transitions"]) == 1
    assert latest_body["transitions"][0]["right_snapshot"]["composition_date"] == "2026-06-01"


def test_overlap_summary_compares_constituents_across_etfs(
    client, admin_headers, auth_headers
):
    spy = client.post(
        "/api/v1/etf-holdings/OVLA/ingest",
        json={
            "composition_date": "2026-06-07",
            "source_provider": "manual-test",
            "rows": [
                {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.07000000"},
                {"symbol": "MSFT", "name": "Microsoft Corp", "weight": "0.06000000"},
                {"symbol": "XOM", "name": "Exxon Mobil Corp", "weight": "0.02000000"},
            ],
        },
        headers=admin_headers,
    )
    assert spy.status_code == 200

    qqq = client.post(
        "/api/v1/etf-holdings/OVLB/ingest",
        json={
            "composition_date": "2026-06-07",
            "source_provider": "manual-test",
            "rows": [
                {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.12000000"},
                {"symbol": "MSFT", "name": "Microsoft Corp", "weight": "0.09000000"},
                {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": "0.08000000"},
            ],
        },
        headers=admin_headers,
    )
    assert qqq.status_code == 200

    response = client.post(
        "/api/v1/etf-holdings/overlap-summary",
        json={
            "etf_symbols": ["OVLA", "OVLB", "MISSING"],
            "snapshot_date": "2026-06-08",
            "top_n": 1,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requested_symbols"] == ["OVLA", "OVLB", "MISSING"]
    assert body["snapshot_date"] == "2026-06-08"
    assert body["point_in_time"] is True
    assert body["etf_count"] == 2
    assert body["pair_count"] == 1
    assert body["missing"] == ["MISSING"]

    pair = body["pairs"][0]
    assert pair["left_symbol"] == "OVLA"
    assert pair["right_symbol"] == "OVLB"
    assert pair["left_snapshot"]["composition_date"] == "2026-06-07"
    assert pair["right_snapshot"]["composition_date"] == "2026-06-07"
    assert pair["left_count"] == 3
    assert pair["right_count"] == 3
    assert pair["shared_count"] == 2
    assert pair["left_unique_count"] == 1
    assert pair["right_unique_count"] == 1
    assert pair["jaccard_overlap"] == "0.5"
    assert pair["shared_weight_left"] == "0.13000000"
    assert pair["shared_weight_right"] == "0.21000000"
    assert pair["overlap_weight_min"] == "0.13000000"
    assert len(pair["top_shared"]) == 1
    assert pair["top_shared"][0]["symbol"] == "AAPL"
    assert pair["top_shared"][0]["weight_left"] == "0.07000000"
    assert pair["top_shared"][0]["weight_right"] == "0.12000000"
    assert pair["top_shared"][0]["min_weight"] == "0.07000000"


def test_overlap_matrix_summarizes_many_etf_relationships(
    client, admin_headers, auth_headers
):
    payloads = {
        "OMXA": [
            {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.07000000"},
            {"symbol": "MSFT", "name": "Microsoft Corp", "weight": "0.06000000"},
            {"symbol": "XOM", "name": "Exxon Mobil Corp", "weight": "0.02000000"},
        ],
        "OMXB": [
            {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.12000000"},
            {"symbol": "MSFT", "name": "Microsoft Corp", "weight": "0.09000000"},
            {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": "0.08000000"},
        ],
        "OMXC": [
            {"symbol": "TSLA", "name": "Tesla Inc.", "weight": "0.05000000"},
            {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": "0.04000000"},
        ],
    }
    for symbol, rows in payloads.items():
        response = client.post(
            f"/api/v1/etf-holdings/{symbol}/ingest",
            json={
                "composition_date": "2026-06-07",
                "source_provider": "manual-test",
                "rows": rows,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200

    response = client.post(
        "/api/v1/etf-holdings/overlap-matrix",
        json={
            "etf_symbols": ["OMXA", "OMXB", "OMXC", "NOPE"],
            "snapshot_date": "2026-06-08",
            "metric": "jaccard",
            "top_n": 2,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requested_symbols"] == ["OMXA", "OMXB", "OMXC", "NOPE"]
    assert body["metric"] == "jaccard"
    assert body["etf_count"] == 3
    assert body["symbols"] == ["OMXA", "OMXB", "OMXC"]
    assert body["missing"] == ["NOPE"]
    assert len(body["rows"]) == 3

    omxa_row = next(row for row in body["rows"] if row["symbol"] == "OMXA")
    assert omxa_row["closest_peer"] == "OMXB"
    assert omxa_row["most_distinct_peer"] == "OMXC"
    assert omxa_row["average_overlap"] == "0.25"
    assert omxa_row["max_overlap"] == "0.5"
    assert omxa_row["min_overlap"] == "0"
    diagonal = next(cell for cell in omxa_row["cells"] if cell["column_symbol"] == "OMXA")
    assert diagonal["value"] == "1"
    omxb_cell = next(cell for cell in omxa_row["cells"] if cell["column_symbol"] == "OMXB")
    assert omxb_cell["value"] == "0.5"
    assert omxb_cell["shared_count"] == 2
    assert omxb_cell["overlap_weight_min"] == "0.13000000"

    assert body["highest_overlap_pairs"][0]["left_symbol"] == "OMXA"
    assert body["highest_overlap_pairs"][0]["right_symbol"] == "OMXB"
    assert body["lowest_overlap_pairs"][0]["left_symbol"] == "OMXA"
    assert body["lowest_overlap_pairs"][0]["right_symbol"] == "OMXC"


def test_overlap_matrix_can_expand_etf_family_from_profile_metadata(
    client, admin_headers, auth_headers
):
    payloads = {
        "FAMX": [
            {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.07000000"},
            {"symbol": "MSFT", "name": "Microsoft Corp", "weight": "0.06000000"},
        ],
        "FAMY": [
            {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.12000000"},
            {"symbol": "NVDA", "name": "NVIDIA Corp", "weight": "0.08000000"},
        ],
        "FAMZ": [
            {"symbol": "XOM", "name": "Exxon Mobil Corp", "weight": "0.05000000"},
            {"symbol": "CVX", "name": "Chevron Corp", "weight": "0.04000000"},
        ],
        "OUTX": [
            {"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.20000000"},
        ],
    }
    for symbol, rows in payloads.items():
        response = client.post(
            f"/api/v1/etf-holdings/{symbol}/ingest",
            json={
                "composition_date": "2026-06-07",
                "source_provider": "manual-test",
                "rows": rows,
            },
            headers=admin_headers,
        )
        assert response.status_code == 200
        profile = client.patch(
            f"/api/v1/etf-holdings/{symbol}/profile",
            json={
                "issuer": "Matrix Funds" if symbol.startswith("FAM") else "Outside Funds",
                "fund_family": "Core Matrix" if symbol in {"FAMX", "FAMY"} else "Other Matrix",
            },
            headers=admin_headers,
        )
        assert profile.status_code == 200

    response = client.post(
        "/api/v1/etf-holdings/overlap-matrix",
        json={
            "issuer": "Matrix",
            "fund_family": "Core",
            "snapshot_date": "2026-06-08",
            "metric": "jaccard",
            "limit": 10,
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["requested_symbols"] == ["FAMX", "FAMY"]
    assert body["symbols"] == ["FAMX", "FAMY"]
    assert body["etf_count"] == 2
    assert body["missing"] == []

    famx_row = next(row for row in body["rows"] if row["symbol"] == "FAMX")
    assert famx_row["closest_peer"] == "FAMY"
    famy_cell = next(cell for cell in famx_row["cells"] if cell["column_symbol"] == "FAMY")
    assert famy_cell["jaccard_overlap"] == "0.3333333333333333333333333333"
    assert body["highest_overlap_pairs"][0]["left_symbol"] == "FAMX"
    assert body["highest_overlap_pairs"][0]["right_symbol"] == "FAMY"


def test_admin_can_refresh_spdr_provider_xlsx_route(
    client, admin_headers, auth_headers, monkeypatch
):
    raw_workbook = _xlsx_workbook(
        [
            ["Fund Ticker", "XLY"],
            ["Fund Name", "Consumer Discretionary Select Sector SPDR Fund"],
            [],
            ["Ticker", "Name", "Weight (%)", "Shares", "Market Value", "Currency"],
            ["AMZN", "Amazon.com Inc.", "18.5%", "20", "4500", "USD"],
            ["TSLA", "Tesla Inc.", "12.1%", "12", "3000", "USD"],
        ]
    )

    class FakeResponse:
        text = ""
        content = raw_workbook
        headers = {
            "content-type": (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        }

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            assert url == (
                "https://www.ssga.com/us/en/intermediary/etfs/library-content/"
                "products/fund-data/etfs/us/holdings-daily-us-en-xly.xlsx"
            )
            assert kwargs["follow_redirects"] is True
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/XLY/profile",
        json={
            "issuer": "State Street",
            "provider_aliases": {
                "holdings_composition_date": "2026-06-06",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 1
    assert refresh.json()["failed"] == 0

    latest = client.get("/api/v1/etf-holdings/XLY/latest", headers=auth_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["composition_date"] == "2026-06-06"
    assert body["source_provider"] == "spdr"
    assert body["parser_version"] == "spdr-xlsx-v1"
    assert body["row_count"] == 2
    assert body["holdings"][0]["reported_symbol"] == "AMZN"
    assert body["holdings"][0]["weight"] == "0.18500000"
    assert body["extra_data"]["legal_metadata"]["source_format"] == "xlsx"
    validation = body["extra_data"]["legal_metadata"]["artifact_identity_validation"]
    assert validation["status"] == "matched_inferred"
    assert validation["matched"][0]["value"] == "XLY"


def test_admin_can_refresh_spdr_product_page_discovered_zip_route(
    client, admin_headers, auth_headers, monkeypatch
):
    product_url = "https://issuer.example/funds/spy"
    holdings_url = "https://issuer.example/spdr-daily-holdings.zip"
    product_html = f'<a href="{holdings_url}">Download holdings</a>'
    raw_csv = "\n".join(
        [
            "Fund Ticker,Fund Name,Ticker,Name,Weight (%),Shares,Market Value,Currency",
            "SPY,SPDR S&P 500 ETF Trust,AAPL,Apple Inc.,7.1%,100,20000,USD",
            "SPY,SPDR S&P 500 ETF Trust,NVDA,NVIDIA Corp.,6.2%,80,16000,USD",
        ]
    )
    raw_archive = BytesIO()
    with zipfile.ZipFile(raw_archive, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("readme.txt", "Issuer archive")
        archive.writestr("daily-holdings.csv", raw_csv)
    requested_urls = []

    class FakeResponse:
        def __init__(self, *, text="", content=b"", content_type="text/html"):
            self.text = text
            self.content = content or text.encode()
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            requested_urls.append(url)
            assert kwargs["follow_redirects"] is True
            if url == product_url:
                return FakeResponse(text=product_html)
            if url == holdings_url:
                return FakeResponse(
                    content=raw_archive.getvalue(),
                    content_type="application/zip",
                )
            raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/SPY/profile",
        json={
            "issuer": "State Street",
            "provider_aliases": {
                "product_url": product_url,
                "holdings_composition_date": "2026-06-06",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 1
    assert refresh.json()["failed"] == 0
    assert requested_urls == [product_url, holdings_url]

    latest = client.get("/api/v1/etf-holdings/SPY/latest", headers=auth_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["composition_date"] == "2026-06-06"
    assert body["source_provider"] == "spdr"
    assert body["parser_version"] == "spdr-zip-v1"
    assert body["row_count"] == 2
    assert body["holdings"][0]["reported_symbol"] == "AAPL"
    legal_metadata = body["extra_data"]["legal_metadata"]
    assert legal_metadata["source_format"] == "zip"
    assert legal_metadata["selected_archive_file"] == "daily-holdings.csv"
    assert legal_metadata["selected_archive_file_format"] == "csv"
    validation = legal_metadata["artifact_identity_validation"]
    assert validation["status"] == "matched_inferred"
    assert validation["matched"][0]["value"] == "SPY"


def test_refresh_failure_records_rate_limit_adapter_state(
    client, admin_headers, monkeypatch
):
    request = httpx.Request("GET", "https://issuer.example/rate-holdings.csv")
    response = httpx.Response(429, request=request)
    calls = {"count": 0}

    class RateLimitedResponse:
        text = ""
        content = b""
        headers = {"content-type": "text/csv"}

        def raise_for_status(self):
            raise httpx.HTTPStatusError("Too Many Requests", request=request, response=response)

    class SuccessfulResponse:
        text = "\n".join(
            [
                "Ticker,Name,Weight (%),Shares,Market Value,Currency",
                "AAPL,Apple Inc.,5.0%,10,2000,USD",
            ]
        )
        content = text.encode()
        headers = {"content-type": "text/csv"}

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            assert url == (
                "https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
                "ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv"
            )
            assert kwargs["follow_redirects"] is True
            calls["count"] += 1
            if calls["count"] == 1:
                return RateLimitedResponse()
            return SuccessfulResponse()

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/ARKK/profile",
        json={
            "issuer": "ARK Invest",
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 0
    assert refresh.json()["failed"] == 1

    state = client.get("/api/v1/etf-holdings/ARKK/adapter-state", headers=admin_headers)
    assert state.status_code == 200
    body = state.json()
    assert len(body) == 1
    assert body[0]["adapter_key"] == "ark"
    assert body[0]["status"] == "failure"
    assert body[0]["rate_limit_state"] == "http_429"
    assert "Too Many Requests" in body[0]["failure_reason"]
    assert body[0]["last_failure_at"] is not None

    retry = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert retry.status_code == 200
    assert retry.json()["refreshed"] == 1
    assert retry.json()["failed"] == 0

    recovered_state = client.get(
        "/api/v1/etf-holdings/ARKK/adapter-state",
        headers=admin_headers,
    )
    assert recovered_state.status_code == 200
    recovered_body = recovered_state.json()
    assert recovered_body[0]["status"] == "success"
    assert recovered_body[0]["rate_limit_state"] is None
    assert recovered_body[0]["failure_reason"] is None
    assert recovered_body[0]["last_success_at"] is not None


def test_refresh_failure_records_malformed_holdings_adapter_state(
    client, admin_headers, auth_headers, monkeypatch
):
    raw_csv = "\n".join(
        [
            "This file is a marketing disclaimer,not a holdings table",
            "Nothing useful,was published here",
        ]
    )

    class FakeResponse:
        text = raw_csv
        content = raw_csv.encode()
        headers = {"content-type": "text/csv"}

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            assert url == (
                "https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
                "ARK_SPACE_EXPLORATION_&_INNOVATION_ETF_ARKX_HOLDINGS.csv"
            )
            assert kwargs["follow_redirects"] is True
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/ARKX/profile",
        json={
            "issuer": "ARK Invest",
            "provider_aliases": {
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 0
    assert refresh.json()["failed"] == 1

    latest = client.get("/api/v1/etf-holdings/ARKX/latest", headers=auth_headers)
    assert latest.status_code == 404

    state = client.get("/api/v1/etf-holdings/ARKX/adapter-state", headers=admin_headers)
    assert state.status_code == 200
    body = state.json()
    assert body[0]["status"] == "failure"
    assert body[0]["rate_limit_state"] is None
    assert "no parseable rows" in body[0]["failure_reason"].lower()


def test_admin_can_refresh_issuer_adapter_route_without_direct_holdings_url(
    client, admin_headers, auth_headers, monkeypatch
):
    raw_csv = "\n".join(
        [
            "Fund Name,Ticker,Name,Weight (%),Shares,Market Value,Currency",
            "ARK Innovation ETF,TSLA,Tesla Inc.,9.1%,20,3600,USD",
            "ARK Innovation ETF,ROKU,Roku Inc.,4.2%,15,1200,USD",
        ]
    )
    requested_urls = []

    class FakeResponse:
        text = raw_csv

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            requested_urls.append(url)
            assert kwargs["follow_redirects"] is True
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/ARKK/profile",
        json={
            "issuer": "ARK Invest",
            "provider_aliases": {
                "holdings_file_name": "ARK_INNOVATION_ETF_ARKK_HOLDINGS",
                "expected_fund_name": "ARK Innovation ETF",
                "holdings_composition_date": "2026-06-04",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["adapter_key"] == "ark"
    assert profile.json()["adapter_status"] == "candidate"

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 1
    assert refresh.json()["skipped"] == 0
    assert requested_urls == [
        "https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
        "ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv"
    ]

    latest = client.get("/api/v1/etf-holdings/ARKK/latest", headers=auth_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["composition_date"] == "2026-06-04"
    assert body["source_provider"] == "ark"
    assert body["source_url"] == requested_urls[0]
    assert body["parser_version"] == "ark-csv-v1"
    assert body["row_count"] == 2
    assert body["extra_data"]["legal_metadata"]["artifact_identity_validation"]["status"] == "matched"


def test_admin_can_probe_ready_issuer_adapter_route(client, admin_headers):
    profile = client.patch(
        "/api/v1/etf-holdings/ARKQ/profile",
        json={
            "issuer": "ARK Invest",
            "provider_aliases": {},
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200

    probe = client.post("/api/v1/etf-holdings/ARKQ/probe-adapter", headers=admin_headers)
    assert probe.status_code == 200
    body = probe.json()
    assert body["symbol"] == "ARKQ"
    assert body["adapter_key"] == "ark"
    assert body["source_provider"] == "ark"
    assert body["status"] == "ready"
    assert body["source_url"] == (
        "https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
        "ARK_AUTONOMOUS_TECHNOLOGY_&_ROBOTICS_ETF_ARKQ_HOLDINGS.csv"
    )
    assert body["required_identifiers"] == []


def test_admin_can_list_holdings_adapter_catalog(client, admin_headers):
    response = client.get("/api/v1/etf-holdings/adapters", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    adapters = {row["adapter_key"]: row for row in body}

    assert "configured_csv_url" not in adapters

    assert "ishares" in adapters
    ishares = adapters["ishares"]
    assert ishares["source_provider"] == "ishares"
    assert ishares["required_identifiers"] == ["issuer_product_id"]
    assert ishares["supported_formats"] == ["csv", "xlsx", "zip", "json", "xml", "html"]
    assert ishares["supports_product_page_discovery"] is False
    assert ishares["live_tested_default_route"] is True
    assert ishares["supports_sec_filing_fallback"] is True
    assert ishares["support_route_types"] == [
        "issuer_native_live_route",
        "sec_edgar_filing_fallback",
    ]
    assert ishares["supports_issuer_product_id"] is True
    assert ishares["supports_dated_fetch"] is True
    assert ishares["supports_etf_discovery"] is True
    assert ishares["parser"] == "generic_holdings_table"
    assert ishares["parser_confidence"] == "medium"
    assert ishares["url_templates"] == []
    assert "ishares_dated_holdings_url_template" in ishares["route_identifiers"]
    assert "ishares_discovery_feed_url" in ishares["route_identifiers"]

    schwab = adapters["schwab"]
    assert schwab["required_identifiers"] == []
    assert schwab["product_page_templates"] == [
        "https://www.schwabassetmanagement.com/products/{symbol_lower}"
    ]
    assert schwab["live_tested_default_route"] is True
    assert schwab["supports_sec_filing_fallback"] is True
    assert schwab["support_route_types"] == [
        "issuer_native_live_route",
        "sec_edgar_filing_fallback",
    ]
    assert schwab["supports_product_page_discovery"] is True

    invesco = adapters["invesco"]
    assert invesco["live_tested_default_route"] is True
    assert any("shareclasses/{symbol_upper}/holdings/fund" in template for template in invesco["url_templates"])


def test_admin_can_discover_etf_profiles_from_issuer_feed(
    client, admin_headers, auth_headers, monkeypatch
):
    raw_csv = "\n".join(
        [
            "Ticker,Fund Name,Issuer,Product URL,Issuer Product ID,CUSIP,ISIN,"
            "FIGI,Composite FIGI,Share Class FIGI,SEC CIK,SEC Series ID,SEC Class ID,"
            "Holdings URL,Dated Holdings URL Template",
            "AAA,Alpha Allocation ETF,Example Funds,https://example.com/aaa,1001,"
            "000000101,US0000001010,BBG000000AAA,BBG00000CAAA,BBG00000SAAA,"
            "0001234567,S000000001,C000000001,"
            "https://example.com/aaa/holdings.csv,"
            "https://example.com/archive/AAA/{date_yyyymmdd}.csv",
            "BBB,Beta Builder ETF,Example Funds,https://example.com/bbb,1002,"
            "000000202,US0000002020,BBG000000BBB,BBG00000CBBB,BBG00000SBBB,"
            "0001234568,S000000002,C000000002,"
            "https://example.com/bbb/holdings.csv,"
            "https://example.com/archive/BBB/{date_yyyymmdd}.csv",
        ]
    )
    requested_urls = []

    class FakeResponse:
        text = raw_csv
        content = raw_csv.encode()
        headers = {"content-type": "text/csv"}

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            requested_urls.append(url)
            assert kwargs["follow_redirects"] is True
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_refresh.httpx.AsyncClient", FakeClient)

    response = client.post(
        "/api/v1/etf-holdings/discover",
        json={
            "adapter_key": "ishares",
            "source_url": "https://example.com/issuer-fund-list.csv",
            "issuer": "Example Funds",
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["adapter_key"] == "ishares"
    assert body["source_url"] == "https://example.com/issuer-fund-list.csv"
    assert body["discovered"] == 2
    assert body["created"] == 2
    assert body["updated"] == 0
    assert body["skipped"] == 0
    assert body["symbols"] == ["AAA", "BBB"]
    assert requested_urls == ["https://example.com/issuer-fund-list.csv"]

    listing = client.get("/api/v1/etf-holdings?q=Alpha", headers=auth_headers)
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAA"
    assert rows[0]["name"] == "Alpha Allocation ETF"
    assert rows[0]["issuer"] == "Example Funds"
    assert rows[0]["product_url"] == "https://example.com/aaa"
    assert rows[0]["adapter_key"] == "ishares"
    assert rows[0]["sec_cik"] == "0001234567"
    assert rows[0]["sec_series_id"] == "S000000001"
    assert rows[0]["sec_class_id"] == "C000000001"
    assert rows[0]["provider_aliases"]["issuer_product_id"] == "1001"
    assert rows[0]["provider_aliases"]["figi"] == "BBG000000AAA"
    assert rows[0]["provider_aliases"]["composite_figi"] == "BBG00000CAAA"
    assert rows[0]["provider_aliases"]["share_class_figi"] == "BBG00000SAAA"
    assert rows[0]["provider_aliases"]["sec_cik"] == "0001234567"
    assert rows[0]["provider_aliases"]["sec_series_id"] == "S000000001"
    assert rows[0]["provider_aliases"]["sec_class_id"] == "C000000001"
    assert rows[0]["provider_aliases"]["holdings_url"] == "https://example.com/aaa/holdings.csv"
    assert rows[0]["provider_aliases"]["dated_holdings_url_template"] == (
        "https://example.com/archive/AAA/{date_yyyymmdd}.csv"
    )
    assert rows[0]["legal_metadata"]["discovery_source_url"] == (
        "https://example.com/issuer-fund-list.csv"
    )


def test_admin_can_discover_etf_profiles_from_sec_fund_tickers(
    client, admin_headers, auth_headers, monkeypatch
):
    requested_urls = []
    payload = {
        "0": {
            "cik_str": "0001029090",
            "ticker": "VTI",
            "title": "Vanguard Total Stock Market ETF",
            "seriesId": "S000002001",
            "classId": "C000005001",
        },
        "1": {
            "cik_str": 1100663,
            "ticker": "IVV",
            "title": "iShares Core S&P 500 ETF",
            "seriesId": "S000004001",
            "classId": "C000009001",
        },
        "2": {
            "ticker": "SKIP",
            "title": "ETF Missing SEC Identity",
        },
    }

    class FakeResponse:
        def json(self):
            return payload

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            requested_urls.append(url)
            assert kwargs["follow_redirects"] is True
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_refresh.httpx.AsyncClient", FakeClient)

    response = client.post("/api/v1/etf-holdings/discover-sec-funds", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["adapter_key"] == "sec_company_tickers_mf"
    assert body["source_url"] == "https://www.sec.gov/files/company_tickers_mf.json"
    assert body["discovered"] == 3
    assert body["created"] == 2
    assert body["updated"] == 0
    assert body["skipped"] == 1
    assert body["symbols"] == ["VTI", "IVV"]
    assert requested_urls == ["https://www.sec.gov/files/company_tickers_mf.json"]

    listing = client.get("/api/v1/etf-holdings?q=Vanguard", headers=auth_headers)
    assert listing.status_code == 200
    rows = listing.json()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "VTI"
    assert rows[0]["name"] == "Vanguard Total Stock Market ETF"
    assert rows[0]["sec_cik"] == "0001029090"
    assert rows[0]["sec_series_id"] == "S000002001"
    assert rows[0]["sec_class_id"] == "C000005001"
    assert rows[0]["provider_aliases"]["sec_fund_tickers_symbol"] == "VTI"
    assert rows[0]["provider_aliases"]["sec_cik"] == "0001029090"
    assert rows[0]["provider_aliases"]["sec_series_id"] == "S000002001"
    assert rows[0]["provider_aliases"]["sec_class_id"] == "C000005001"
    assert rows[0]["legal_metadata"]["sec_fund_tickers_source_access"] == "sec_public_file"
    assert rows[0]["legal_metadata"]["sec_fund_tickers_last_row"]["ticker"] == "VTI"

    ishares_listing = client.get("/api/v1/etf-holdings?q=iShares", headers=auth_headers)
    assert ishares_listing.status_code == 200
    assert ishares_listing.json()[0]["sec_cik"] == "0001100663"


def test_admin_can_discover_sec_fund_tickers_from_fields_data_payload(
    client, admin_headers, auth_headers, monkeypatch
):
    requested_urls = []
    payload = {
        "fields": ["cik_str", "ticker", "title", "seriesId", "classId"],
        "data": [
            ["0000884394", "SPY", "SPDR S&P 500 ETF Trust", "S000030001", "C000060001"],
        ],
    }

    class FakeResponse:
        def json(self):
            return payload

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            requested_urls.append(url)
            assert kwargs["follow_redirects"] is True
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_refresh.httpx.AsyncClient", FakeClient)

    response = client.post(
        "/api/v1/etf-holdings/discover-sec-funds",
        params={"source_url": "https://mirror.example/sec-company-tickers-mf.json"},
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_url"] == "https://mirror.example/sec-company-tickers-mf.json"
    assert body["discovered"] == 1
    assert body["created"] == 1
    assert body["symbols"] == ["SPY"]
    assert requested_urls == ["https://mirror.example/sec-company-tickers-mf.json"]

    listing = client.get("/api/v1/etf-holdings?q=SPDR", headers=auth_headers)
    assert listing.status_code == 200
    rows = listing.json()
    assert rows[0]["symbol"] == "SPY"
    assert rows[0]["sec_cik"] == "0000884394"
    assert rows[0]["sec_series_id"] == "S000030001"
    assert rows[0]["sec_class_id"] == "C000060001"


def test_admin_can_probe_ready_ishares_product_id_route(client, admin_headers):
    profile = client.patch(
        "/api/v1/etf-holdings/IVV/profile",
        json={
            "issuer": "iShares",
            "provider_aliases": {"issuer_product_id": "239726"},
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["adapter_key"] == "ishares"

    probe = client.post("/api/v1/etf-holdings/IVV/probe-adapter", headers=admin_headers)
    assert probe.status_code == 200
    body = probe.json()
    assert body["symbol"] == "IVV"
    assert body["adapter_key"] == "ishares"
    assert body["source_provider"] == "ishares"
    assert body["status"] == "ready"
    assert body["source_url"] == (
        "https://www.blackrock.com/varnish-api/blk-one01-product-data/"
        "product-data/api/v2/get-product-data?appSubType=ISHARES&appType=PRODUCT_PAGE&"
        "component=holdings.all&locale=en_US&portfolioId=239726&targetSite=us-ishares&"
        "userType=individual&excludeContent=true&includeConfig=true"
    )
    assert body["required_identifiers"] == []


def test_admin_can_refresh_ishares_product_id_route(
    client, admin_headers, auth_headers, monkeypatch
):
    payload = {
        "componentsByNameMap": {
            "holdings": {
                "containersByNameMap": {
                    "all": {
                        "dataPointsByNameMap": {
                            "ticker": {"value": ["AAPL", "MSFT"]},
                            "issueName": {"value": ["Apple Inc.", "Microsoft Corp."]},
                            "cusip": {"value": ["037833100", "594918104"]},
                            "isin": {"value": ["US0378331005", "US5949181045"]},
                            "sedol": {"value": ["2046251", "2588173"]},
                            "holdingPercent": {"value": ["7.4", "6.8"]},
                            "unitsHeld": {"value": ["100", "90"]},
                            "marketValue": {"value": ["1000000", "900000"]},
                            "currencyCode": {"value": ["USD", "USD"]},
                            "countryOfRisk": {"value": ["United States", "United States"]},
                            "exchange": {"value": ["NASDAQ", "NASDAQ"]},
                            "assetClass": {"value": ["Equity", "Equity"]},
                            "sectorName": {
                                "value": [
                                    "Information Technology",
                                    "Information Technology",
                                ]
                            },
                            "asOfDate": {"value": "20260606"},
                            "fundTicker": {"value": ["IVV", "IVV"]},
                            "fundName": {
                                "value": [
                                    "iShares Core S&P 500 ETF",
                                    "iShares Core S&P 500 ETF",
                                ]
                            },
                        }
                    }
                }
            }
        }
    }
    requested_urls = []

    class FakeResponse:
        text = json.dumps(payload)
        content = text.encode()
        headers = {"content-type": "application/json"}

        def json(self):
            return payload

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            requested_urls.append(url)
            assert kwargs["follow_redirects"] is True
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/IVV/profile",
        json={
            "issuer": "iShares",
            "provider_aliases": {
                "issuer_product_id": "239726",
                "holdings_composition_date": "2026-06-06",
                "expected_fund_symbol": "IVV",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 1
    assert requested_urls == [
        "https://www.blackrock.com/varnish-api/blk-one01-product-data/"
        "product-data/api/v2/get-product-data?appSubType=ISHARES&appType=PRODUCT_PAGE&"
        "component=holdings.all&locale=en_US&portfolioId=239726&targetSite=us-ishares&"
        "userType=individual&excludeContent=true&includeConfig=true"
    ]

    latest = client.get("/api/v1/etf-holdings/IVV/latest", headers=auth_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["composition_date"] == "2026-06-06"
    assert body["source_provider"] == "ishares"
    assert body["source_url"] == requested_urls[0]
    assert body["parser_version"] == "ishares-json-v1"
    assert body["row_count"] == 2
    assert body["holdings"][0]["reported_symbol"] == "AAPL"
    assert body["holdings"][0]["country"] == "United States"
    assert body["holdings"][0]["weight"] == "0.07400000"
    validation = body["extra_data"]["legal_metadata"]["artifact_identity_validation"]
    assert validation["status"] == "matched"
    assert validation["matched"][0]["value"] == "IVV"


def test_admin_can_refresh_issuer_holdings_for_specific_date(
    client, admin_headers, auth_headers, monkeypatch
):
    raw_csv = "\n".join(
        [
            "Fund Ticker,Fund Name,Ticker,Name,Weight (%),Shares,Market Value,Currency",
            "ARKX,ARK Space Exploration ETF,IRDM,Iridium Communications,4.0%,10,700,USD",
            "ARKX,ARK Space Exploration ETF,KTOS,Kratos Defense,3.5%,12,600,USD",
        ]
    )
    requested_urls = []

    class FakeResponse:
        text = raw_csv
        content = raw_csv.encode()
        headers = {"content-type": "text/csv"}

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            requested_urls.append(url)
            assert kwargs["follow_redirects"] is True
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/ARKX/profile",
        json={
            "issuer": "ARK Invest",
            "provider_aliases": {
                "dated_holdings_url_template": (
                    "https://issuer.example/archive/{symbol}/{date_yyyymmdd}.csv"
                ),
                "expected_fund_symbol": "ARKX",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["adapter_key"] == "ark"

    refresh = client.post(
        "/api/v1/etf-holdings/ARKX/refresh-date",
        json={"requested_date": "2026-05-29"},
        headers=admin_headers,
    )
    assert refresh.status_code == 200
    body = refresh.json()
    assert body["composition_date"] == "2026-05-29"
    assert body["as_of_date"] == "2026-05-29"
    assert body["source_provider"] == "ark"
    assert body["source_url"] == "https://issuer.example/archive/ARKX/20260529.csv"
    assert body["parser_version"] == "ark-csv-v1"
    assert body["row_count"] == 2
    assert requested_urls == ["https://issuer.example/archive/ARKX/20260529.csv"]
    legal_metadata = body["extra_data"]["legal_metadata"]
    assert legal_metadata["requested_holdings_date"] == "2026-05-29"
    assert legal_metadata["route_resolution"] == "issuer_dated_profile_template"
    assert legal_metadata["artifact_identity_validation"]["status"] == "matched"

    dates = client.get("/api/v1/etf-holdings/ARKX/dates", headers=auth_headers)
    assert dates.status_code == 200
    assert dates.json()[0]["composition_date"] == "2026-05-29"


def test_issuer_adapter_can_discover_holdings_file_from_product_page(
    client, admin_headers, auth_headers, monkeypatch
):
    product_url = "https://issuer.example/funds/qqq"
    holdings_url = "https://issuer.example/downloads/qqq-holdings.csv"
    product_html = """
      <html>
        <body>
          <a href="/downloads/qqq-fact-sheet.pdf">Fact sheet</a>
          <a href="/downloads/qqq-holdings.csv">Download holdings</a>
        </body>
      </html>
    """
    raw_csv = "\n".join(
        [
            "Fund Ticker,Fund Name,Ticker,Name,Weight (%),Shares,Market Value,Currency",
            "QQQ,Invesco QQQ Trust,AAPL,Apple Inc.,8.4%,100,19000,USD",
            "QQQ,Invesco QQQ Trust,MSFT,Microsoft Corp.,7.9%,90,32000,USD",
        ]
    )
    requested_urls = []

    class FakeResponse:
        def __init__(self, text):
            self.text = text
            self.content = text.encode()
            self.headers = {"content-type": "text/html"}

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            requested_urls.append(url)
            assert kwargs["follow_redirects"] is True
            if url == product_url:
                return FakeResponse(product_html)
            if url == holdings_url:
                return FakeResponse(raw_csv)
            raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/QQQ/profile",
        json={
            "issuer": "Invesco",
            "provider_aliases": {
                "product_url": product_url,
                "expected_fund_symbol": "QQQ",
                "holdings_composition_date": "2026-06-05",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["adapter_key"] == "invesco"

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 1
    assert requested_urls == [product_url, holdings_url]

    latest = client.get("/api/v1/etf-holdings/QQQ/latest", headers=auth_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["source_provider"] == "invesco"
    assert body["source_url"] == holdings_url
    assert body["row_count"] == 2
    legal_metadata = body["extra_data"]["legal_metadata"]
    assert legal_metadata["route_resolution"] == "issuer_product_page_discovery"
    assert legal_metadata["artifact_identity_validation"]["status"] == "matched"


def test_issuer_adapter_discovers_holdings_file_from_product_page_data_attribute(
    client, admin_headers, auth_headers, monkeypatch
):
    product_url = "https://issuer.example/funds/spy"
    holdings_url = "https://issuer.example/api/portfolio/spy-holdings.xlsx?download=1"
    product_html = f"""
      <html>
        <body>
          <button data-download-url="{holdings_url}">Download portfolio</button>
        </body>
      </html>
    """
    raw_workbook = _xlsx_workbook(
        [
            ["Fund Ticker", "SPY"],
            ["Fund Name", "SPDR S&P 500 ETF Trust"],
            [],
            ["Ticker", "Name", "Weight (%)", "Shares", "Market Value", "Currency"],
            ["AAPL", "Apple Inc.", "7.2%", "100", "19000", "USD"],
            ["MSFT", "Microsoft Corp", "6.9%", "90", "32000", "USD"],
        ]
    )
    requested_urls = []

    class FakeResponse:
        def __init__(self, *, text="", content=b"", content_type="text/html"):
            self.text = text
            self.content = content or text.encode()
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            requested_urls.append(url)
            assert kwargs["follow_redirects"] is True
            if url == product_url:
                return FakeResponse(text=product_html)
            if url == holdings_url:
                return FakeResponse(
                    content=raw_workbook,
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/SPY/profile",
        json={
            "issuer": "SPDR",
            "provider_aliases": {
                "product_url": product_url,
                "expected_fund_symbol": "SPY",
                "holdings_composition_date": "2026-06-05",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["adapter_key"] == "spdr"

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 1
    assert requested_urls == [product_url, holdings_url]

    latest = client.get("/api/v1/etf-holdings/SPY/latest", headers=auth_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["source_provider"] == "spdr"
    assert body["source_url"] == holdings_url
    assert body["row_count"] == 2
    assert body["extra_data"]["legal_metadata"]["route_resolution"] == "issuer_product_page_discovery"
    assert body["extra_data"]["legal_metadata"]["source_format"] == "xlsx"


def test_issuer_adapter_discovers_holdings_from_inferred_product_page_template(
    client, admin_headers, auth_headers, monkeypatch
):
    product_url = "https://www.schwabassetmanagement.com/products/schd"
    holdings_url = "/resource/schd-portfolio-holdings.csv"
    product_html = f"""
      <html>
        <body>
          <a href="{holdings_url}">Export All Holdings</a>
        </body>
      </html>
    """
    raw_csv = "\n".join(
        [
            "Fund Ticker,Fund Name,Ticker,Name,CUSIP,Weight (%),Shares,Market Value,Currency",
            "SCHD,Schwab U.S. Dividend Equity ETF,QCOM,QUALCOMM INC,747525103,6.51%,100,6200,USD",
            "SCHD,Schwab U.S. Dividend Equity ETF,TXN,TEXAS INSTRUMENT INC,882508104,5.89%,90,5600,USD",
        ]
    )
    requested_urls = []

    class FakeResponse:
        def __init__(self, *, text="", content_type="text/html"):
            self.text = text
            self.content = text.encode()
            self.headers = {"content-type": content_type}

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            requested_urls.append(url)
            assert kwargs["follow_redirects"] is True
            if url == product_url:
                return FakeResponse(text=product_html)
            if url == "https://www.schwabassetmanagement.com/resource/schd-portfolio-holdings.csv":
                return FakeResponse(text=raw_csv, content_type="text/csv")
            raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/SCHD/profile",
        json={
            "issuer": "Schwab Asset Management",
            "provider_aliases": {
                "expected_fund_symbol": "SCHD",
                "holdings_composition_date": "2026-06-04",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["adapter_key"] == "schwab"

    probe = client.post("/api/v1/etf-holdings/SCHD/probe-adapter", headers=admin_headers)
    assert probe.status_code == 200
    probe_body = probe.json()
    assert probe_body["status"] == "ready"
    assert probe_body["source_url"] == product_url

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 1
    assert requested_urls == [
        product_url,
        "https://www.schwabassetmanagement.com/resource/schd-portfolio-holdings.csv",
    ]

    latest = client.get("/api/v1/etf-holdings/SCHD/latest", headers=auth_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["source_provider"] == "schwab"
    assert body["source_url"] == (
        "https://www.schwabassetmanagement.com/resource/schd-portfolio-holdings.csv"
    )
    assert body["row_count"] == 2
    assert body["extra_data"]["legal_metadata"]["route_resolution"] == (
        "schwab_product_page_declared_holdings_csv"
    )


def test_issuer_adapter_refresh_infers_artifact_identity_from_fund_columns(
    client, admin_headers, auth_headers, monkeypatch
):
    raw_csv = "\n".join(
        [
            "Fund Ticker,Fund Name,Ticker,Name,Weight (%),Shares,Market Value,Currency",
            "ARKQ,ARK Autonomous Technology ETF,TSLA,Tesla Inc.,8.0%,20,3600,USD",
            "ARKQ,ARK Autonomous Technology ETF,KTOS,Kratos Defense,3.0%,40,900,USD",
        ]
    )

    class FakeResponse:
        text = raw_csv

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            assert url.endswith("ARK_AUTONOMOUS_TECH_ARKQ_HOLDINGS.csv")
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/ARKQ/profile",
        json={
            "issuer": "ARK Invest",
            "provider_aliases": {
                "holdings_file_name": "ARK_AUTONOMOUS_TECH_ARKQ_HOLDINGS",
                "holdings_composition_date": "2026-06-05",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 1

    latest = client.get("/api/v1/etf-holdings/ARKQ/latest", headers=auth_headers)
    assert latest.status_code == 200
    validation = latest.json()["extra_data"]["legal_metadata"]["artifact_identity_validation"]
    assert validation["status"] == "matched_inferred"
    assert validation["matched"][0]["value"] == "ARKQ"


def test_issuer_adapter_refresh_rejects_mismatched_artifact_identity(
    client, admin_headers, auth_headers, monkeypatch
):
    raw_csv = "\n".join(
        [
            "Fund Name,Ticker,Name,Weight (%),Shares,Market Value,Currency",
            "Some Other ETF,TSLA,Tesla Inc.,9.1%,20,3600,USD",
        ]
    )

    class FakeResponse:
        text = raw_csv

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            assert url.endswith("ARK_NEXT_GENERATION_ARKW_HOLDINGS.csv")
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/ARKW/profile",
        json={
            "issuer": "ARK Invest",
            "provider_aliases": {
                "holdings_file_name": "ARK_NEXT_GENERATION_ARKW_HOLDINGS",
                "expected_fund_name": "ARK Next Generation Internet ETF",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 0
    assert refresh.json()["failed"] == 1

    latest = client.get("/api/v1/etf-holdings/ARKW/latest", headers=auth_headers)
    assert latest.status_code == 404


def test_issuer_adapter_refresh_rejects_inferred_artifact_identity_mismatch(
    client, admin_headers, auth_headers, monkeypatch
):
    raw_csv = "\n".join(
        [
            "Fund Ticker,Fund Name,Ticker,Name,Weight (%),Shares,Market Value,Currency",
            "ARKX,ARK Space Exploration ETF,TSLA,Tesla Inc.,8.0%,20,3600,USD",
        ]
    )

    class FakeResponse:
        text = raw_csv

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            assert url.endswith("ARK_GENOMIC_ARKG_HOLDINGS.csv")
            return FakeResponse()

    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/ARKG/profile",
        json={
            "issuer": "ARK Invest",
            "provider_aliases": {
                "holdings_file_name": "ARK_GENOMIC_ARKG_HOLDINGS",
            },
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    assert refresh.json()["refreshed"] == 0
    assert refresh.json()["failed"] == 1

    latest = client.get("/api/v1/etf-holdings/ARKG/latest", headers=auth_headers)
    assert latest.status_code == 404


def test_issuer_adapter_without_route_metadata_is_skipped_as_needing_route(
    client, admin_headers
):
    profile = client.patch(
        "/api/v1/etf-holdings/WTST/profile",
        json={"issuer": "WisdomTree"},
        headers=admin_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["adapter_key"] == "wisdomtree"

    refresh = client.post("/api/v1/etf-holdings/refresh", headers=admin_headers)
    assert refresh.status_code == 200
    body = refresh.json()
    assert body["refreshed"] == 0
    assert body["skipped"] == 1
    assert body["failed"] == 0


def test_profile_product_url_domain_routes_adapter_without_name_guessing(
    client, admin_headers
):
    profile = client.patch(
        "/api/v1/etf-holdings/DOMAIN/profile",
        json={
            "product_url": "https://investor.vanguard.com/investment-products/etfs/profile/domain",
        },
        headers=admin_headers,
    )
    assert profile.status_code == 200
    body = profile.json()
    assert body["adapter_key"] == "vanguard"
    assert body["adapter_status"] == "candidate"
    assert body["adapter_confidence"] == "0.8500"

    probe = client.post("/api/v1/etf-holdings/DOMAIN/probe-adapter", headers=admin_headers)
    assert probe.status_code == 200
    probe_body = probe.json()
    assert probe_body["adapter_key"] == "vanguard"
    assert probe_body["status"] == "ready"
    assert probe_body["source_url"] == (
        "https://investor.vanguard.com/investment-products/etfs/profile/domain"
    )


def test_admin_can_probe_ready_spdr_symbol_route(client, admin_headers):
    profile = client.patch(
        "/api/v1/etf-holdings/SPY/profile",
        json={"issuer": "State Street Global Advisors"},
        headers=admin_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["adapter_key"] == "spdr"

    probe = client.post("/api/v1/etf-holdings/SPY/probe-adapter", headers=admin_headers)
    assert probe.status_code == 200
    body = probe.json()
    assert body["symbol"] == "SPY"
    assert body["adapter_key"] == "spdr"
    assert body["status"] == "ready"
    assert body["source_url"] == (
        "https://www.ssga.com/us/en/intermediary/etfs/library-content/"
        "products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
    )
    assert body["required_identifiers"] == []


def test_profile_ticker_alone_does_not_guess_issuer_adapter(client, admin_headers):
    profile = client.patch(
        "/api/v1/etf-holdings/VOO/profile",
        json={},
        headers=admin_headers,
    )
    assert profile.status_code == 200
    body = profile.json()
    assert body["adapter_key"] == "unresolved"
    assert body["adapter_status"] == "holdings_adapter_unresolved"


def test_admin_probe_uses_sec_identifiers_as_vanguard_support_route(client, admin_headers):
    profile = client.patch(
        "/api/v1/etf-holdings/VOOG/profile",
        json={"issuer": "Vanguard", "sec_cik": "0000036405"},
        headers=admin_headers,
    )
    assert profile.status_code == 200

    probe = client.post("/api/v1/etf-holdings/VOOG/probe-adapter", headers=admin_headers)
    assert probe.status_code == 200
    body = probe.json()
    assert body["symbol"] == "VOOG"
    assert body["adapter_key"] == "vanguard"
    assert body["status"] == "ready"
    assert body["required_identifiers"] == []
    assert body["source_url"] == "https://data.sec.gov/submissions/CIK0000036405.json"


def test_admin_can_probe_invesco_as_ready_symbol_route(client, admin_headers):
    profile = client.patch(
        "/api/v1/etf-holdings/QQQ/profile",
        json={"issuer": "Invesco"},
        headers=admin_headers,
    )
    assert profile.status_code == 200
    assert profile.json()["adapter_key"] == "invesco"

    probe = client.post("/api/v1/etf-holdings/QQQ/probe-adapter", headers=admin_headers)
    assert probe.status_code == 200
    body = probe.json()
    assert body["symbol"] == "QQQ"
    assert body["adapter_key"] == "invesco"
    assert body["source_provider"] == "invesco"
    assert body["status"] == "ready"
    assert "shareclasses/QQQ/holdings/fund" in body["source_url"]
    assert body["required_identifiers"] == []


def test_admin_can_ingest_and_user_can_read_etf_holdings(client, admin_headers, auth_headers):
    payload = {
        "composition_date": "2026-05-31",
        "provenance": "issuer_current_holdings",
        "source_provider": "issuer-test",
        "source_quality": "issuer_current",
        "completeness_status": "complete",
        "rows": [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "weight": "0.0625",
                "shares": "100",
                "market_value": "19500",
                "currency": "USD",
            },
            {
                "symbol": "MSFT",
                "name": "Microsoft Corporation",
                "weight": "0.055",
                "shares": "80",
                "market_value": "32000",
                "currency": "USD",
            },
            {
                "name": "US Dollar",
                "weight": "0.002",
                "holding_type": "cash",
                "row_type": "cash",
                "currency": "USD",
            },
        ],
    }

    ingest = client.post("/api/v1/etf-holdings/SPY/ingest", json=payload, headers=admin_headers)
    assert ingest.status_code == 200
    body = ingest.json()
    assert body["etf_symbol"] == "SPY"
    assert body["row_count"] == 3
    assert body["resolved_count"] == 2
    assert body["unresolved_count"] == 1
    assert body["holdings"][0]["constituent_symbol"] == "AAPL"
    assert len(body["holdings"][0]["source_row_hash"]) == 64
    assert body["holdings"][0]["source_row_hash"] != body["holdings"][1]["source_row_hash"]
    assert body["holdings"][2]["row_type"] == "cash"

    latest = client.get("/api/v1/etf-holdings/SPY/latest", headers=auth_headers)
    assert latest.status_code == 200
    latest_body = latest.json()
    assert latest_body["composition_date"] == "2026-05-31"
    assert latest_body["source_provider"] == "issuer-test"

    search = client.get("/api/v1/etf-holdings", headers=auth_headers)
    assert search.status_code == 200
    assert search.json()[0]["symbol"] == "SPY"


def test_etf_holdings_snapshot_can_materialize_read_only_basket(
    client,
    admin_headers,
    auth_headers,
):
    ingest = client.post(
        "/api/v1/etf-holdings/DIA/ingest",
        json={
            "composition_date": "2026-05-31",
            "provenance": "issuer_current_holdings",
            "source_provider": "issuer-test",
            "rows": [
                {
                    "symbol": "AAPL",
                    "name": "Apple Inc.",
                    "weight": "0.04",
                    "shares": "100",
                },
                {
                    "symbol": "MSFT",
                    "name": "Microsoft Corporation",
                    "weight": "0.03",
                    "shares": "80",
                },
                {
                    "name": "US Dollar",
                    "weight": "0.01",
                    "holding_type": "cash",
                    "row_type": "cash",
                    "currency": "USD",
                },
            ],
        },
        headers=admin_headers,
    )
    assert ingest.status_code == 200

    materialized = client.get("/api/v1/etf-holdings/DIA/basket", headers=auth_headers)
    assert materialized.status_code == 200
    basket = materialized.json()
    assert basket["source_type"] == "etf_holdings"
    assert basket["is_system_managed"] is True
    assert basket["is_read_only"] is True
    assert basket["composition_date"] == "2026-05-31"
    assert basket["metadata"]["etf_symbol"] == "DIA"
    assert [member["symbol"] for member in basket["members"]] == ["AAPL", "MSFT"]
    assert basket["members"][0]["weight"] == "0.04000000"

    listed = client.get("/api/v1/baskets", headers=auth_headers)
    assert listed.status_code == 200
    assert any(row["id"] == basket["id"] for row in listed.json())

    read = client.get(f"/api/v1/baskets/{basket['id']}", headers=auth_headers)
    assert read.status_code == 200
    assert read.json()["source_snapshot_id"] == basket["source_snapshot_id"]


def test_csv_ingestion_normalizes_common_issuer_columns(client, admin_headers, auth_headers):
    raw_csv = "\n".join(
        [
            "Ticker,Name,Weight (%),Shares,Market Value,Currency,CUSIP",
            "NVDA,NVIDIA Corp,4.2%,12,12000,USD,67066G104",
            "CASH,US Dollar,0.5%,,,USD,",
        ]
    )
    response = client.post(
        "/api/v1/etf-holdings/QQQ/ingest-csv",
        json={
            "composition_date": "2026-06-01",
            "source_provider": "csv-test",
            "raw_csv": raw_csv,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["holdings"][0]["reported_symbol"] == "NVDA"
    assert body["holdings"][0]["weight"] == "0.04200000"

    dates = client.get("/api/v1/etf-holdings/QQQ/dates", headers=auth_headers)
    assert dates.status_code == 200
    assert dates.json()[0]["composition_date"] == "2026-06-01"


def test_csv_ingestion_normalizes_broader_issuer_schema_variants(
    client, admin_headers, auth_headers
):
    raw_csv = "\n".join(
        [
            "Name of Issuer,Security Identifier,% of Fund,Shares/Par Value,Market Value ($),Local Currency,Country,Exchange",
            "Apple Inc.,037833100,6.2%,\"1,250\",\"$240,000\",USD,United States,NASDAQ",
            "US Dollar,CASH,0.5%,,,USD,United States,",
            "Disclaimer,,,,,,,",
        ]
    )
    response = client.post(
        "/api/v1/etf-holdings/SCHEMA/ingest-csv",
        json={
            "composition_date": "2026-06-02",
            "source_provider": "schema-test",
            "raw_csv": raw_csv,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["row_count"] == 2
    assert body["holdings"][0]["reported_name"] == "Apple Inc."
    assert body["holdings"][0]["cusip"] == "037833100"
    assert body["holdings"][0]["weight"] == "0.06200000"
    assert body["holdings"][0]["shares"] == "1250.00000000"
    assert body["holdings"][0]["market_value"] == "240000.000000"
    assert body["holdings"][0]["currency"] == "USD"
    assert body["holdings"][1]["row_type"] == "cash"

    latest = client.get("/api/v1/etf-holdings/SCHEMA/latest", headers=auth_headers)
    assert latest.status_code == 200
    assert latest.json()["row_count"] == 2


def test_sec_nport_ingestion_reconstructs_filing_holdings(client, admin_headers, auth_headers):
    raw_xml = """
    <edgarSubmission>
      <formData>
        <generalInfo>
          <repPdDate>2026-03-31</repPdDate>
        </generalInfo>
        <invstOrSecs>
          <invstOrSec>
            <name>Apple Inc.</name>
            <title>Apple Inc Common Stock</title>
            <cusip>037833100</cusip>
            <balance>125</balance>
            <valUSD>24000</valUSD>
            <pctVal>6.25</pctVal>
            <curCd>USD</curCd>
            <assetCat>Equity</assetCat>
          </invstOrSec>
          <invstOrSec>
            <name>Microsoft Corporation</name>
            <cusip>594918104</cusip>
            <balance>80</balance>
            <valUSD>32000</valUSD>
            <pctVal>5.5</pctVal>
            <curCd>USD</curCd>
            <assetCat>Equity</assetCat>
          </invstOrSec>
        </invstOrSecs>
      </formData>
    </edgarSubmission>
    """

    response = client.post(
        "/api/v1/etf-holdings/VTI/ingest-sec-nport",
        json={
            "raw_xml": raw_xml,
            "published_at": "2026-05-01T12:00:00Z",
            "accession_number": "0000000000-26-000001",
            "filing_url": "https://www.sec.gov/Archives/example.xml",
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["composition_date"] == "2026-03-31"
    assert body["as_of_date"] == "2026-03-31"
    assert body["known_at"] == "2026-05-01T12:00:00Z"
    assert body["provenance"] == "sec_nport_reconstructed_holdings"
    assert body["source_quality"] == "filing_reconstructed_holdings"
    assert body["source_identifier"] == "0000000000-26-000001"
    assert body["holdings"][0]["reported_name"] == "Apple Inc."
    assert body["holdings"][0]["cusip"] == "037833100"
    assert body["holdings"][0]["weight"] == "0.06250000"

    latest = client.get("/api/v1/etf-holdings/VTI/latest", headers=auth_headers)
    assert latest.status_code == 200
    assert latest.json()["parser_version"] == "sec-nport-v1"


def test_sec_legacy_ingestion_reconstructs_table_like_filing_holdings(
    client, admin_headers, auth_headers
):
    raw_xml = """
    <filing>
      <periodOfReport>2018-12-31</periodOfReport>
      <scheduleOfInvestments>
        <investment>
          <issuerName>Apple Inc.</issuerName>
          <ticker>AAPL</ticker>
          <cusip>037833100</cusip>
          <shares>125</shares>
          <marketValue>24000</marketValue>
          <percentageOfNetAssets>6.25</percentageOfNetAssets>
          <currency>USD</currency>
          <securityType>Common Stock</securityType>
        </investment>
        <investment>
          <issuerName>Microsoft Corporation</issuerName>
          <ticker>MSFT</ticker>
          <cusip>594918104</cusip>
          <shares>80</shares>
          <marketValue>32000</marketValue>
          <percentageOfNetAssets>5.5</percentageOfNetAssets>
          <currency>USD</currency>
          <securityType>Common Stock</securityType>
        </investment>
      </scheduleOfInvestments>
    </filing>
    """

    response = client.post(
        "/api/v1/etf-holdings/IVV/ingest-sec-legacy",
        json={
            "raw_xml": raw_xml,
            "published_at": "2019-02-01T12:00:00Z",
            "accession_number": "0000000000-19-000001",
            "filing_url": "https://www.sec.gov/Archives/legacy-example.xml",
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["composition_date"] == "2018-12-31"
    assert body["as_of_date"] == "2018-12-31"
    assert body["known_at"] == "2019-02-01T12:00:00Z"
    assert body["provenance"] == "sec_legacy_reconstructed_holdings"
    assert body["source_quality"] == "filing_reconstructed_holdings"
    assert body["source_identifier"] == "0000000000-19-000001"
    assert body["parser_version"] == "sec-legacy-v1"
    assert body["holdings"][0]["reported_symbol"] == "AAPL"
    assert body["holdings"][0]["cusip"] == "037833100"
    assert body["holdings"][0]["weight"] == "0.06250000"
    assert body["extra_data"]["legal_metadata"]["source_format"] == "legacy_xml_table"

    latest = client.get("/api/v1/etf-holdings/IVV/latest", headers=auth_headers)
    assert latest.status_code == 200
    assert latest.json()["provenance"] == "sec_legacy_reconstructed_holdings"


def test_sec_legacy_ingestion_reconstructs_html_table_filing_holdings(
    client, admin_headers, auth_headers
):
    raw_html = """
    <html>
      <body>
        <p>Period of Report: 2017-06-30</p>
        <table>
          <tr>
            <th>Issuer Name</th>
            <th>Ticker</th>
            <th>CUSIP</th>
            <th>Shares</th>
            <th>Market Value</th>
            <th>Percent of Net Assets</th>
            <th>Currency</th>
            <th>Security Type</th>
          </tr>
          <tr>
            <td>Apple Inc.</td>
            <td>AAPL</td>
            <td>037833100</td>
            <td>125</td>
            <td>$24,000</td>
            <td>6.25%</td>
            <td>USD</td>
            <td>Common Stock</td>
          </tr>
          <tr>
            <td>Microsoft Corporation</td>
            <td>MSFT</td>
            <td>594918104</td>
            <td>80</td>
            <td>$32,000</td>
            <td>5.50%</td>
            <td>USD</td>
            <td>Common Stock</td>
          </tr>
        </table>
      </body>
    </html>
    """

    response = client.post(
        "/api/v1/etf-holdings/VHT/ingest-sec-legacy",
        json={
            "raw_xml": raw_html,
            "published_at": "2017-08-01T12:00:00Z",
            "accession_number": "0000000000-17-000001",
            "filing_url": "https://www.sec.gov/Archives/legacy-example.htm",
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["composition_date"] == "2017-06-30"
    assert body["known_at"] == "2017-08-01T12:00:00Z"
    assert body["provenance"] == "sec_legacy_reconstructed_holdings"
    assert body["parser_version"] == "sec-legacy-v1"
    assert body["holdings"][0]["reported_symbol"] == "AAPL"
    assert body["holdings"][0]["reported_name"] == "Apple Inc."
    assert body["holdings"][0]["cusip"] == "037833100"
    assert body["holdings"][0]["weight"] == "0.06250000"

    latest = client.get("/api/v1/etf-holdings/VHT/latest", headers=auth_headers)
    assert latest.status_code == 200
    assert len(latest.json()["holdings"]) == 2


def test_sec_legacy_ingestion_reconstructs_split_identity_html_rows(
    client, admin_headers, auth_headers
):
    raw_html = """
    <html>
      <body>
        <p>Period of Report: 2016-12-31</p>
        <table>
          <tr>
            <th>Description</th>
            <th>Shares Held</th>
            <th>Investment Value</th>
            <th>% of Net Assets</th>
          </tr>
          <tr>
            <td>Apple Inc. Common Stock CUSIP 037833100</td>
            <td></td>
            <td></td>
            <td></td>
          </tr>
          <tr>
            <td></td>
            <td>125</td>
            <td>$24,000</td>
            <td>6.25%</td>
          </tr>
          <tr>
            <td>Microsoft Corporation Common Stock CUSIP 594918104</td>
            <td></td>
            <td></td>
            <td></td>
          </tr>
          <tr>
            <td></td>
            <td>80</td>
            <td>$32,000</td>
            <td>5.50%</td>
          </tr>
        </table>
      </body>
    </html>
    """

    response = client.post(
        "/api/v1/etf-holdings/VCR/ingest-sec-legacy",
        json={
            "raw_xml": raw_html,
            "published_at": "2017-02-24T12:00:00Z",
            "accession_number": "0000000000-17-000002",
            "filing_url": "https://www.sec.gov/Archives/legacy-split-rows.htm",
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["composition_date"] == "2016-12-31"
    assert body["known_at"] == "2017-02-24T12:00:00Z"
    assert len(body["holdings"]) == 2
    assert body["holdings"][0]["reported_name"] == "Apple Inc. Common Stock CUSIP 037833100"
    assert body["holdings"][0]["cusip"] == "037833100"
    assert body["holdings"][0]["shares"] == "125.00000000"
    assert body["holdings"][0]["market_value"] == "24000.000000"
    assert body["holdings"][0]["weight"] == "0.06250000"
    assert body["holdings"][1]["reported_name"] == "Microsoft Corporation Common Stock CUSIP 594918104"
    assert body["holdings"][1]["cusip"] == "594918104"

    latest = client.get("/api/v1/etf-holdings/VCR/latest", headers=auth_headers)
    assert latest.status_code == 200
    assert len(latest.json()["holdings"]) == 2


def test_sec_legacy_ingestion_handles_month_name_dates_and_value_thousands(
    client, admin_headers, auth_headers
):
    raw_html = """
    <html>
      <body>
        <p>Schedule of Investments as of June 30, 2015</p>
        <table>
          <tr>
            <th>Name of Issuer</th>
            <th>Title of Issue</th>
            <th>CUSIP Number</th>
            <th>Shares or Principal Amount</th>
            <th>Value (000s)</th>
            <th>% Net Assets</th>
          </tr>
          <tr>
            <td>Apple Inc.</td>
            <td>Common Stock</td>
            <td>037833100</td>
            <td>125</td>
            <td>24</td>
            <td>6.25%</td>
          </tr>
          <tr>
            <td>Microsoft Corporation</td>
            <td>Common Stock</td>
            <td>594918104</td>
            <td>80</td>
            <td>32</td>
            <td>5.50%</td>
          </tr>
        </table>
      </body>
    </html>
    """

    response = client.post(
        "/api/v1/etf-holdings/VLEG/ingest-sec-legacy",
        json={
            "raw_xml": raw_html,
            "published_at": "2015-08-15T12:00:00Z",
            "accession_number": "0000000000-15-000001",
            "filing_url": "https://www.sec.gov/Archives/legacy-thousands.htm",
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["composition_date"] == "2015-06-30"
    assert body["known_at"] == "2015-08-15T12:00:00Z"
    assert len(body["holdings"]) == 2
    assert body["holdings"][0]["reported_name"] == "Apple Inc."
    assert body["holdings"][0]["cusip"] == "037833100"
    assert body["holdings"][0]["shares"] == "125.00000000"
    assert body["holdings"][0]["market_value"] == "24000.000000"
    assert body["holdings"][0]["weight"] == "0.06250000"

    latest = client.get("/api/v1/etf-holdings/VLEG/latest", headers=auth_headers)
    assert latest.status_code == 200
    assert latest.json()["composition_date"] == "2015-06-30"


def test_sec_nport_backfill_discovers_and_ingests_edgar_filings(
    client, admin_headers, auth_headers, monkeypatch
):
    submissions = {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "accessionNumber": ["0000000000-26-000000"],
                "filingDate": ["2026-02-01"],
                "reportDate": ["2025-12-31"],
                "acceptanceDateTime": ["2026-02-01T12:00:00.000Z"],
                "primaryDocument": ["form10k.htm"],
            },
            "files": [
                {
                    "name": "CIK0001029090-submissions-001.json",
                    "filingFrom": "2026-01-01",
                    "filingTo": "2026-12-31",
                    "filingCount": 1,
                }
            ],
        }
    }
    archived_submissions = {
        "form": ["NPORT-P"],
        "accessionNumber": ["0001029090-26-000001"],
        "filingDate": ["2026-05-01"],
        "reportDate": ["2026-03-31"],
        "acceptanceDateTime": ["2026-05-01T15:30:00.000Z"],
        "primaryDocument": ["primary_doc.xml"],
    }
    raw_xml = """
    <edgarSubmission>
      <formData>
        <generalInfo>
          <repPdDate>2026-03-31</repPdDate>
        </generalInfo>
        <invstOrSecs>
          <invstOrSec>
            <name>Apple Inc.</name>
            <cusip>037833100</cusip>
            <balance>125</balance>
            <valUSD>24000</valUSD>
            <pctVal>6.25</pctVal>
            <curCd>USD</curCd>
            <assetCat>Equity</assetCat>
          </invstOrSec>
        </invstOrSecs>
      </formData>
    </edgarSubmission>
    """

    class FakeResponse:
        def __init__(self, *, json_body=None, text=""):
            self._json_body = json_body
            self.text = text

        def json(self):
            return self._json_body

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            assert kwargs["follow_redirects"] is True
            if "submissions/CIK0001029090.json" in url:
                return FakeResponse(json_body=submissions)
            if "submissions/CIK0001029090-submissions-001.json" in url:
                return FakeResponse(json_body=archived_submissions)
            if "Archives/edgar/data/1029090/000102909026000001/primary_doc.xml" in url:
                return FakeResponse(text=raw_xml)
            raise AssertionError(f"unexpected EDGAR URL: {url}")

    monkeypatch.setattr("app.services.etf_holdings_edgar.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/VT/profile",
        json={"issuer": "Vanguard", "sec_cik": "1029090"},
        headers=admin_headers,
    )
    assert profile.status_code == 200

    backfill = client.post(
        "/api/v1/etf-holdings/VT/backfill-sec-nport",
        json={"start_date": "2026-01-01", "end_date": "2026-12-31", "max_filings": 10},
        headers=admin_headers,
    )
    assert backfill.status_code == 200
    backfill_body = backfill.json()
    job_id = backfill_body.pop("job_id")
    assert isinstance(job_id, int)
    assert backfill_body == {
        "status": "completed",
        "discovered": 1,
        "ingested": 1,
        "skipped": 0,
        "failed": 0,
        "failures": [],
    }

    jobs = client.get("/api/v1/etf-holdings/VT/backfills", headers=admin_headers)
    assert jobs.status_code == 200
    assert jobs.json()[0]["id"] == job_id
    assert jobs.json()[0]["discovered_count"] == 1
    assert jobs.json()[0]["ingested_count"] == 1
    assert jobs.json()[0]["filings"][0]["accession_number"] == "0001029090-26-000001"
    assert jobs.json()[0]["filings"][0]["status"] == "ingested"

    job = client.get(f"/api/v1/etf-holdings/backfill-jobs/{job_id}", headers=admin_headers)
    assert job.status_code == 200
    assert job.json()["filings"][0]["snapshot_id"] is not None

    duplicate = client.post(
        "/api/v1/etf-holdings/VT/backfill-sec-nport",
        json={"start_date": "2026-01-01", "end_date": "2026-12-31", "max_filings": 10},
        headers=admin_headers,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "completed"
    assert duplicate.json()["discovered"] == 1
    assert duplicate.json()["ingested"] == 0
    assert duplicate.json()["skipped"] == 1

    bulk = client.post(
        "/api/v1/etf-holdings/backfill-sec-nport",
        json={
            "symbols": ["VT"],
            "start_date": "2026-01-01",
            "end_date": "2026-12-31",
            "max_profiles": 10,
            "max_filings_per_etf": 10,
        },
        headers=admin_headers,
    )
    assert bulk.status_code == 200
    assert bulk.json()["profiles"] == 1
    assert bulk.json()["discovered"] == 1
    assert bulk.json()["ingested"] == 0
    assert bulk.json()["skipped"] == 1
    assert bulk.json()["results"][0]["symbol"] == "VT"

    latest = client.get("/api/v1/etf-holdings/VT/latest", headers=auth_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["composition_date"] == "2026-03-31"
    assert body["known_at"] == "2026-05-01T15:30:00Z"
    assert body["source_identifier"] == "0001029090-26-000001"
    assert body["source_url"].endswith("/primary_doc.xml")
    assert body["source_quality"] == "filing_reconstructed_holdings"


def test_sec_legacy_backfill_discovers_and_ingests_edgar_filings(
    client, admin_headers, auth_headers, monkeypatch
):
    submissions = {
        "filings": {
            "recent": {
                "form": ["N-CSR"],
                "accessionNumber": ["0001029090-19-000001"],
                "filingDate": ["2019-02-01"],
                "reportDate": ["2018-12-31"],
                "acceptanceDateTime": ["2019-02-01T15:30:00.000Z"],
                "primaryDocument": ["ncsr.xml"],
            },
            "files": [],
        }
    }
    raw_xml = """
    <filing>
      <periodOfReport>2018-12-31</periodOfReport>
      <scheduleOfInvestments>
        <investment>
          <issuerName>Apple Inc.</issuerName>
          <ticker>AAPL</ticker>
          <cusip>037833100</cusip>
          <shares>125</shares>
          <marketValue>24000</marketValue>
          <percentageOfNetAssets>6.25</percentageOfNetAssets>
          <currency>USD</currency>
        </investment>
      </scheduleOfInvestments>
    </filing>
    """

    class FakeResponse:
        def __init__(self, *, json_body=None, text=""):
            self._json_body = json_body
            self.text = text

        def json(self):
            return self._json_body

        def raise_for_status(self):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, **kwargs):
            assert kwargs["follow_redirects"] is True
            if "submissions/CIK0001029090.json" in url:
                return FakeResponse(json_body=submissions)
            if "Archives/edgar/data/1029090/000102909019000001/ncsr.xml" in url:
                return FakeResponse(text=raw_xml)
            raise AssertionError(f"unexpected EDGAR URL: {url}")

    monkeypatch.setattr("app.services.etf_holdings_edgar.httpx.AsyncClient", FakeClient)

    profile = client.patch(
        "/api/v1/etf-holdings/VTV/profile",
        json={"issuer": "Vanguard", "sec_cik": "1029090"},
        headers=admin_headers,
    )
    assert profile.status_code == 200

    backfill = client.post(
        "/api/v1/etf-holdings/VTV/backfill-sec-legacy",
        json={"start_date": "2018-01-01", "end_date": "2019-12-31", "max_filings": 10},
        headers=admin_headers,
    )
    assert backfill.status_code == 200
    backfill_body = backfill.json()
    job_id = backfill_body.pop("job_id")
    assert isinstance(job_id, int)
    assert backfill_body == {
        "status": "completed",
        "discovered": 1,
        "ingested": 1,
        "skipped": 0,
        "failed": 0,
        "failures": [],
    }

    jobs = client.get("/api/v1/etf-holdings/VTV/backfills", headers=admin_headers)
    assert jobs.status_code == 200
    assert jobs.json()[0]["id"] == job_id
    assert jobs.json()[0]["job_type"] == "sec_legacy_recent"
    assert jobs.json()[0]["filings"][0]["form"] == "N-CSR"
    assert jobs.json()[0]["filings"][0]["status"] == "ingested"

    duplicate = client.post(
        "/api/v1/etf-holdings/VTV/backfill-sec-legacy",
        json={"start_date": "2018-01-01", "end_date": "2019-12-31", "max_filings": 10},
        headers=admin_headers,
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "completed"
    assert duplicate.json()["discovered"] == 1
    assert duplicate.json()["ingested"] == 0
    assert duplicate.json()["skipped"] == 1

    bulk = client.post(
        "/api/v1/etf-holdings/backfill-sec-legacy",
        json={
            "symbols": ["VTV"],
            "start_date": "2018-01-01",
            "end_date": "2019-12-31",
            "max_profiles": 10,
            "max_filings_per_etf": 10,
        },
        headers=admin_headers,
    )
    assert bulk.status_code == 200
    assert bulk.json()["profiles"] == 1
    assert bulk.json()["discovered"] == 1
    assert bulk.json()["ingested"] == 0
    assert bulk.json()["skipped"] == 1
    assert bulk.json()["results"][0]["symbol"] == "VTV"

    latest = client.get("/api/v1/etf-holdings/VTV/latest", headers=auth_headers)
    assert latest.status_code == 200
    body = latest.json()
    assert body["composition_date"] == "2018-12-31"
    assert body["known_at"] == "2019-02-01T15:30:00Z"
    assert body["provenance"] == "sec_legacy_reconstructed_holdings"
    assert body["source_identifier"] == "0001029090-19-000001"
    assert body["source_url"].endswith("/ncsr.xml")
    assert body["parser_version"] == "sec-legacy-v1"


def test_coverage_summary_reports_missing_partial_and_full_ranges(
    client, admin_headers, auth_headers
):
    client.post(
        "/api/v1/etf-holdings/IWV/ingest",
        json={
            "composition_date": "2024-01-01",
            "source_provider": "issuer-test",
            "rows": [{"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.01"}],
        },
        headers=admin_headers,
    )
    client.post(
        "/api/v1/etf-holdings/IWV/ingest",
        json={
            "composition_date": "2026-12-31",
            "source_provider": "issuer-test",
            "rows": [{"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.01"}],
        },
        headers=admin_headers,
    )
    client.post(
        "/api/v1/etf-holdings/RECENT/ingest",
        json={
            "composition_date": "2026-01-01",
            "source_provider": "issuer-test",
            "rows": [{"symbol": "MSFT", "name": "Microsoft Corp", "weight": "0.01"}],
        },
        headers=admin_headers,
    )

    response = client.post(
        "/api/v1/etf-holdings/coverage-summary",
        json={
            "etf_symbols": ["IWV", "RECENT", "UNKNOWN"],
            "start_date": "2025-01-01",
            "end_date": "2025-12-31",
        },
        headers=auth_headers,
    )
    assert response.status_code == 200
    body = response.json()
    statuses = {row["symbol"]: row["status"] for row in body["rows"]}
    assert statuses["IWV"] == "full"
    assert statuses["RECENT"] == "none"
    assert statuses["UNKNOWN"] == "missing"
    assert body["full"] == 1
    assert body["partial"] == 0
    assert body["none"] == 1
    assert body["missing"] == 1


def test_nearest_snapshot_is_point_in_time_safe(client, admin_headers, auth_headers):
    for snapshot_date in [date(2026, 1, 1), date(2026, 3, 1)]:
        client.post(
            "/api/v1/etf-holdings/SAFE/ingest",
            json={
                "composition_date": snapshot_date.isoformat(),
                "known_at": f"{snapshot_date.isoformat()}T00:00:00Z",
                "source_provider": "issuer-test",
                "rows": [{"symbol": "AAPL", "name": "Apple Inc.", "weight": "0.01"}],
            },
            headers=admin_headers,
        )

    response = client.get(
        "/api/v1/etf-holdings/SAFE/nearest?date=2026-02-15",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["composition_date"] == "2026-01-01"
