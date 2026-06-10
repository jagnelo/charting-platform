from __future__ import annotations

import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from xml.sax.saxutils import escape

import pytest

from app.services.etf_holdings_adapters import (
    ISSUER_ADAPTER_CONFIGS,
    IssuerCsvAdapterConfig,
    IssuerCsvHoldingsAdapter,
    PublicCsvHoldingsAdapter,
    _decimal,
    _discover_holdings_download_url,
    _format_template,
    _parse_ishares_inline_top_holdings,
    _row_dict,
    get_holdings_adapter,
    holdings_adapter_catalog,
    infer_adapter_key,
    parse_etf_discovery_csv,
    parse_holdings_csv,
    parse_holdings_table,
    parse_holdings_xlsx,
    parse_holdings_zip,
    parse_xlsx_table,
    registered_adapter_keys,
)


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


class FakeResponse:
    def __init__(self, *, text: str = "", content: bytes | None = None, content_type: str = "text/csv"):
        self.text = text
        self.content = content if content is not None else text.encode()
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None

    def json(self):
        import json

        return json.loads(self.text)


class FakeAsyncClient:
    queue: list[FakeResponse] = []
    requested: list[tuple[str, dict]] = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def get(self, url, **kwargs):
        type(self).requested.append((url, kwargs))
        if not type(self).queue:
            raise AssertionError(f"Unexpected URL {url}")
        return type(self).queue.pop(0)


def test_decimal_handles_percent_parentheses_and_unicode_minus():
    assert _decimal("6.5%") == Decimal("0.065")
    assert _decimal("(1,234.50)") == Decimal("-1234.50")
    assert _decimal("\u221212.0") == Decimal("-12.0")
    assert _decimal("N/A") is None


def test_row_dict_pads_missing_columns():
    row = _row_dict(["Ticker", "Name", "Weight"], ["AAPL", "Apple"])
    assert row["Ticker"] == "AAPL"
    assert row["Name"] == "Apple"
    assert row["Weight"] is None


def test_parse_holdings_table_handles_aliases_cash_rows_and_cusip_fallback():
    rows = parse_holdings_table(
        [
            ["Fund Name", "Example ETF"],
            ["Security Identifier", "Issuer Name", "% of Fund", "Shares or Principal Amount", "Value USD", "Asset Class", "Currency"],
            ["037833100", "Apple Inc.", "6.10%", "10", "2000", "Equity", "USD"],
            ["USD", "US Dollar", "1.50%", "100", "100", "Cash", "USD"],
            ["", "", "", "", "", "", ""],
        ]
    )
    assert len(rows) == 2
    assert rows[0].cusip == "037833100"
    assert rows[0].symbol is None
    assert rows[0].weight == Decimal("0.061")
    assert rows[1].row_type == "cash"
    assert rows[1].holding_type == "cash"


def test_parse_holdings_table_handles_ark_company_name_alias():
    rows = parse_holdings_csv(
        "\n".join(
            [
                "date,fund,company,ticker,cusip,shares,market value ($),weight (%)",
                "06/07/2026,ARKK,Tesla Inc,TSLA,88160R101,100,12000,8.5",
            ]
        )
    )
    assert len(rows) == 1
    assert rows[0].symbol == "TSLA"
    assert rows[0].name == "Tesla Inc"
    assert rows[0].cusip == "88160R101"
    assert rows[0].weight == Decimal("0.085")


def test_parse_holdings_csv_and_xlsx_roundtrip():
    csv_rows = parse_holdings_csv(
        "\n".join(
            [
                "Ticker,Name,Weight (%),Shares,Market Value,Currency",
                "AAPL,Apple Inc.,6.1%,10,2000,USD",
                "MSFT,Microsoft Corp,5.4%,8,3200,USD",
            ]
        )
    )
    workbook = _xlsx_workbook(
        [
            ["Ticker", "Name", "Weight (%)", "Shares", "Market Value", "Currency"],
            ["AAPL", "Apple Inc.", "6.1%", "10", "2000", "USD"],
            ["MSFT", "Microsoft Corp", "5.4%", "8", "3200", "USD"],
        ]
    )
    xlsx_rows = parse_holdings_xlsx(workbook)
    parsed_table = parse_xlsx_table(workbook)

    assert len(csv_rows) == 2
    assert len(xlsx_rows) == 2
    assert parsed_table[0][:3] == ["Ticker", "Name", "Weight (%)"]
    assert xlsx_rows[1].symbol == "MSFT"


def test_parse_holdings_zip_prefers_holdings_member():
    csv_text = "\n".join(
        [
            "Ticker,Name,Weight (%),Shares,Market Value,Currency",
            "QQQ,Invesco QQQ,1.0%,1,1,USD",
        ]
    )
    workbook = _xlsx_workbook(
        [
            ["Ticker", "Name", "Weight (%)", "Shares", "Market Value", "Currency"],
            ["AAPL", "Apple Inc.", "6.1%", "10", "2000", "USD"],
        ]
    )
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w") as archive:
        archive.writestr("docs/readme.txt", "ignore")
        archive.writestr("portfolio_holdings.csv", csv_text)
        archive.writestr("other.xlsx", workbook)

    rows, raw_text, metadata = parse_holdings_zip(output.getvalue())

    assert len(rows) == 1
    assert rows[0].symbol == "QQQ"
    assert "portfolio_holdings.csv" in metadata["selected_archive_file"]
    assert metadata["selected_archive_file_format"] == "csv"
    assert "Ticker,Name" in raw_text


def test_parse_etf_discovery_csv_preserves_route_metadata():
    rows = parse_etf_discovery_csv(
        "\n".join(
            [
                "Symbol,Fund Name,Issuer,Product URL,Issuer Product ID,Holdings URL Template,Dated Holdings URL Template,SEC CIK,FIGI",
                "IVV,iShares Core S&P 500 ETF,iShares,https://issuer.example/ivv,239726,https://issuer.example/{symbol}.csv,https://issuer.example/{date_yyyymmdd}.csv,0001234567,BBG000BLNNH6",
            ]
        )
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.symbol == "IVV"
    assert row.issuer_product_id == "239726"
    assert row.holdings_url_template == "https://issuer.example/{symbol}.csv"
    assert row.dated_holdings_url_template == "https://issuer.example/{date_yyyymmdd}.csv"
    assert row.sec_cik == "0001234567"


def test_discover_holdings_download_url_accepts_download_route_without_extension():
    html = """
      <html>
        <body>
          <a href="/funds/spy/factsheet.pdf">Fact sheet</a>
          <a href="/investments/spy/downloads/holdings/">Download all holdings</a>
        </body>
      </html>
    """
    assert (
        _discover_holdings_download_url("https://issuer.example/funds/spy", html)
        == "https://issuer.example/investments/spy/downloads/holdings/"
    )


def test_discover_holdings_download_url_accepts_data_uri_with_download_filename():
    html = """
      <html>
        <body>
          <a download="NIKL-holdings-2026-06-08.csv"
             href="data:application/csv;charset=utf-8,Ticker%2CName%0D%0ANIC%2CNickel%20Industries">
             Download holdings
          </a>
        </body>
      </html>
    """
    assert _discover_holdings_download_url(
        "https://sprottetfs.example/nikl",
        html,
    ).startswith("data:application/csv")


def test_parse_ishares_inline_top_holdings_extracts_rows():
    html_text = (
        '{"topHoldings":['
        '{"holdingsName":"NVIDIA CORP","holdingPercent":"8.15","holdingSerialNumber":1},'
        '{"holdingsName":"MICROSOFT CORP","holdingPercent":"4.88","holdingSerialNumber":2}'
        ']}'
    )
    rows = _parse_ishares_inline_top_holdings(html_text)
    assert [row.name for row in rows] == ["NVIDIA CORP", "MICROSOFT CORP"]
    assert rows[0].weight == Decimal("8.15")
    assert rows[1].source_row_id == "2"


@pytest.mark.asyncio
async def test_public_csv_holdings_adapter_parses_csv_xlsx_zip_and_ishares_html(monkeypatch):
    csv_text = "\n".join(
        [
            "Ticker,Name,Weight (%),Shares,Market Value,Currency",
            "AAPL,Apple Inc.,6.1%,10,2000,USD",
        ]
    )
    workbook = _xlsx_workbook(
        [
            ["Ticker", "Name", "Weight (%)", "Shares", "Market Value", "Currency"],
            ["MSFT", "Microsoft Corp", "5.4%", "8", "3200", "USD"],
        ]
    )
    archive_buffer = BytesIO()
    with zipfile.ZipFile(archive_buffer, mode="w") as archive:
        archive.writestr("portfolio_holdings.csv", csv_text)

    FakeAsyncClient.requested = []
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    adapter = PublicCsvHoldingsAdapter("parser_helper", "issuer_csv")

    FakeAsyncClient.queue = [FakeResponse(text=csv_text)]
    result = await adapter.fetch_latest(symbol="SPY", source_url="https://issuer.example/spy.csv")
    assert result.rows[0].symbol == "AAPL"
    assert result.legal_metadata["source_format"] == "csv"

    FakeAsyncClient.queue = [FakeResponse(content=workbook, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")]
    result = await adapter.fetch_latest(symbol="SPY", source_url="https://issuer.example/spy.xlsx")
    assert result.rows[0].symbol == "MSFT"
    assert result.legal_metadata["source_format"] == "xlsx"

    FakeAsyncClient.queue = [FakeResponse(content=archive_buffer.getvalue(), content_type="application/zip")]
    result = await adapter.fetch_latest(symbol="SPY", source_url="https://issuer.example/spy.zip")
    assert result.rows[0].symbol == "AAPL"
    assert result.legal_metadata["selected_archive_file"] == "portfolio_holdings.csv"

    FakeAsyncClient.queue = [
        FakeResponse(
            text='{"topHoldings":[{"holdingsName":"META","holdingPercent":"2.5","holdingSerialNumber":1}]}',
            content_type="text/html",
        )
    ]
    result = await PublicCsvHoldingsAdapter("ishares").fetch_latest(
        symbol="IVV",
        source_url="https://issuer.example/ivv",
    )
    assert result.rows[0].name == "META"


@pytest.mark.asyncio
async def test_public_csv_holdings_adapter_parses_data_uri_without_http(monkeypatch):
    FakeAsyncClient.requested = []
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await PublicCsvHoldingsAdapter("sprott").fetch_latest(
        symbol="NIKL",
        source_url=(
            "data:application/csv;charset=utf-8,"
            "Security%2CMarket%20Value%2CSymbol%2CSEDOL%2CQuantity%2CWeight%0D%0A"
            "Nickel%20Industries%20Ltd.%2C10029221.90%2CNIC%20AU%2CBZ7NDP2%2C14024607.00%2C15"
        ),
    )

    assert FakeAsyncClient.requested == []
    assert result.rows[0].name == "Nickel Industries Ltd."
    assert result.rows[0].weight == Decimal("0.15")


@pytest.mark.asyncio
async def test_issuer_csv_holdings_adapter_resolves_templates_discovers_product_pages_and_dated_urls(monkeypatch):
    class ExampleHoldingsAdapter(IssuerCsvHoldingsAdapter):
        dated_url_template_aliases = ("example_dated_holdings_url_template",)

    config = IssuerCsvAdapterConfig(
        adapter_key="example",
        source_provider="example",
        url_templates=("https://issuer.example/{issuer_product_id}/{symbol}.csv",),
        product_page_templates=("https://issuer.example/funds/{symbol_lower}",),
    )
    adapter = ExampleHoldingsAdapter(config)
    csv_text = "\n".join(
        [
            "Ticker,Name,Weight (%),Shares,Market Value,Currency",
            "AAPL,Apple Inc.,6.1%,10,2000,USD",
        ]
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(text='<a href="/downloads/portfolio_holdings.csv">Download holdings</a>', content_type="text/html"),
        FakeResponse(text=csv_text, content_type="text/csv"),
        FakeResponse(text=csv_text, content_type="text/csv"),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    assert (
        adapter.resolve_source_url(symbol="IVV", issuer_product_id="239726", identifiers={})
        == "https://issuer.example/239726/IVV.csv"
    )
    assert adapter.resolve_source_url(
        symbol="SPY",
        identifiers={"product_url": "https://issuer.example/funds/spy"},
    ) is None
    assert (
        adapter.resolve_product_page_url(symbol="SPY", identifiers={})
        == "https://issuer.example/funds/spy"
    )
    assert (
        adapter.resolve_dated_source_url(
            symbol="SPY",
            requested_date=date(2026, 6, 7),
            identifiers={
                "example_dated_holdings_url_template": (
                    "https://issuer.example/{date_yyyymmdd}.csv"
                )
            },
        )
        == "https://issuer.example/20260607.csv"
    )

    result = await adapter.fetch_latest(
        symbol="SPY",
        identifiers={"product_url": "https://issuer.example/funds/spy"},
    )
    assert result.rows[0].symbol == "AAPL"
    assert result.source_url == "https://issuer.example/downloads/portfolio_holdings.csv"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_discovery"

    dated = await adapter.fetch_for_date(
        symbol="SPY",
        requested_date=date(2026, 6, 7),
        identifiers={
            "example_dated_holdings_url_template": (
                "https://issuer.example/{date_yyyymmdd}.csv"
            )
        },
    )
    assert dated.rows[0].symbol == "AAPL"
    assert dated.legal_metadata["requested_holdings_date"] == "2026-06-07"


@pytest.mark.asyncio
async def test_ark_adapter_resolves_known_public_assets_file(monkeypatch):
    adapter = get_holdings_adapter("ark")
    assert adapter is not None

    expected_url = (
        "https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
        "ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv"
    )
    assert adapter.resolve_source_url(symbol="ARKK", identifiers={}) == expected_url

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "date,fund,company,ticker,cusip,shares,market value ($),weight (%)",
                    "06/07/2026,ARKK,Tesla Inc,TSLA,88160R101,100,12000,8.5",
                ]
            )
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="ARKK", identifiers={})

    assert FakeAsyncClient.requested[0][0] == expected_url
    assert result.rows[0].symbol == "TSLA"
    assert result.rows[0].name == "Tesla Inc"
    assert result.rows[0].weight == Decimal("0.085")
    assert result.legal_metadata["route_resolution"] == "issuer_profile_metadata"


@pytest.mark.asyncio
async def test_invesco_adapter_fetches_public_json_api(monkeypatch):
    adapter = get_holdings_adapter("invesco")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '{"effectiveDate":"2026-06-06","effectiveBusinessDate":"2026-06-05",'
                '"totalNumberOfHoldings":105,'
                '"holdings":[{"ticker":"NVDA","issuerName":"NVIDIA Corp",'
                '"units":190601606,"percentageOfTotalNetAssets":8.305722,'
                '"securityTypeName":"Common Stock","cusip":"67066G104","currency":"USD"}]}'
            ),
            content_type="application/json",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(
        symbol="QQQ",
        identifiers={},
    )

    assert "shareclasses/QQQ/holdings/fund" in FakeAsyncClient.requested[0][0]
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].name == "NVIDIA Corp"
    assert result.rows[0].weight == Decimal("0.08305722")
    assert result.legal_metadata["source_format"] == "json"
    assert result.legal_metadata["route_resolution"] == "issuer_public_json_api"
    request_headers = FakeAsyncClient.requested[0][1]["headers"]
    assert request_headers["Referer"] == "https://www.invesco.com/"
    assert "HeadlessChrome" in request_headers["User-Agent"]


def test_invesco_adapter_resolves_default_live_route_from_symbol():
    adapter = get_holdings_adapter("invesco")
    assert adapter is not None

    source_url = adapter.resolve_source_url(symbol="QQQ", identifiers={})
    assert source_url == (
        "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/"
        "QQQ/holdings/fund?idType=ticker&interval=monthly&productType=ETF"
    )
    probe = adapter.probe(symbol="QQQ", name="Invesco QQQ Trust", identifiers={})
    assert probe.status == "ready"
    assert probe.source_url == source_url


def test_holdings_adapter_catalog_and_inference_cover_known_routes():
    catalog = holdings_adapter_catalog()
    vaneck = next(item for item in catalog if item["adapter_key"] == "vaneck")

    assert "configured_csv_url" not in {item["adapter_key"] for item in catalog}
    assert vaneck["supports_product_page_discovery"] is True
    assert any("product_url" in item["route_identifiers"] for item in catalog if item["adapter_key"] == "global_x")

    by_domain = infer_adapter_key(
        issuer=None,
        fund_family=None,
        name="Something",
        product_url="https://www.vaneck.com/us/en/investments/smh/",
    )
    assert by_domain.adapter_key == "vaneck"
    assert by_domain.status == "candidate"

    by_name = infer_adapter_key(
        issuer="ARK Investment Management",
        fund_family=None,
        name="ARK Innovation ETF",
    )
    assert by_name.adapter_key == "ark"

    sprott = infer_adapter_key(
        issuer="Sprott",
        fund_family=None,
        name="Sprott Nickel Miners ETF",
    )
    assert sprott.adapter_key == "sprott"

    unresolved = infer_adapter_key(
        issuer="Unknown",
        fund_family="Unknown",
        name="Mystery ETF",
    )
    assert unresolved.adapter_key == "unresolved"


def test_registered_holdings_adapters_are_provider_specific():
    assert "configured_csv_url" not in registered_adapter_keys()
    for adapter_key in ISSUER_ADAPTER_CONFIGS:
        adapter = get_holdings_adapter(adapter_key)
        assert adapter is not None
        assert type(adapter) is not IssuerCsvHoldingsAdapter
        assert type(adapter) is not PublicCsvHoldingsAdapter


@pytest.mark.asyncio
async def test_sprott_adapter_discovers_product_page_from_public_sitemap(monkeypatch):
    adapter = get_holdings_adapter("sprott")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<?xml version="1.0" encoding="utf-8"?>'
                '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                '<url><loc>https://sprottetfs.com/nikl-sprott-nickel-miners-etf/</loc></url>'
                "</urlset>"
            ),
            content_type="application/xml",
        ),
        FakeResponse(
            text=(
                '<a download="NIKL-holdings-2026-06-08.csv" '
                'href="data:application/csv;charset=utf-8,Security%2CMarket%20Value%2CSymbol%2CSEDOL%2CQuantity%2CWeight%0D%0A'
                'Nickel%20Industries%20Ltd.%2C10029221.90%2CNIC%20AU%2CBZ7NDP2%2C14024607.00%2C15">'
                "Download holdings</a>"
            ),
            content_type="text/html",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="NIKL", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://sprottetfs.com/xml-sitemap/"
    assert FakeAsyncClient.requested[1][0] == "https://sprottetfs.com/nikl-sprott-nickel-miners-etf/"
    assert result.rows
    assert result.rows[0].name == "Nickel Industries Ltd."
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_discovery"


def test_ishares_adapter_resolves_known_product_id_from_symbol():
    adapter = get_holdings_adapter("ishares")
    assert adapter is not None

    source_url = adapter.resolve_source_url(symbol="IWM", identifiers={})

    assert source_url is not None
    assert source_url.startswith(
        "https://www.blackrock.com/varnish-api/blk-one01-product-data/"
        "product-data/api/v2/get-product-data?"
    )
    assert "component=holdings.all" in source_url
    assert "portfolioId=239710" in source_url
    probe = adapter.probe(symbol="IWM", name="iShares Russell 2000 ETF", identifiers={})
    assert probe.status == "ready"
    assert probe.issuer_product_id == "239710"


def test_ishares_adapter_resolves_known_product_id_for_eem():
    adapter = get_holdings_adapter("ishares")
    assert adapter is not None

    source_url = adapter.resolve_source_url(symbol="EEM", identifiers={})

    assert source_url is not None
    assert "portfolioId=239637" in source_url
    probe = adapter.probe(symbol="EEM", name="iShares MSCI Emerging Markets ETF", identifiers={})
    assert probe.status == "ready"
    assert probe.issuer_product_id == "239637"


@pytest.mark.asyncio
async def test_ishares_adapter_fetches_blackrock_product_data_json(monkeypatch):
    adapter = get_holdings_adapter("ishares")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '{"componentsByNameMap":{"holdings":{"containersByNameMap":{"all":'
                '{"dataPointsByNameMap":{'
                '"asOfDate":{"value":20260605},'
                '"ticker":{"value":["BE"]},'
                '"issueName":{"value":["BLOOM ENERGY CLASS A CORP"]},'
                '"holdingPercent":{"value":[1.73984]},'
                '"unitsHeld":{"value":[10]},'
                '"marketValue":{"value":[1000.25]},'
                '"currencyCode":{"value":["USD"]},'
                '"countryOfRisk":{"value":["United States"]},'
                '"exchange":{"value":["NYSE"]},'
                '"assetClass":{"value":["Equity"]},'
                '"cusip":{"value":["093712107"]},'
                '"isin":{"value":["US0937121079"]},'
                '"sedol":{"value":["BDD1BB8"]},'
                '"sectorName":{"value":["Industrials"]}'
                "}}}}}}"
            ),
            content_type="application/json",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="IWM", identifiers={})

    assert "portfolioId=239710" in FakeAsyncClient.requested[0][0]
    assert result.rows[0].symbol == "BE"
    assert result.rows[0].name == "BLOOM ENERGY CLASS A CORP"
    assert result.rows[0].weight == Decimal("0.0173984")
    assert result.rows[0].shares == Decimal("10")
    assert result.rows[0].market_value == Decimal("1000.25")
    assert result.legal_metadata["route_resolution"] == "issuer_public_json_api"
    assert result.legal_metadata["source_format"] == "json"
    assert result.legal_metadata["composition_date"] == "2026-06-05"


def test_format_template_returns_none_when_missing_fields():
    assert _format_template("https://issuer.example/{symbol}/{date}", {"symbol": "SPY"}) is None
    assert _format_template("https://issuer.example/{symbol}", {"symbol": "SPY"}) == "https://issuer.example/SPY"
