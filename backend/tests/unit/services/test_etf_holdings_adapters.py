from __future__ import annotations

import json
import zipfile
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
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
    parse_html_holdings_table_by_headers,
    parse_html_holdings_table_by_id,
    parse_xlsx_table,
    registered_adapter_keys,
)


def _xlsx_workbook(rows: list[list[str]]) -> bytes:
    return _xlsx_workbook_sheets([rows])


def _xlsx_workbook_sheets(sheets: list[list[list[str]]]) -> bytes:
    def cell_ref(column_index: int, row_index: int) -> str:
        column = ""
        value = column_index + 1
        while value:
            value, remainder = divmod(value - 1, 26)
            column = chr(ord("A") + remainder) + column
        return f"{column}{row_index}"

    output = BytesIO()
    with zipfile.ZipFile(output, mode="w") as workbook:
        for sheet_index, rows in enumerate(sheets, start=1):
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
            workbook.writestr(f"xl/worksheets/sheet{sheet_index}.xml", worksheet)
    return output.getvalue()


class FakeResponse:
    def __init__(
        self,
        *,
        text: str = "",
        content: bytes | None = None,
        content_type: str = "text/csv",
        status_code: int = 200,
    ):
        self.text = text
        self.content = content if content is not None else text.encode()
        self.headers = {"content-type": content_type}
        self.status_code = status_code
        self.url = "https://issuer.example/holdings.csv"

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

    async def post(self, url, **kwargs):
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


def test_parse_holdings_table_handles_schwab_percent_of_assets_alias():
    rows = parse_holdings_csv(
        "\n".join(
            [
                "As-Of-Date,Symbol,Name,Quantity,Percent of Assets,Currency,Exchange",
                "2026-06-11,TXN,TEXAS INSTRUMENT INC,18627699.0000000000,5.7492400368,USD,XNGS",
            ]
        )
    )

    assert len(rows) == 1
    assert rows[0].symbol == "TXN"
    assert rows[0].name == "TEXAS INSTRUMENT INC"
    assert rows[0].shares == Decimal("18627699.0000000000")
    assert rows[0].weight == Decimal("0.057492400368")
    assert rows[0].currency == "USD"
    assert rows[0].exchange == "XNGS"


def test_parse_holdings_table_handles_graniteshares_legacy_xls_shape():
    rows = parse_holdings_table(
        [
            [
                "Position Date",
                "ETF Ticker",
                "Ticker/Cusip",
                "Security Description",
                "Shares/Par",
                "Asset Group",
                "Mat/Exp Date",
                "Market/Notional Value",
                "Contract Size",
                "Value 1 Pt",
                "Shares Outstanding",
                "Percentage Weighting",
                "NAV/Share",
            ],
            [
                "2026-06-12 00:00:00",
                "NVD",
                "NVDA",
                "NVDA",
                "-555500",
                "SW",
                "",
                "-113805285",
                "1",
                "1",
                "11297577",
                "-2.000426",
                "0",
            ],
            [
                "2026-06-12 00:00:00",
                "NVD",
                "USD",
                "US Dollars",
                "56890519.787702",
                "CU",
                "",
                "56890519.787702",
                "1",
                "1",
                "11297577",
                "1",
                "5.03563903903483",
            ],
        ]
    )

    assert len(rows) == 2
    assert rows[0].symbol == "NVDA"
    assert rows[0].shares == Decimal("-555500")
    assert rows[0].market_value == Decimal("-113805285")
    assert rows[0].weight == Decimal("-0.02000426")
    assert rows[1].row_type == "cash"
    assert rows[1].symbol is None
    assert rows[1].weight == Decimal("0.01")


def test_parse_html_holdings_table_handles_proshares_table_shape():
    rows = parse_html_holdings_table_by_id(
        """
        <table id="holdings">
          <thead>
            <tr>
              <th>Exposure Weight</th>
              <th>Ticker</th>
              <th>Description</th>
              <th>Exposure Value<br>(Notional + GL)</th>
              <th>Market Value</th>
              <th>Shares/Contracts</th>
              <th>SEDOL Number</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>2.51%</td>
              <td>NVDA</td>
              <td>NVIDIA CORP</td>
              <td>--</td>
              <td>$903,347,631.90</td>
              <td>4,409,370</td>
              <td>2379504</td>
            </tr>
          </tbody>
        </table>
        """,
        table_id="holdings",
    )

    assert len(rows) == 1
    assert rows[0].symbol == "NVDA"
    assert rows[0].name == "NVIDIA CORP"
    assert rows[0].weight == Decimal("0.0251")
    assert rows[0].market_value == Decimal("903347631.90")
    assert rows[0].shares == Decimal("4409370")
    assert rows[0].sedol == "2379504"


def test_parse_html_holdings_table_handles_first_trust_table_shape():
    rows = parse_html_holdings_table_by_headers(
        """
        <table class="fundSilverGrid">
          <tr class="fundSilverGridHeader">
            <td>Security Name</td>
            <td>Identifier</td>
            <td>CUSIP</td>
            <td>Classification</td>
            <td>Shares / Quantity</td>
            <td>Market Value</td>
            <td>Weighting</td>
          </tr>
          <tr>
            <td>Arm Holdings Plc</td>
            <td>ARM</td>
            <td>042068205</td>
            <td>Technology</td>
            <td>231,408</td>
            <td>$79,194,759.84</td>
            <td>4.52%</td>
          </tr>
        </table>
        """,
        required_headers={
            "security name",
            "identifier",
            "cusip",
            "shares / quantity",
            "market value",
            "weighting",
        },
    )

    assert len(rows) == 1
    assert rows[0].symbol == "ARM"
    assert rows[0].name == "Arm Holdings Plc"
    assert rows[0].cusip == "042068205"
    assert rows[0].shares == Decimal("231408")
    assert rows[0].market_value == Decimal("79194759.84")
    assert rows[0].weight == Decimal("0.0452")


def test_roundhill_adapter_parses_account_scoped_daily_holdings_csv():
    adapter = get_holdings_adapter("roundhill")
    assert adapter is not None

    rows, composition_date = adapter._parse_roundhill_csv(
        "\n".join(
            [
                "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag",
                "06/12/2026,MAGS,02079K305 TRS 071426 NM,02079K305 TRS 071426 NM,ALPHABET INC-CL A SWAP,647296.00000000,357.770000,231583089.92,6.47%,3577333386.00,55110000,5511.000000000000,",
                "06/12/2026,BETZ,9672 JP,6896065,Tokyotokeiba Co Ltd,24300.00000000,4680.000000,708516.60,1.39%,51025500.00,2550000,102.000000000000,",
            ]
        ),
        account_symbol="MAGS",
    )

    assert composition_date == date(2026, 6, 12)
    assert len(rows) == 1
    assert rows[0].symbol == "02079K305 TRS 071426 NM"
    assert rows[0].name == "ALPHABET INC-CL A SWAP"
    assert rows[0].weight == Decimal("0.0647")
    assert rows[0].shares == Decimal("647296.00000000")
    assert rows[0].market_value == Decimal("231583089.92")
    assert rows[0].extra_data["Account"] == "MAGS"


def test_parse_holdings_csv_handles_yieldmax_column_shape():
    rows = parse_holdings_csv(
        "\n".join(
            [
                "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits",
                "06/12/2026,TSLY,912797RF6,912797RF6,United States Treasury Bill 07/09/2026,197990000,99.730375,197456169.46,23.87%,827224384.14,29729965,1189.2",
            ]
        )
    )

    assert len(rows) == 1
    assert rows[0].symbol == "912797RF6"
    assert rows[0].cusip == "912797RF6"
    assert rows[0].name == "United States Treasury Bill 07/09/2026"
    assert rows[0].shares == Decimal("197990000")
    assert rows[0].market_value == Decimal("197456169.46")
    assert rows[0].weight == Decimal("0.2387")


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
async def test_21shares_adapter_fetches_product_details_constituents(monkeypatch):
    adapter = get_holdings_adapter("21shares")
    assert adapter is not None

    payload = {
        "success": True,
        "data": {
            "ticker": "ARKB",
            "product_name": "ARK 21shares Bitcoin ETF",
            "currency": {"short_name": "USD"},
            "total_units_outstanding": 99085000,
            "total_nav": 2092083784.9,
            "nav_per_unit": 21.11,
            "valuation_date": "2026-06-12",
            "constituents": [
                {
                    "name": "BITCOIN",
                    "ticker": "BTC",
                    "weight": 1,
                    "quantity": 32870.7435,
                    "price": 63654.16,
                    "market_value": 2092359570.44,
                    "total_fiat": 32870.7435,
                    "amount_per_creation_unit": None,
                    "cusip": None,
                }
            ],
        },
    }
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(text=json.dumps(payload), content_type="application/json"),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="ARKB")

    assert FakeAsyncClient.requested[0][0] == (
        "https://21sharesprimary.paradox-coworking.com/api/product_details/ARKB"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Origin"] == "https://www.21shares.com"
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.symbol == "BTC"
    assert row.name == "BITCOIN"
    assert row.holding_type == "crypto"
    assert row.row_type == "crypto"
    assert row.weight == Decimal("1")
    assert row.shares == Decimal("32870.7435")
    assert row.market_value == Decimal("2092359570.44")
    assert row.currency == "USD"
    assert row.extra_data["valuation_date"] == "2026-06-12"
    assert result.legal_metadata["source_provider"] == "21shares"
    assert result.legal_metadata["route_resolution"] == "issuer_public_product_details_api"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_renaissance_capital_adapter_fetches_public_holdings_workbook(monkeypatch):
    adapter = get_holdings_adapter("renaissance_capital")
    assert adapter is not None

    workbook = _xlsx_workbook(
        [
            [
                "Date",
                "Holding Name",
                "Asset Class",
                "Ticker",
                "SEDOL",
                "Shares",
                "Holding Value",
                "Weight",
            ],
            [
                "46185",
                "Astera Labs",
                "Equity",
                "ALAB",
                "BMTQ7V2",
                "63607",
                "23373664.29",
                "14.14579914",
            ],
        ]
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            content=workbook,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="IPO")

    assert FakeAsyncClient.requested[0][0] == (
        "https://etfs.renaissancecapital.com/excel-downloads/holdings/ipo"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == (
        "https://etfs.renaissancecapital.com/us-ipo-etf"
    )
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.symbol == "ALAB"
    assert row.name == "Astera Labs"
    assert row.sedol == "BMTQ7V2"
    assert row.holding_type == "equity"
    assert row.weight == Decimal("0.1414579914")
    assert row.shares == Decimal("63607")
    assert row.market_value == Decimal("23373664.29")
    assert result.legal_metadata["source_provider"] == "renaissance_capital"
    assert result.legal_metadata["source_format"] == "xlsx"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_xlsx"


@pytest.mark.asyncio
async def test_matthews_adapter_fetches_product_page_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("matthews")
    assert adapter is not None

    html = """
    <html>
      <body>
        <span id="asOfHoldings">(as of 06/15/2026)</span>
        <table class="top_10_daily" id="tblDailyTopHoldings">
          <tr>
            <th>Ticker</th>
            <th>Name</th>
            <th>SEDOL</th>
            <th>Market Value</th>
            <th>Shares</th>
            <th>% Net Assets</th>
          </tr>
          <tr>
            <td>700</td>
            <td>TENCENT HOLDINGS, LTD.</td>
            <td>BMMV2K8</td>
            <td>$3,029,157</td>
            <td>51,200</td>
            <td>13.1</td>
          </tr>
        </table>
      </body>
    </html>
    """
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [FakeResponse(text=html, content_type="text/html")]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="MCH")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.matthewsasia.com/funds/etfs/china-active-etf/"
    )
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.symbol == "700"
    assert row.name == "TENCENT HOLDINGS, LTD."
    assert row.sedol == "BMMV2K8"
    assert row.market_value == Decimal("3029157")
    assert row.shares == Decimal("51200")
    assert row.weight == Decimal("0.131")
    assert result.legal_metadata["source_provider"] == "matthews"
    assert result.legal_metadata["source_format"] == "html"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_holdings_table"
    assert result.legal_metadata["composition_date"] == "2026-06-15"


@pytest.mark.asyncio
async def test_new_york_life_adapter_fetches_public_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("new_york_life")
    assert adapter is not None

    raw_csv = "\n".join(
        [
            '"Fund Name:","NYLI Candriam International Equity ETF"',
            '"Holdings:","2026-06-12"',
            '" "," "',
            (
                '"Ticker","ISIN","SEDOL","CUSIP","Security Description","Asset Group",'
                '"Trading Currency","Shares/Par","Maturity Date","Coupon Rate",'
                '"Issue Date","Market Value","Notional Value","% of Net Assets"'
            ),
            (
                '"=""ASML""","=""NL0010273215""","=""B929F46""","=""N07059202""",'
                '"ASML Holding NV","Equity Common","EUR","7288","","0","",'
                '"=DOLLAR(13746455.09)","=DOLLAR(0)","5.6"'
            ),
        ]
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [FakeResponse(text=raw_csv, content_type="text/csv")]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="IQSI")

    assert FakeAsyncClient.requested[0][0] == "https://data.nylim.com/MIQSI.csv"
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.symbol == "ASML"
    assert row.name == "ASML Holding NV"
    assert row.isin == "NL0010273215"
    assert row.sedol == "B929F46"
    assert row.cusip == "N07059202"
    assert row.weight == Decimal("0.056")
    assert row.shares == Decimal("7288")
    assert row.market_value == Decimal("13746455.09")
    assert row.currency == "EUR"
    assert row.extra_data["fund_name"] == "NYLI Candriam International Equity ETF"
    assert row.extra_data["composition_date"] == "2026-06-12"
    assert result.legal_metadata["source_provider"] == "new_york_life"
    assert result.legal_metadata["source_format"] == "csv"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_bondbloxx_adapter_fetches_product_page_embedded_holdings(monkeypatch):
    adapter = get_holdings_adapter("bondbloxx")
    assert adapter is not None

    raw_html = """
    <html>
      <script id="tickers_custom-js-extra">
        var generalData = {
          "holdings": [
            {
              "as_of_date": "2026-06-12T00:00:00Z",
              "currency": "USD",
              "cusip": "03665GAR5",
              "etfticker": "PCMM",
              "isin": "US03665GAR56",
              "market_value": 10029392.15,
              "px_usd": 99.5737,
              "security_name": "ANTR 2023-1A BR V/R 07/25/37",
              "security_number": "03665GAR5",
              "shares_held": 10000000,
              "ticker": null,
              "weight": 0.0518
            },
            {
              "as_of_date": "2026-06-12T00:00:00Z",
              "currency": "USD",
              "cusip": "CASHUSD",
              "etfticker": "PCMM",
              "market_value": 5327345.33,
              "security_name": "CASHUSD",
              "security_number": "CASHUSD",
              "shares_held": 5327345.33,
              "ticker": null,
              "weight": 0.0275
            }
          ]
        };
      </script>
    </html>
    """
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [FakeResponse(text=raw_html, content_type="text/html")]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="PCMM")

    assert FakeAsyncClient.requested[0][0] == (
        "https://bondbloxxetf.com/bondbloxx-private-credit-clo-etf/"
    )
    assert len(result.rows) == 2
    bond_row = result.rows[0]
    assert bond_row.symbol is None
    assert bond_row.name == "ANTR 2023-1A BR V/R 07/25/37"
    assert bond_row.cusip == "03665GAR5"
    assert bond_row.isin == "US03665GAR56"
    assert bond_row.holding_type == "fixed_income"
    assert bond_row.weight == Decimal("0.0518")
    assert bond_row.shares == Decimal("10000000")
    assert bond_row.market_value == Decimal("10029392.15")
    assert bond_row.currency == "USD"
    cash_row = result.rows[1]
    assert cash_row.row_type == "cash"
    assert cash_row.holding_type == "cash"
    assert cash_row.symbol is None
    assert cash_row.cusip is None
    assert result.legal_metadata["source_provider"] == "bondbloxx"
    assert result.legal_metadata["source_format"] == "html_embedded_json"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_product_page_embedded_general_data"
    )
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_bondbloxx_adapter_discovers_product_page_from_sitemap(monkeypatch):
    adapter = get_holdings_adapter("bondbloxx")
    assert adapter is not None

    sitemap = """
    <urlset>
      <url><loc>https://bondbloxxetf.com/bondbloxx-private-credit-clo-etf/</loc></url>
      <url><loc>https://bondbloxxetf.com/bondbloxx-tax-aware-etf-for-ma-residents/</loc></url>
    </urlset>
    """
    wrong_page = '<script>var generalData = {"holdings":[{"etfticker":"PCMM"}]};</script>'
    right_page = """
    <script>
      var generalData = {
        "holdings": [
          {
            "as_of_date": "2026-06-12T00:00:00Z",
            "currency": "USD",
            "cusip": "657339Z83",
            "etfticker": "TAXM",
            "isin": "US657339Z838",
            "market_value": 817450.3,
            "security_name": "NORTH ATTLEBOROUGH 4% 03/15/43",
            "security_number": "657339Z83",
            "shares_held": 800000,
            "ticker": null,
            "weight": 0.023
          }
        ]
      };
    </script>
    """
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(text=sitemap, content_type="text/xml"),
        FakeResponse(text=wrong_page, content_type="text/html"),
        FakeResponse(text=right_page, content_type="text/html"),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="TAXM")

    assert [request[0] for request in FakeAsyncClient.requested] == [
        "https://bondbloxxetf.com/tickers-sitemap.xml",
        "https://bondbloxxetf.com/bondbloxx-private-credit-clo-etf/",
        "https://bondbloxxetf.com/bondbloxx-tax-aware-etf-for-ma-residents/",
    ]
    assert len(result.rows) == 1
    assert result.rows[0].name == "NORTH ATTLEBOROUGH 4% 03/15/43"
    assert result.rows[0].cusip == "657339Z83"
    assert result.rows[0].weight == Decimal("0.023")


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


@pytest.mark.asyncio
async def test_vanguard_adapter_fetches_public_json_api(monkeypatch):
    adapter = get_holdings_adapter("vanguard")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '{"size":503,"asOfDate":"2026-04-30T00:00:00-04:00",'
                '"fund":{"entity":[{"type":"portfolioHolding",'
                '"longName":"NVIDIA Corp.","shortName":"NVIDIA CORP",'
                '"sharesHeld":"630093008","marketValue":125747661606.56,'
                '"ticker":"NVDA","isin":"US67066G1040","percentWeight":"7.85",'
                '"cusip":"67066G104","sedol":"2379504"}]}}'
            ),
            content_type="application/json",
        ),
        FakeResponse(text="{}", content_type="application/json"),
        FakeResponse(text="{}", content_type="application/json"),
        FakeResponse(text="{}", content_type="application/json"),
        FakeResponse(text="{}", content_type="application/json"),
        FakeResponse(text="{}", content_type="application/json"),
        FakeResponse(text="{}", content_type="application/json"),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="VOO", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://investor.vanguard.com/vmf/api/"
        "VOO/portfolio-holding/stock.json?start=1&count=20000"
    )
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].name == "NVIDIA Corp."
    assert result.rows[0].cusip == "67066G104"
    assert result.rows[0].isin == "US67066G1040"
    assert result.rows[0].sedol == "2379504"
    assert result.rows[0].weight == Decimal("0.0785")
    assert result.rows[0].shares == Decimal("630093008")
    assert result.rows[0].market_value == Decimal("125747661606.56")
    assert result.legal_metadata["source_format"] == "json"
    assert result.legal_metadata["route_resolution"] == "issuer_public_json_api"
    assert result.legal_metadata["holding_types"] == ["stock"]


@pytest.mark.asyncio
async def test_innovator_adapter_filters_public_aggregate_csv(monkeypatch):
    adapter = get_holdings_adapter("innovator")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag",
                    "06/12/2026,AAPR,SPY,78462F103,SPDR S&P 500 ETF Trust,1,600,600,0.10%,1000000,1,1,",
                    "06/12/2026,BALT,SPY,78462F103,SPDR S&P 500 ETF Trust,2,600,1200,0.25%,1000000,1,1,",
                    "06/12/2026,BALT,USDOLLAR,,Cash,500,1,500,0.05%,1000000,1,1,1",
                ]
            ),
            content_type="text/csv",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BALT", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.innovatoretfs.com/etf/xt_holdings.csv"
    assert [row.symbol for row in result.rows] == ["SPY", None]
    assert result.rows[0].weight == Decimal("0.0025")
    assert result.rows[0].shares == Decimal("2")
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == "issuer_aggregate_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_cambria_adapter_filters_public_aggregate_csv(monkeypatch):
    adapter = get_holdings_adapter("cambria")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag",
                    "06/12/2026,ENDW,AAPL,037833100,Apple Inc,1,295.63,295.63,0.97%,100000,1,1,",
                    "06/12/2026,SYLD,MSFT,594918104,Microsoft Corp,2,400,800,1.10%,100000,1,1,",
                ]
            ),
            content_type="text/csv",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="SYLD", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.cambriafunds.com/assets/data/"
        "FilepointCambria.40C1.C1_ETF_Holdings.csv"
    )
    assert result.rows[0].symbol == "MSFT"
    assert result.rows[0].weight == Decimal("0.0110")
    assert result.legal_metadata["source_provider"] == "cambria"
    assert result.legal_metadata["route_resolution"] == "issuer_aggregate_holdings_csv"


@pytest.mark.asyncio
async def test_bitwise_adapter_parses_product_page_embedded_holdings(monkeypatch):
    adapter = get_holdings_adapter("bitwise")
    assert adapter is not None

    next_data = (
        '{"props":{"pageProps":{"fundData":{"data":{"holdings":{'
        '"basket":[{"companyName":"BITCOIN","ticker":"","shares":36707.10908116,'
        '"marketValue":2334025568.71,"weight":1}],'
        '"asOfDate":"2026-06-11"}}}}}}'
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<html><body><script id="__NEXT_DATA__" type="application/json">'
                f"{next_data}"
                "</script></body></html>"
            ),
            content_type="text/html",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BITB", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://bitbetf.com/"
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "BITCOIN"
    assert result.rows[0].holding_type == "crypto"
    assert result.rows[0].weight == Decimal("1")
    assert result.rows[0].shares == Decimal("36707.10908116")
    assert result.rows[0].market_value == Decimal("2334025568.71")
    assert result.legal_metadata["source_format"] == "next_json"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_embedded_json"
    assert result.legal_metadata["composition_date"] == "2026-06-11"


@pytest.mark.asyncio
async def test_defiance_adapter_fetches_full_holdings_html_table(monkeypatch):
    adapter = get_holdings_adapter("defiance")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <html>
              <body>
                <h6 class="def-title h-6">Data as of 06/12/2026</h6>
                <table id="table-full-holdings" class="def-table">
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Name</th>
                      <th>CUSIP</th>
                      <th>ETF Weight</th>
                      <th>Shares</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>4NDX 261218C01000340</td>
                      <td>Ndx 12/18/2026 1000.34 C</td>
                      <td>4NDX 261218C01000340</td>
                      <td>98.83%</td>
                      <td>64</td>
                    </tr>
                    <tr>
                      <td>Cash&Other</td>
                      <td>Cash &amp; Other</td>
                      <td>Cash&Other</td>
                      <td>0.80%</td>
                      <td>1,477,468</td>
                    </tr>
                  </tbody>
                </table>
              </body>
            </html>
            """,
            content_type="text/html",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="QQQY", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.defianceetfs.com/qqqy-full-holdings/"
    )
    assert result.rows[0].symbol == "4NDX 261218C01000340"
    assert result.rows[0].name == "Ndx 12/18/2026 1000.34 C"
    assert result.rows[0].cusip == "4NDX 261218C01000340"
    assert result.rows[0].weight == Decimal("0.9883")
    assert result.rows[0].shares == Decimal("64")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.rows[1].weight == Decimal("0.0080")
    assert result.rows[1].shares == Decimal("1477468")
    assert result.legal_metadata["source_format"] == "html"
    assert result.legal_metadata["route_resolution"] == "issuer_full_holdings_html_table"
    assert result.legal_metadata["table_id"] == "table-full-holdings"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_advisor_shares_adapter_fetches_symbol_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("advisor_shares")
    assert adapter is not None

    holdings_csv = "\n".join(
        [
            (
                "Date,Account Symbol,Stock Ticker,Security Number,Security Description,"
                " Shares/Par (Full) , Price (Base) , Traded Market Value (Base) ,"
                "Portfolio Weight %,Asset Group"
            ),
            (
                '6/11/2026,MSOS,TRLV,TRLVCAN,TRULIEVE CANNABIS SWAP,'
                '" 27,456,691.00 ",11.55," 317,124,781.05 ",29.07%,TW'
            ),
            (
                ',,CURLD,CURLFCAN,CURALEAF HOLDINGS INC,'
                '" 27,740,126.67 ",10.43," 289,329,521.13 ",26.52%,FS'
            ),
        ]
    )
    requested: list[tuple[str, dict]] = []

    def fake_get(url, **kwargs):
        requested.append((url, kwargs))
        response = FakeResponse(text=holdings_csv, content_type="text/csv")
        response.url = url
        return response

    monkeypatch.setattr("app.services.etf_holdings_adapters.requests.get", fake_get)

    result = await adapter.fetch_latest(symbol="MSOS", identifiers={})

    assert requested[0][0] == (
        "https://advisorshares.com/wp-content/uploads/csv/holdings/"
        "AdvisorShares_MSOS_Holdings_File.csv"
    )
    assert result.rows[0].symbol == "TRLV"
    assert result.rows[0].name == "TRULIEVE CANNABIS SWAP"
    assert result.rows[0].cusip is None
    assert result.rows[0].weight == Decimal("0.2907")
    assert result.rows[0].shares == Decimal("27456691.00")
    assert result.rows[0].market_value == Decimal("317124781.05")
    assert result.rows[1].symbol == "CURLD"
    assert result.rows[1].weight == Decimal("0.2652")
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-11"


@pytest.mark.asyncio
async def test_teucrium_adapter_filters_aggregate_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("teucrium")
    assert adapter is not None

    holdings_csv = "\n".join(
        [
            (
                "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,"
                "Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag"
            ),
            (
                "06/12/2026,BTCK,XBTUSD,XBTUSD,BITCOIN,17.80647512,63579.360000,"
                "1132124.29,77.98%,1451844.00,60000,6.000000000000,"
            ),
            (
                "06/12/2026,CORN,C N26 Comdty,C N26 COMDTY,CORN FUTURE Jul26,"
                "100.00000000,438.250000,2191250.00,35.00%,6260714.29,100000,10,"
            ),
            (
                "06/12/2026,CORN,Cash&Other,Cash&Other,Cash & Other,"
                "1000.00000000,1.000000,1000.00,0.02%,6260714.29,100000,10,Y"
            ),
        ]
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(text=holdings_csv, content_type="text/csv"),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="CORN", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://etfs.teucrium.com/assets/data/FilepointTeucrium.40TZ.TZ_Holdings.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "C N26 Comdty"
    assert result.rows[0].name == "CORN FUTURE Jul26"
    assert result.rows[0].cusip == "C N26 COMDTY"
    assert result.rows[0].weight == Decimal("0.3500")
    assert result.rows[0].shares == Decimal("100.00000000")
    assert result.rows[0].market_value == Decimal("2191250.00")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.legal_metadata["route_resolution"] == "issuer_aggregate_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_us_global_investors_adapter_parses_product_page_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("us_global_investors")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <html>
              <body>
                <div class="tab-pane" id="holdings" role="tabpanel">
                  <h2 class="title">Holdings</h2>
                  <span class="as-of">Data as of 06/02/2026</span>
                  <table>
                    <tr class="header-row">
                      <th class="number">% Net Assets</th>
                      <th>Name</th>
                      <th>CUSIP</th>
                      <th>Country</th>
                      <th>Ticker</th>
                      <th class="number">Shares Held</th>
                      <th class="number">Market ($)</th>
                    </tr>
                    <tr>
                      <td><div class="h-title">% Net Assets</div><div class="h-data">12.67%</div></td>
                      <td><div class="h-title">Name</div><div class="h-data">Delta Air Lines Inc</div></td>
                      <td><div class="h-title">CUSIP</div><div class="h-data">247361702</div></td>
                      <td><div class="h-title">Country</div><div class="h-data">United States</div></td>
                      <td><div class="h-title">Ticker</div><div class="h-data">DAL</div></td>
                      <td><div class="h-title">Shares Held</div><div class="h-data">1,258,808</div></td>
                      <td><div class="h-title">Market ($)</div><div class="h-data">108,998,022</div></td>
                    </tr>
                  </table>
                </div>
              </body>
            </html>
            """,
            content_type="text/html",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="JETS", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://usglobaletfs.com/fund/jets/"
    assert result.rows[0].symbol == "DAL"
    assert result.rows[0].name == "Delta Air Lines Inc"
    assert result.rows[0].cusip == "247361702"
    assert result.rows[0].country == "United States"
    assert result.rows[0].weight == Decimal("0.1267")
    assert result.rows[0].shares == Decimal("1258808")
    assert result.rows[0].market_value == Decimal("108998022")
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_holdings_table"
    assert result.legal_metadata["composition_date"] == "2026-06-02"


@pytest.mark.asyncio
async def test_american_century_adapter_parses_avantis_embedded_holdings(monkeypatch):
    adapter = get_holdings_adapter("american_century")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <html>
              <script>
                a.portfolio={
                  etfHoldingsAsOfDate:"06/11/2026",
                  etfHoldings:[
                    {
                      name:"VIASAT INC COMMON STOCK USD.0001",
                      ticker:"VSAT",
                      securityType:"COMMON STOCK",
                      cusip:"92552V100",
                      isin:"US92552V1008",
                      sedol:"2946243",
                      shareQuantity:"4512700",
                      contractCount:"0",
                      baseMarketValue:"328118417.00",
                      weight:"1.16%",
                      coupon:"0",
                      maturityDate:"",
                      sector:"INFORMATION TECHNOLOGY",
                      country:"UNITED STATES"
                    },
                    {
                      name:"MATSON INC COMMON STOCK",
                      ticker:"MATX",
                      securityType:"COMMON STOCK",
                      cusip:"57686G105",
                      isin:"US57686G1058",
                      sedol:"B8GNC91",
                      shareQuantity:"1512342",
                      contractCount:"0",
                      baseMarketValue:"300925811.16",
                      weight:"1.06%",
                      coupon:"0",
                      maturityDate:"",
                      sector:"INDUSTRIALS",
                      country:"UNITED STATES"
                    }
                  ]
                }
              </script>
            </html>
            """,
            content_type="text/html",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="AVUV", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.avantisinvestors.com/avantis-investments/"
        "avantis-us-small-cap-value-etf/"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "VSAT"
    assert result.rows[0].name == "VIASAT INC COMMON STOCK USD.0001"
    assert result.rows[0].cusip == "92552V100"
    assert result.rows[0].isin == "US92552V1008"
    assert result.rows[0].sedol == "2946243"
    assert result.rows[0].country == "UNITED STATES"
    assert result.rows[0].weight == Decimal("0.0116")
    assert result.rows[0].shares == Decimal("4512700")
    assert result.rows[0].market_value == Decimal("328118417.00")
    assert result.rows[0].extra_data["sector"] == "INFORMATION TECHNOLOGY"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_embedded_holdings"
    assert result.legal_metadata["composition_date"] == "2026-06-11"


@pytest.mark.asyncio
async def test_jpmorgan_adapter_parses_product_data_daily_holdings(monkeypatch):
    adapter = get_holdings_adapter("jpmorgan")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            {
              "fundData": {
                "dailyHoldingsAll": {
                  "effectiveDate": "2026-06-11",
                  "data": [
                    {
                      "marketValue": 772702376.47,
                      "netAssetValuePercent": 1.75,
                      "securityDescription": "ROSS STORES INC COMMON",
                      "securityId": "778296103",
                      "securityTicker": "ROST",
                      "securityType": "DOMESTIC COMMON STOCK",
                      "shares": 3231577,
                      "navDate": "2026-06-11",
                      "country": "United States",
                      "sector": "Consumer Discretionary"
                    },
                    {
                      "marketValue": 25615564.82,
                      "netAssetValuePercent": 0.06,
                      "securityDescription": "JPM USD CASH",
                      "securityId": "USD",
                      "securityTicker": "USD",
                      "securityType": "CASH",
                      "shares": 25615564.82,
                      "navDate": "2026-06-11",
                      "country": "United States"
                    }
                  ]
                }
              }
            }
            """,
            content_type="application/json",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="JEPI", issuer_product_id="46641Q332")

    requested_url, requested_kwargs = FakeAsyncClient.requested[0]
    assert requested_url == "https://am.jpmorgan.com/FundsMarketingHandler/product-data"
    assert requested_kwargs["params"]["cusip"] == "46641Q332"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ROST"
    assert result.rows[0].name == "ROSS STORES INC COMMON"
    assert result.rows[0].cusip == "778296103"
    assert result.rows[0].shares == Decimal("3231577")
    assert result.rows[0].market_value == Decimal("772702376.47")
    assert result.rows[0].weight == Decimal("0.0175")
    assert result.rows[0].country == "United States"
    assert result.rows[0].extra_data["sector"] == "Consumer Discretionary"
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_product_data_json"
    assert result.legal_metadata["source_provider"] == "jpmorgan"
    assert result.legal_metadata["composition_date"] == "2026-06-11"


@pytest.mark.asyncio
async def test_franklin_adapter_parses_graphql_holdings(monkeypatch):
    adapter = get_holdings_adapter("franklin")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            {
              "data": {
                "Portfolio": {
                  "fundname": "Franklin U.S. Large Cap Multifactor Index ETF",
                  "producttype": "ETFs",
                  "assetclass": "Equity",
                  "portfolio": {
                    "dailyholdings": [
                      {
                        "fundid": "25773",
                        "asofdate": "06/11/2026",
                        "asofdatestd": "2026-06-11",
                        "frequency": "DAILY",
                        "secticker": "NTRS",
                        "isinsecnbr": "US6658591044",
                        "cusipnbr": "665859104",
                        "secname": "NORTHERN TRUST CORP",
                        "quantityshrpar": "18,828.00",
                        "pctofnetassetsstd": "0.1599",
                        "mktvalue": "3,214,881.00",
                        "notionalmktvalue": "3,214,881.00",
                        "assetclasscatg": "COMMON STOCK",
                        "mktcurr": "USD",
                        "contracts": "0.00000"
                      },
                      {
                        "fundid": "25773",
                        "asofdate": "06/11/2026",
                        "asofdatestd": "2026-06-11",
                        "frequency": "DAILY",
                        "secticker": "USD",
                        "secname": "U.S. Dollar",
                        "quantityshrpar": "100.00",
                        "pctofnetassetsstd": "0.0100",
                        "mktvalue": "100.00",
                        "assetclasscatg": "CASH",
                        "mktcurr": "USD"
                      }
                    ]
                  }
                }
              }
            }
            """,
            content_type="application/json",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="FLQL", identifiers={})

    requested_url, requested_kwargs = FakeAsyncClient.requested[0]
    assert requested_url == "https://www.franklintempleton.com/api/pds/price-and-performance"
    assert requested_kwargs["json"]["operationName"] == "Holdings"
    assert requested_kwargs["json"]["variables"] == {
        "productId": "25773",
        "countryCode": "US",
        "languageCode": "en_US",
    }
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "NTRS"
    assert result.rows[0].name == "NORTHERN TRUST CORP"
    assert result.rows[0].cusip == "665859104"
    assert result.rows[0].isin == "US6658591044"
    assert result.rows[0].shares == Decimal("18828.00")
    assert result.rows[0].market_value == Decimal("3214881.00")
    assert result.rows[0].weight == Decimal("0.001599")
    assert result.rows[0].currency == "USD"
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_graphql_holdings"
    assert result.legal_metadata["source_provider"] == "franklin"
    assert result.legal_metadata["composition_date"] == "2026-06-11"


@pytest.mark.asyncio
async def test_calamos_adapter_parses_native_xlsx_holdings(monkeypatch):
    adapter = get_holdings_adapter("calamos")
    assert adapter is not None

    workbook = _xlsx_workbook(
        [
            [
                "Holdings",
                "Calamos S&P 500 Structured Alt Protection ETF - May",
                "",
                "",
                "",
                "",
                "As of Date: 2026-06-11",
            ],
            [
                "Ticker",
                "Security Description",
                "SEDOL",
                "CUSIP",
                "ISIN",
                "Local Currency",
                "Weight %",
                "Shares",
                "Market Value Base",
            ],
            ["", "NET OTHER ASSETS", "", "", "", "", "-0.07830834", "0", "-43984.02"],
            [
                "4SPY 270430 C 4.96",
                "SPDR S&P 500 ETF Trust (SPY) Long Call Option",
                "",
                "",
                "",
                "United States dollar",
                "100.71052258",
                "778",
                "56566824",
            ],
            [
                "4SPY 270430 P 718.66",
                "SPDR S&P 500 ETF Trust (SPY) Long Put Option",
                "",
                "",
                "",
                "United States dollar",
                "4.84243807",
                "778",
                "2719888",
            ],
            ["", "US DOLLAR", "", "", "", "", "0.76538873", "429901.55", "429901.55"],
            ["Holdings and weightings are subject to change daily."],
        ]
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            content=workbook,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="CPSM", identifiers={})

    requested_url, requested_kwargs = FakeAsyncClient.requested[0]
    assert requested_url == "https://www.calamos.com/download/CPSMHoldings.xlsx"
    assert requested_kwargs["headers"]["Referer"] == "https://www.calamos.com/"
    assert len(result.rows) == 4
    assert result.rows[0].row_type == "cash"
    assert result.rows[0].symbol is None
    assert result.rows[0].weight == Decimal("-0.0007830834")
    assert result.rows[0].market_value == Decimal("-43984.02")
    assert result.rows[1].symbol == "4SPY 270430 C 4.96"
    assert result.rows[1].holding_type == "derivative"
    assert result.rows[1].shares == Decimal("778")
    assert result.rows[1].market_value == Decimal("56566824")
    assert result.rows[1].weight == Decimal("1.0071052258")
    assert result.rows[-1].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == "issuer_xlsx_holdings_download"
    assert result.legal_metadata["source_provider"] == "calamos"
    assert result.legal_metadata["composition_date"] == "2026-06-11"


@pytest.mark.asyncio
async def test_janus_henderson_adapter_parses_full_holdings_html(monkeypatch):
    adapter = get_holdings_adapter("janus_henderson")
    assert adapter is not None

    raw_html = """
    <html>
      <body>
        <table>
          <thead>
            <tr>
              <th>Full Portfolio Holdings (As of 06/12/2026)</th>
              <th>Ticker</th>
              <th>Cusip</th>
              <th>Underlying Security</th>
              <th>Strike Price</th>
              <th>Quantity (Shares/ Par/ Units/ Contracts)</th>
              <th>Notional Value</th>
              <th>Market Value</th>
              <th>Weight %</th>
              <th>Current Market Value</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>KKR CLO 35 AR 4.87523% 20-JAN-2038, 4.88%, 01/20/38</td>
              <td>KKR 35A</td>
              <td>48254LAN5</td>
              <td></td>
              <td>-</td>
              <td>249,004,000</td>
              <td>$251,147,474</td>
              <td>$251,147,474</td>
              <td>0.88</td>
              <td>$249,259,105</td>
            </tr>
            <tr>
              <td>JPM USD CASH</td>
              <td>USD</td>
              <td>USD</td>
              <td></td>
              <td>-</td>
              <td>100</td>
              <td>$100</td>
              <td>$100</td>
              <td>0.01</td>
              <td>$100</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [FakeResponse(text=raw_html, content_type="text/html")]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="JAAA", identifiers={})

    requested_url, requested_kwargs = FakeAsyncClient.requested[0]
    assert requested_url == (
        "https://www.janushenderson.com/en-us/advisor/product/"
        "jaaa-aaa-clo-etf/full-holdings/"
    )
    assert requested_kwargs["headers"]["Accept"] == "text/html,*/*"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "KKR 35A"
    assert result.rows[0].name == "KKR CLO 35 AR 4.87523% 20-JAN-2038, 4.88%, 01/20/38"
    assert result.rows[0].cusip == "48254LAN5"
    assert result.rows[0].shares == Decimal("249004000")
    assert result.rows[0].market_value == Decimal("251147474")
    assert result.rows[0].weight == Decimal("0.0088")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_full_holdings_html_table"
    assert result.legal_metadata["source_provider"] == "janus_henderson"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_northern_trust_adapter_parses_flexshares_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("northern_trust")
    assert adapter is not None

    raw_csv = "\n".join(
        [
            (
                "Date,CUSIP,ISIN,SEDOL,Name,Ticker,Market Value-Local,"
                "Market Value-Base,Fund Weight %,Shares Held,Coupon,Maturity,"
                "Sector Type,Country"
            ),
            (
                "06/12/2026,037833100,US0378331005,2046251,"
                "APPLE INC COMMON STOCK USD 0.00001,AAPL,181555364.00,"
                "181555364.00,8.2419,623623,.000,,Information Technology,"
                "United States"
            ),
            (
                "06/12/2026,478160104,US4781601046,2475833,"
                "JOHNSON &#38; JOHNSON COMMON STOCK USD 1,JNJ,58717120.77,"
                "58717120.77,2.6655,243771,.000,,Health Care,United States"
            ),
            "06/12/2026,USD,,,,US DOLLAR,100,100,0.01,100,,,,United States",
        ]
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [FakeResponse(text=raw_csv, content_type="text/csv")]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="QDF", identifiers={})

    requested_url, requested_kwargs = FakeAsyncClient.requested[0]
    assert requested_url == (
        "https://www.flexshares.com/content/dam/ntflexshares/fund/qdf/qdf-holdings.csv"
    )
    assert requested_kwargs["headers"]["Referer"] == "https://www.flexshares.com/"
    assert len(result.rows) == 3
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].name == "APPLE INC COMMON STOCK USD 0.00001"
    assert result.rows[0].cusip == "037833100"
    assert result.rows[0].isin == "US0378331005"
    assert result.rows[0].sedol == "2046251"
    assert result.rows[0].weight == Decimal("0.082419")
    assert result.rows[0].shares == Decimal("623623")
    assert result.rows[0].market_value == Decimal("181555364.00")
    assert result.rows[1].name == "JOHNSON & JOHNSON COMMON STOCK USD 1"
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_flexshares_holdings_csv"
    assert result.legal_metadata["source_provider"] == "northern_trust"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_allianz_adapter_filters_multi_fund_csv_and_preserves_option_rows(monkeypatch):
    adapter = get_holdings_adapter("allianz")
    assert adapter is not None

    raw_csv = "\n".join(
        [
            (
                "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,"
                "MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,"
                "MoneyMarketFlag,IncomeByPosition,MaturityDate,StrikePrice"
            ),
            (
                "6/12/2026,FEBT,4SPY  270129C00005120,4SPY  270129C00005120,"
                "SPY 01/29/2027 5.12 C,2206,727.7041,160531524.46,101.26%,"
                "158541411.44,3900000,156,,,1/29/2027,5.12"
            ),
            (
                "6/12/2026,FEBT,Cash&Other,Cash&Other,Cash&Other,"
                "2177192.12,1,2177192.12,1.37%,158541411.44,3900000,156,Y,,,"
            ),
            (
                "6/12/2026,FLJJ,4SPY  260630C00005180,4SPY  260630C00005180,"
                "SPY 06/30/2026 5.18 C,118,730.6193,8621307.74,102.93%,"
                "8375533.43,250000,10,,,6/30/2026,5.18"
            ),
        ]
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [FakeResponse(text=raw_csv, content_type="text/csv")]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="FEBT", identifiers={})

    requested_url, requested_kwargs = FakeAsyncClient.requested[0]
    assert requested_url == (
        "https://www.allianzim.com/wp-content/uploads/feeds/BBH_FOR_ALZ_ETF_PVAL_WEB.csv"
    )
    assert requested_kwargs["headers"]["Referer"] == "https://www.allianzim.com/etfs/"
    assert len(result.rows) == 2
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "SPY 01/29/2027 5.12 C"
    assert result.rows[0].cusip is None
    assert result.rows[0].holding_type == "option"
    assert result.rows[0].weight == Decimal("1.0126")
    assert result.rows[0].shares == Decimal("2206")
    assert result.rows[0].market_value == Decimal("160531524.46")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_multi_fund_holdings_csv"
    assert result.legal_metadata["source_provider"] == "allianz"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_pacer_adapter_fetches_known_public_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("pacer")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,"
                    "MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits",
                    "2026-06-12,COWZ,AAPL,037833100,Apple Inc,\"1,000\",200,"
                    "\"200,000\",4.5%,1000000,10000,1",
                    "2026-06-12,COWZ,MSFT,594918104,Microsoft Corp,500,350,"
                    "175000,3.5%,1000000,10000,1",
                ]
            ),
            content_type="text/csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="COWZ", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.paceretfs.com/usbank/live/fsb0.pacer.x330.COWZ_Holdings.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].name == "Apple Inc"
    assert result.rows[0].cusip == "037833100"
    assert result.rows[0].shares == Decimal("1000")
    assert result.rows[0].market_value == Decimal("200000")
    assert result.rows[0].weight == Decimal("0.045")
    assert result.legal_metadata["route_resolution"] == "issuer_profile_metadata"
    assert result.legal_metadata["source_provider"] == "pacer"


@pytest.mark.asyncio
async def test_acquirers_adapter_fetches_native_holdings_workbook(monkeypatch):
    adapter = get_holdings_adapter("acquirers")
    assert adapter is not None
    xls_payload = b"\xd0\xcf\x11\xe0acquirers-xls"

    def fake_parse_xls(raw_workbook):
        assert raw_workbook == xls_payload
        return (
            [
                SimpleNamespace(
                    symbol="AAPL",
                    name="Apple Inc",
                    cusip="037833100",
                    isin=None,
                    sedol=None,
                    weight=Decimal("0.0518"),
                    shares=Decimal("100"),
                    market_value=Decimal("20000"),
                    currency=None,
                    country=None,
                    holding_type="equity",
                    row_type="security",
                    source_row_id=None,
                    extra_data={},
                )
            ],
            [
                [
                    "Percentage Of Net Assets",
                    "Name",
                    "Identifier",
                    "CUSIP",
                    "Shares Held",
                    "Market Value",
                ],
                ["5.18%", "Apple Inc", "AAPL", "037833100", "100", "20000"],
            ],
        )

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            content=xls_payload,
            content_type="application/vnd.ms-excel",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("app.services.etf_holdings_adapters.parse_holdings_xls", fake_parse_xls)

    result = await adapter.fetch_latest(symbol="ZIG", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://acquirersfund.com/download-holdings-usbanks.php?fticker=ZIG"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == "https://acquirersfund.com/"
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].cusip == "037833100"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_xls"
    assert result.legal_metadata["source_provider"] == "acquirers"
    assert result.legal_metadata["source_format"] == "xls"


@pytest.mark.asyncio
async def test_graniteshares_adapter_discovers_legacy_xls_holdings(monkeypatch):
    adapter = get_holdings_adapter("graniteshares")
    assert adapter is not None

    def fake_parse_xls(raw_workbook):
        assert raw_workbook == b"legacy-xls"
        return (
            [
                SimpleNamespace(
                    symbol="NVDA",
                    name="NVIDIA CORP",
                    cusip="67066G104",
                    isin=None,
                    sedol=None,
                    weight=Decimal("0.9723"),
                    shares=Decimal("100"),
                    market_value=Decimal("120000"),
                    currency="USD",
                    country=None,
                    holding_type="equity",
                    row_type="security",
                    source_row_id=None,
                    extra_data={},
                )
            ],
            [
                ["Ticker", "Name", "CUSIP", "Shares", "Value", "Allocation"],
                ["NVDA", "NVIDIA CORP", "67066G104", "100", "120000", "97.23%"],
            ],
        )

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <html>
              <body>
                <a href="/media/nwnlfyi3/nvd_holdings_file_20260611.xls">
                  Download Holdings
                </a>
              </body>
            </html>
            """,
            content_type="text/html",
        ),
        FakeResponse(
            content=b"legacy-xls",
            content_type="application/vnd.ms-excel",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("app.services.etf_holdings_adapters.parse_holdings_xls", fake_parse_xls)

    result = await adapter.fetch_latest(symbol="NVD", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://graniteshares.com/etfs/nvd/"
    assert FakeAsyncClient.requested[1][0] == (
        "https://graniteshares.com/media/nwnlfyi3/nvd_holdings_file_20260611.xls"
    )
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].weight == Decimal("0.9723")
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_discovery"
    assert result.legal_metadata["source_provider"] == "graniteshares"
    assert result.legal_metadata["source_format"] == "xls"


@pytest.mark.asyncio
async def test_axs_adapter_filters_dated_aggregate_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("axs")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="not found",
            content_type="text/html",
            status_code=404,
        ),
        FakeResponse(
            text="\n".join(
                [
                    (
                        "ETF Ticker,Date,ISIN,CUSIP,SEDOL,Ticker,Description,Security Type,"
                        "Market Value,Maturity Date,Shares,Security Price,Asset Currency,"
                        "Shares Outstanding,Total Net Assets,Market Value Weight"
                    ),
                    (
                        "OTHER,6/11/2026,,,0000000,OTHER,Other Holding,EQUITY,10,,1,10,"
                        "USD,100,1000,1.00%"
                    ),
                    (
                        "TARK,6/11/2026,,,,AXSBSBNFV9WFB,CFD ARK INNOVATION ETF,SWAPS,"
                        "15626332.26,,207081,75.46,USD,446380,18834132.78,82.97%"
                    ),
                    (
                        "TARK,6/11/2026,,CASHUSD,,USD,CASHUSD,CASH,133695391.66,,"
                        "133695391.66,,USD,6531350,124655072.01,107.25%"
                    ),
                ]
            ),
            content_type="application/octet-stream",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="TARK", identifiers={})

    assert FakeAsyncClient.requested[0][0].endswith(
        f"BBH_AXS_ETF_PVAL_WEB.{date.today().strftime('%Y%m%d')}.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "AXSBSBNFV9WFB"
    assert result.rows[0].name == "CFD ARK INNOVATION ETF"
    assert result.rows[0].market_value == Decimal("15626332.26")
    assert result.rows[0].shares == Decimal("207081")
    assert result.rows[0].weight == Decimal("0.8297")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_dated_aggregate_holdings_csv"
    assert result.legal_metadata["source_provider"] == "axs"
    assert result.legal_metadata["composition_date"] == "2026-06-11"


@pytest.mark.asyncio
async def test_kraneshares_adapter_parses_public_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("kraneshares")
    assert adapter is not None

    holdings_csv = "\n".join(
        [
            '"KWEB Holdings","As of 2026-06-11","Holdings Are Subject To Change"',
            'Rank,"Company Name","% of Net Assets",Ticker,Identifier,"Shares Held","Market Value($)"',
            '1,"TENCENT HOLDINGS LTD",10.08,700,KYG875721634,"9,923,675","578,937,496"',
            '2,"PDD HOLDINGS INC",7.50,PDD,US7223041028,"5,297,745","430,706,669"',
        ]
    )
    requested: list[tuple[str, dict]] = []

    def fake_get(url, **kwargs):
        requested.append((url, kwargs))
        response = FakeResponse(text=holdings_csv, content_type="text/csv")
        response.url = url
        return response

    monkeypatch.setattr("app.services.etf_holdings_adapters.requests.get", fake_get)

    result = await adapter.fetch_latest(
        symbol="KWEB",
        source_url="https://kraneshares.com/csv/06_11_2026_kweb_holdings.csv",
        identifiers={},
    )

    assert requested[0][0] == (
        "https://kraneshares.com/csv/06_11_2026_kweb_holdings.csv"
    )
    assert result.rows[0].symbol == "700"
    assert result.rows[0].name == "TENCENT HOLDINGS LTD"
    assert result.rows[0].isin == "KYG875721634"
    assert result.rows[0].weight == Decimal("0.1008")
    assert result.rows[0].shares == Decimal("9923675")
    assert result.rows[0].market_value == Decimal("578937496")
    assert result.rows[1].symbol == "PDD"
    assert result.rows[1].isin == "US7223041028"
    assert result.legal_metadata["route_resolution"] == "issuer_dated_csv_lookback"
    assert result.legal_metadata["composition_date"] == "2026-06-11"


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


@pytest.mark.parametrize(
    ("issuer", "fund_family", "name", "expected_adapter_key"),
    [
        ("Capital Group", None, "Capital Group Growth ETF", "capital_group"),
        ("Dimensional Fund Advisors", None, "Dimensional US Core Equity ETF", "dimensional"),
        ("First Trust", None, "First Trust Nasdaq Cybersecurity ETF", "first_trust"),
        ("Goldman Sachs Asset Management", None, "Goldman Sachs ActiveBeta ETF", "goldman_sachs"),
        ("Pacer", None, "Pacer US Cash Cows ETF", "pacer"),
        ("YieldMax", None, "YieldMax option income ETF", "yieldmax"),
        ("Roundhill Investments", None, "Roundhill Magnificent Seven ETF", "roundhill"),
        ("Grayscale Operating LLC", None, "Grayscale Bitcoin Trust ETF", "grayscale"),
        ("Tidal Financial Group", None, "Tidal ETF", "tidal"),
        ("BondBloxx Investment Management", None, "BondBloxx Treasury ETF", "bondbloxx"),
        (None, "FlexShares", "FlexShares Morningstar ETF", "northern_trust"),
        (None, "Xtrackers", "Xtrackers MSCI USA Climate Action ETF", "deutsche_bank"),
        (None, None, "KraneShares CSI China Internet ETF", "kraneshares"),
        (None, None, "AdvisorShares Pure US Cannabis ETF", "advisor_shares"),
        (None, None, "Teucrium Corn Fund", "teucrium"),
        ("21Shares AG", None, "21Shares Crypto Basket ETF", "21shares"),
        ("3EDGE Asset Management LP", None, "3EDGE Dynamic Fixed Income ETF", "3edge"),
        ("Acquirers Funds", None, "Acquirers Deep Value ETF", "acquirers"),
        ("Stone Ridge Holdings Group LP", None, "Stone Ridge ETF", "stone_ridge"),
        ("US Global Investors", None, "US Global Jets ETF", "us_global_investors"),
    ],
)
def test_holdings_adapter_inference_recognizes_broad_us_issuer_set(
    issuer,
    fund_family,
    name,
    expected_adapter_key,
):
    probe = infer_adapter_key(
        issuer=issuer,
        fund_family=fund_family,
        name=name,
    )

    assert probe.adapter_key == expected_adapter_key
    assert probe.status == "candidate"
    assert get_holdings_adapter(probe.adapter_key) is not None


def test_holdings_adapter_catalog_exposes_expanded_recognition_set():
    adapters = {item["adapter_key"]: item for item in holdings_adapter_catalog()}

    assert len(adapters) >= 340
    assert adapters["acquirers"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["acquirers"]["support_route_types"]
    assert adapters["first_trust"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["first_trust"]["support_route_types"]
    assert adapters["roundhill"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["roundhill"]["support_route_types"]
    assert adapters["yieldmax"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["yieldmax"]["support_route_types"]
    assert adapters["kraneshares"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["kraneshares"]["support_route_types"]
    assert adapters["advisor_shares"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["advisor_shares"]["support_route_types"]
    assert adapters["allianz"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["allianz"]["support_route_types"]
    assert adapters["teucrium"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["teucrium"]["support_route_types"]
    assert adapters["us_global_investors"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["us_global_investors"]["support_route_types"]
    assert adapters["pacer"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["pacer"]["support_route_types"]
    assert adapters["21shares"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["21shares"]["support_route_types"]
    assert adapters["renaissance_capital"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["renaissance_capital"]["support_route_types"]
    assert adapters["matthews"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["matthews"]["support_route_types"]
    assert adapters["new_york_life"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["new_york_life"]["support_route_types"]
    assert adapters["bondbloxx"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["bondbloxx"]["support_route_types"]
    assert adapters["grayscale"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["grayscale"]["support_route_types"]
    assert adapters["gmo"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["gmo"]["support_route_types"]
    assert adapters["hashdex"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["hashdex"]["support_route_types"]
    assert adapters["kurv"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["kurv"]["support_route_types"]
    for adapter_key in [
        "capital_group",
        "dimensional",
        "goldman_sachs",
        "3edge",
        "stone_ridge",
    ]:
        assert adapter_key in adapters
        assert adapters[adapter_key]["live_tested_default_route"] is False
        assert adapters[adapter_key]["supports_sec_filing_fallback"] is True
        assert "sec_edgar_filing_fallback" in adapters[adapter_key]["support_route_types"]


def test_every_registered_adapter_has_a_real_support_route():
    catalog = holdings_adapter_catalog()

    assert catalog
    for item in catalog:
        assert item["support_route_types"], item["adapter_key"]
        assert item["supports_sec_filing_fallback"] is True


def test_every_registered_adapter_can_probe_ready_with_sec_identifiers():
    for adapter_key, config in ISSUER_ADAPTER_CONFIGS.items():
        adapter = get_holdings_adapter(adapter_key)
        assert adapter is not None

        probe = adapter.probe(
            symbol="TEST",
            name="Test ETF",
            identifiers={
                "sec_cik": "0000000000",
                "sec_series_id": "S000000001",
                "sec_class_id": "C000000001",
            },
        )

        assert probe.status == "ready", adapter_key
        if not (
            config.live_tested_default_route
            or config.url_templates
            or config.product_page_templates
            or config.required_identifiers
        ):
            assert probe.source_url == "https://data.sec.gov/submissions/CIK0000000000.json"


@pytest.mark.asyncio
async def test_recognition_only_adapter_fetches_holdings_through_sec_fallback(monkeypatch):
    adapter = get_holdings_adapter("capital_group")
    assert adapter is not None

    async def fake_discover_holdings_filings(**kwargs):
        assert kwargs["cik"] == "0001234567"
        return [
            SimpleNamespace(
                accession_number="0001234567-26-000001",
                filing_url="https://www.sec.gov/Archives/edgar/data/1234567/fixture.xml",
                form="NPORT-P",
                report_date=date(2026, 5, 31),
            )
        ]

    monkeypatch.setattr(
        "app.services.etf_holdings_edgar.discover_holdings_filings",
        fake_discover_holdings_filings,
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <edgarSubmission>
              <formData>
                <genInfo>
                  <repPdDate>2026-05-31</repPdDate>
                </genInfo>
                <invstOrSecs>
                  <invstOrSec>
                    <name>Apple Inc.</name>
                    <cusip>037833100</cusip>
                    <ticker>AAPL</ticker>
                    <assetCat>Equity</assetCat>
                    <pctVal>6.5</pctVal>
                    <balance>10</balance>
                    <valUSD>2000</valUSD>
                    <curCd>USD</curCd>
                  </invstOrSec>
                </invstOrSecs>
              </formData>
            </edgarSubmission>
            """,
            content_type="application/xml",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(
        symbol="CGUS",
        identifiers={"sec_cik": "0001234567"},
    )

    assert result.rows[0].symbol == "AAPL"
    assert result.source_url == "https://www.sec.gov/Archives/edgar/data/1234567/fixture.xml"
    assert result.legal_metadata["source_provider"] == "sec"
    assert result.legal_metadata["route_resolution"] == "sec_edgar_filing_fallback"
    assert result.legal_metadata["snapshot_provenance"] == "sec_nport_reconstructed_holdings"


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
async def test_simplify_adapter_discovers_and_filters_aggregate_workbook(monkeypatch):
    adapter = get_holdings_adapter("simplify")
    assert adapter is not None

    workbook = _xlsx_workbook(
        [
            [
                "Holdings are subject to change without notice.",
                "",
                "",
                "",
                "",
                "",
                "06/11/2026",
            ],
            [
                "FUND NAME",
                "SECURITY DESCRIPTION",
                "TICKER",
                "SEDOL",
                "ISIN",
                "CUSIP",
                "Quantity",
                "BNY Prices",
                "Market Value/Exposure",
                "Weight",
            ],
            [
                "AGGH",
                "iShares Core US Aggregate Bond ETF",
                "AGG",
                "2897404",
                "US4642872265",
                "464287226",
                "4850661",
                "98.88",
                "479633359.68",
                "0.94614033",
            ],
            [
                "CTA",
                "SIMPLIFY E GOVT MONEY MKT ETF",
                "SBIL",
                "BNVVNP8",
                "US82889N2696",
                "82889N269",
                "56600",
                "100.2",
                "5671320",
                "0.44835652",
            ],
            [
                "CTA",
                "Cash",
                "Cash",
                "",
                "",
                "",
                "1000",
                "1",
                "1000",
                "0.01",
            ],
        ]
    )

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<a href="/sites/default/files/excel_holdings/'
                '2026_06_11_Simplify_Portfolio_EOD_Tracker.xlsx">'
                "Holdings - All ETFs</a>"
            ),
            content_type="text/html",
        ),
        FakeResponse(
            content=workbook,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="CTA")

    assert FakeAsyncClient.requested[0][0] == "https://www.simplify.us/etfs"
    assert FakeAsyncClient.requested[1][0].endswith(
        "/sites/default/files/excel_holdings/2026_06_11_Simplify_Portfolio_EOD_Tracker.xlsx"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "SBIL"
    assert result.rows[0].name == "SIMPLIFY E GOVT MONEY MKT ETF"
    assert result.rows[0].isin == "US82889N2696"
    assert result.rows[0].cusip == "82889N269"
    assert result.rows[0].weight == Decimal("0.44835652")
    assert result.rows[0].market_value == Decimal("5671320")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_aggregate_holdings_xlsx"
    assert result.legal_metadata["composition_date"] == "2026-06-11"


@pytest.mark.asyncio
async def test_direxion_adapter_fetches_symbol_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("direxion")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Direxion Daily S&P 500 Bull 3X ETF",
                    "SPXL",
                    "Shares Outstanding:23750001",
                    "",
                    '"TradeDate","AccountTicker","StockTicker","SecurityDescription","Shares","Price","MarketValue","Cusip","HoldingsPercent"',
                    '"6/12/2026 12:00:00 AM","SPXL","MMM","3M CO","36219.0000","157.9100","5719342.2900","88579Y101","0.0916"',
                    '"6/12/2026 12:00:00 AM","SPXS","AAPL","APPLE INC","1","200","200","037833100","2.0"',
                    '"6/12/2026 12:00:00 AM","SPXL","USD","US DOLLAR","1000","1","1000","","0.01"',
                ]
            ),
            content_type="text/csv",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="SPXL")

    assert FakeAsyncClient.requested[0][0] == "https://www.direxion.com/holdings/SPXL.csv"
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == "https://www.direxion.com/"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "MMM"
    assert result.rows[0].name == "3M CO"
    assert result.rows[0].cusip == "88579Y101"
    assert result.rows[0].weight == Decimal("0.000916")
    assert result.rows[0].shares == Decimal("36219.0000")
    assert result.rows[0].market_value == Decimal("5719342.2900")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_themes_adapter_fetches_symbol_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("themes")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "id,date,account,stock_ticker,cusip,security_name,shares,price,market_value,weightings,net_assets,shares_outstanding,creation_units,money_market_flag,country_code,country_full,sector,created_at,updated_at",
                    '1,2026-06-15,SPAM,AKAM,00971T101,"Akamai Technologies Inc",1453.000000,133.500000,193975.50,4.23,4581240.000000,120000,12.0000,0,US,"United States","Information Technology",2026-06-13T07:15:09.000000Z,2026-06-13T07:15:11.000000Z',
                    '2,2026-06-15,DRGN,TCEHY,88032Q109,"Tencent Holdings Ltd",100,60,6000,10.00,60000,1000,1,0,CN,China,"Communication Services",2026-06-13T07:15:09.000000Z,2026-06-13T07:15:11.000000Z',
                    '3,2026-06-15,SPAM,AUD,CASHAUD,"AUSTRALIAN DOLLAR",-24.460000,1.000000,-17.25,0.00,4581240.000000,120000,12.0000,0,,,,2026-06-13T07:15:09.000000Z,2026-06-13T07:15:09.000000Z',
                ]
            ),
            content_type="application/octet-stream",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="SPAM")

    assert FakeAsyncClient.requested[0][0] == (
        "https://themesetfs.com/storage/holdings/Holdings-SPAM.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "AKAM"
    assert result.rows[0].name == "Akamai Technologies Inc"
    assert result.rows[0].cusip == "00971T101"
    assert result.rows[0].weight == Decimal("0.0423")
    assert result.rows[0].shares == Decimal("1453.000000")
    assert result.rows[0].market_value == Decimal("193975.50")
    assert result.rows[0].country == "US"
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.rows[1].currency == "AUD"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-15"


@pytest.mark.asyncio
async def test_distillate_adapter_fetches_symbol_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("distillate")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag",
                    "06/15/2026,DSTL,ABBV,00287Y109,AbbVie Inc,245759.00000000,227.730000,55966697.07,3.04%,1839978777.50,30775000,1231.000000000000,",
                    "06/15/2026,DSTL,ACN,G1151C101,Accenture PLC,147256.00000000,170.280000,25074751.68,1.36%,1839978777.50,30775000,1231.000000000000,",
                    "06/15/2026,XV,ABBV,00287Y109,AbbVie Inc,100,1,100,1.00%,10000,1000,1,",
                    "06/15/2026,DSTL,Cash&Other,Cash&Other,Cash & Other,2354611.83000000,1.000000,2354611.83,0.13%,1839978777.50,30775000,1231.000000000000,Y",
                ]
            ),
            content_type="text/csv",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="DSTL")

    assert FakeAsyncClient.requested[0][0] == (
        "https://distillatecapital.com/wp-content/uploads/data-feeds/"
        "DistillateWeb.DSTL_Holdings.csv"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == (
        "https://distillatecapital.com/"
    )
    assert len(result.rows) == 3
    assert result.rows[0].symbol == "ABBV"
    assert result.rows[0].name == "AbbVie Inc"
    assert result.rows[0].cusip == "00287Y109"
    assert result.rows[0].weight == Decimal("0.0304")
    assert result.rows[0].shares == Decimal("245759.00000000")
    assert result.rows[0].market_value == Decimal("55966697.07")
    assert result.rows[1].symbol == "ACN"
    assert result.rows[1].cusip == "G1151C101"
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.rows[2].currency == "USD"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-15"


@pytest.mark.asyncio
async def test_amplify_adapter_filters_multi_account_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("amplify")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag",
                    "06/15/2026,BDRY,C5TCM M26 INDEX,C5TCM M26,Capesize 5TC FFA 180kt Timecharter Average M Jun 26,200,35196,7039200.00,19.89%,35392366.73,2850040,114,",
                    "06/15/2026,BLOK,3350 JP,B03BJ91,Metaplanet Inc,11476589,232,16618722.64,1.32%,1257961560.00,19650000,393,",
                    "06/15/2026,BLOK,AMD,007903107,Advanced Micro Devices Inc,74818,511.57,38274644.26,3.04%,1257961560.00,19650000,393,",
                    "06/15/2026,BLOK,Cash&Other,Cash&Other,Cash & Other,-4395925.92,1,-4395925.92,-0.35%,1257961560.00,19650000,393,Y",
                ]
            ),
            content_type="text/csv",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BLOK")

    assert FakeAsyncClient.requested[0][0] == (
        "https://amplifyetfs.com/wp-content/uploads/feeds/"
        "AmplifyWeb.40XL.XL_Holdings.csv"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == "https://amplifyetfs.com/"
    assert len(result.rows) == 3
    assert result.rows[0].symbol == "3350"
    assert result.rows[0].exchange == "JP"
    assert result.rows[0].name == "Metaplanet Inc"
    assert result.rows[0].cusip is None
    assert result.rows[0].sedol == "B03BJ91"
    assert result.rows[0].weight == Decimal("0.0132")
    assert result.rows[1].symbol == "AMD"
    assert result.rows[1].cusip == "007903107"
    assert result.rows[1].weight == Decimal("0.0304")
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.rows[2].currency == "USD"
    assert result.legal_metadata["route_resolution"] == "issuer_multi_account_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-15"


@pytest.mark.asyncio
async def test_volatility_shares_adapter_parses_derivative_xls(monkeypatch):
    adapter = get_holdings_adapter("volatility_shares")
    assert adapter is not None

    workbook_rows = [
        ["-1x Short VIX Futures ETF", "", ""],
        [],
        ["Description", "Shares/Contracts", "Market Value/Notional"],
        [],
        ["VIX US 07/22/26 C30", "5,400", "415,800.00"],
        ["CBOE VIX FUTURE   Jun26", "-1,047", "-18,866,940.00"],
        ["Cash & Other", "204,031,055", "204,031,055.46"],
    ]

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            content=b"\xd0\xcf\x11\xe0legacy-xls",
            content_type="application/vnd.ms-excel",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "app.services.etf_holdings_adapters.parse_holdings_xls",
        lambda raw: ([], workbook_rows),
    )

    result = await adapter.fetch_latest(symbol="SVIX")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.volatilityshares.com/download-holdings-usbanks-1933.php?fund=svix"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == (
        "https://www.volatilityshares.com/"
    )
    assert len(result.rows) == 3
    option, future, cash = result.rows
    assert option.symbol is None
    assert option.name == "VIX US 07/22/26 C30"
    assert option.holding_type == "option"
    assert option.shares == Decimal("5400")
    assert option.market_value == Decimal("415800.00")
    assert future.symbol is None
    assert future.holding_type == "future"
    assert future.shares == Decimal("-1047")
    assert future.market_value == Decimal("-18866940.00")
    assert cash.row_type == "cash"
    assert cash.currency == "USD"
    assert cash.market_value == Decimal("204031055.46")
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_xls"
    assert result.legal_metadata["source_format"] == "xls"


@pytest.mark.asyncio
async def test_wahed_adapter_discovers_public_google_sheet_holdings(monkeypatch):
    adapter = get_holdings_adapter("wahed")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<a href="https://docs.google.com/spreadsheets/d/'
                '1UC1Bk67bGuYsos_i8y_HQpNoHpVHAvqf71MbgrafJOQ/edit?gid=0#gid=0" '
                'class="downloadable-content"><h4 class="heading-small">Holdings</h4></a>'
            ),
            content_type="text/html",
        ),
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag",
                    "06/12/2026,HLAL,2602335D,BBG01Y2F01K3,TPG Inc,5608,0,0,0.00%,902657280,12800000,512,",
                    "06/12/2026,HLAL,AAPL,037833100,Apple Inc,396515,295.63,117221729.5,12.99%,902657280,12800000,512,",
                    "06/12/2026,HLAL,Cash&Other,Cash&Other,Cash & Other,1000,1,1000,0.01%,902657280,12800000,512,Y",
                    "06/12/2026,UMMA,MSFT,594918104,Microsoft Corp,100,500,50000,1.00%,5000000,1000,1,",
                ]
            ),
            content_type="text/csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="HLAL")

    assert FakeAsyncClient.requested[0][0] == "https://www.wahed.com/hlal"
    assert FakeAsyncClient.requested[1][0] == (
        "https://docs.google.com/spreadsheets/d/"
        "1UC1Bk67bGuYsos_i8y_HQpNoHpVHAvqf71MbgrafJOQ/export?format=csv&gid=0"
    )
    assert len(result.rows) == 3
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "TPG Inc"
    assert result.rows[0].cusip is None
    assert result.rows[1].symbol == "AAPL"
    assert result.rows[1].cusip == "037833100"
    assert result.rows[1].weight == Decimal("0.1299")
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.rows[2].currency == "USD"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_google_sheet"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_tema_adapter_fetches_symbol_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("tema")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "holdings_date,ticker,cusip,proper_name,shares,market_value,percent_of_nav,is_cash,country,sector",
                    "2026-06-12,KALSHI SPV,KALSHI SPV,KALSHI SPV EXPOSURE,6613,3999939.18,0.0871,0,,",
                    "2026-06-12,LRCX,512807306,LAM RESEARCH CORP,8113,2975929.53,0.0648,0,United States,Information Technology",
                    "2026-06-12,FER SM,,FERROVIAL NV,18303,1234642.99,0.0269,0,Netherlands,Industrials",
                    "2026-06-12,CASH,,Cash & Other,1,1000,0.0010,1,,",
                ]
            ),
            content_type="text/csv",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="TOLL")

    assert FakeAsyncClient.requested[0][0] == (
        "https://temaetfs.com/hubfs/Website/Holdings/TOLL-holdings.csv"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == "https://temaetfs.com/"
    assert len(result.rows) == 4
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "KALSHI SPV EXPOSURE"
    assert result.rows[0].weight == Decimal("0.0871")
    assert result.rows[1].symbol == "LRCX"
    assert result.rows[1].cusip == "512807306"
    assert result.rows[1].country == "United States"
    assert result.rows[2].symbol == "FER"
    assert result.rows[2].exchange == "SM"
    assert result.rows[2].country == "Netherlands"
    assert result.rows[3].row_type == "cash"
    assert result.rows[3].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_main_management_adapter_fetches_symbol_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("main_management")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Main BuyWrite ETF",
                    "Fund Holdings Data as of 06/12/2026",
                    "Name, Security Identifier, Symbol, Net Assets %, Market Price, Shares Held, Market Value, Market Value %",
                    "SS FINANCIAL SEL,81369Y605,XLF US,1022.44,53.34,2351200,125413008,10.23",
                    "XLE US 12/31/26 C52,XLE C52   12/31/2026,XLE   261231C00052000,-20.74,7.9,-3221,-2544590,-0.21",
                    "US DOLLARS,USD,USD,8.24,1,1010353,1010353,0.08",
                ]
            ),
            content_type="application/octet-stream",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BUYW")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.mainmgtetfs.com/etfs/download-buyw.php"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == (
        "https://www.mainmgtetfs.com/"
    )
    assert len(result.rows) == 3
    assert result.rows[0].symbol == "XLF"
    assert result.rows[0].exchange == "US"
    assert result.rows[0].name == "SS FINANCIAL SEL"
    assert result.rows[0].cusip == "81369Y605"
    assert result.rows[0].weight == Decimal("0.1023")
    assert result.rows[1].holding_type == "option"
    assert result.rows[1].symbol == "XLE 261231C00052000"
    assert result.rows[1].weight == Decimal("-0.0021")
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.rows[2].currency == "USD"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_procure_adapter_discovers_current_holdings_csv_from_product_page(monkeypatch):
    adapter = get_holdings_adapter("procuream")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<a href="https://procureetfs.com/wp-content/uploads/2026/06/'
                'UFO-JP-Holdings-Jun-12-2026.csv">Download All Holdings (.xls)</a>'
            ),
            content_type="text/html",
        ),
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag",
                    "06/12/2026,UFO,RKLB,773121108,Rocket Lab Corp,617581,114.78,70885947.18,6.40%,1107289600,19625000,785,",
                    "06/12/2026,UFO,MDA CN,BMZ0WL3,MDA Space Ltd,1363203,57.05,55481170.79,5.01%,1107289600,19625000,785,",
                    "06/12/2026,UFO,USD,,US DOLLAR,1000,1,1000,0.01%,1107289600,19625000,785,1",
                ]
            ),
            content_type="text/csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="UFO")

    assert FakeAsyncClient.requested[0][0] == "https://procureetfs.com/ufo/"
    assert FakeAsyncClient.requested[1][0] == (
        "https://procureetfs.com/wp-content/uploads/2026/06/"
        "UFO-JP-Holdings-Jun-12-2026.csv"
    )
    assert FakeAsyncClient.requested[1][1]["headers"]["Referer"] == "https://procureetfs.com/"
    assert len(result.rows) == 3
    assert result.rows[0].symbol == "RKLB"
    assert result.rows[0].name == "Rocket Lab Corp"
    assert result.rows[0].cusip == "773121108"
    assert result.rows[0].weight == Decimal("0.0640")
    assert result.rows[0].shares == Decimal("617581")
    assert result.rows[0].market_value == Decimal("70885947.18")
    assert result.rows[1].symbol == "MDA"
    assert result.rows[1].exchange == "CN"
    assert result.rows[1].sedol == "BMZ0WL3"
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_discovery"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_horizon_kinetics_adapter_fetches_daily_xlsx(monkeypatch):
    adapter = get_holdings_adapter("horizon_kinetics")
    assert adapter is not None

    workbook_rows = [
        ["Data as of:", "% Net Assets", "Name", "Ticker", "CUSIP", "Shares Held", "Market Value"],
        ["06/15/26", "0.0572", "Landbridge Co LLC", "LB", "514952100", "1,285,033", "$89,039,937"],
        ["06/15/26", "0.0509", "PrairieSky Royalty Ltd", "PSK CN", "BN320L4", "3,255,775", "$79,249,964"],
        ["06/15/26", "0.001", "Cash & Other", "Cash&Other", "Cash&Other", "1,584,462", "$1,584,462"],
        ["06/15/26", "0.00%", "JAPANESE YEN", "JPY", "CASHJPY", "48,524,515", "$302,852"],
    ]

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            content=b"fake-xlsx",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "app.services.etf_holdings_adapters.parse_xlsx_table",
        lambda content: workbook_rows,
    )

    result = await adapter.fetch_latest(symbol="INFL")

    assert FakeAsyncClient.requested[0][0] == (
        "https://horizonkinetics.com/wp/wp-admin/admin-ajax.php"
        "?action=daily_holdings&ticker=INFL&prefix=Holdings"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == (
        "https://horizonkinetics.com/"
    )
    assert len(result.rows) == 4
    assert result.rows[0].symbol == "LB"
    assert result.rows[0].name == "Landbridge Co LLC"
    assert result.rows[0].cusip == "514952100"
    assert result.rows[0].weight == Decimal("0.0572")
    assert result.rows[0].shares == Decimal("1285033")
    assert result.rows[0].market_value == Decimal("89039937")
    assert result.rows[1].symbol == "PSK"
    assert result.rows[1].exchange == "CN"
    assert result.rows[1].sedol == "BN320L4"
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.rows[3].row_type == "cash"
    assert result.rows[3].currency == "JPY"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_xlsx"
    assert result.legal_metadata["composition_date"] == "2026-06-15"


@pytest.mark.asyncio
async def test_world_gold_council_adapter_parses_gold_archive_workbook(monkeypatch):
    adapter = get_holdings_adapter("world_gold_council")
    assert adapter is not None

    workbook = _xlsx_workbook_sheets(
        [
            [["Disclaimer"], ["Not holdings data"]],
            [
                [
                    "Date",
                    "Closing Price",
                    "Ounces of Gold per Share",
                    "NAV/Share at 10:30am NYT",
                    "Indicative Price per Share at 4:15pm NYT",
                    "Mid point of bid/ask spread at 4:15pm NYT",
                    "Premium/Discount of GLD Mid Point vs Indicative Value of GLD at 4:15pm NYT",
                    "Daily Share Volume",
                    "Total Ounces of Gold in the Trust",
                    "Tonnes of Gold",
                    "Total Net Asset Value in the Trust",
                ],
                ["10-Jun-2026", "374.58", "0.09179084", "382.855019", "374.399", "374.68", "0.0751", "13956163", "32589536.27", "1013.64", "135913531902.03"],
                ["11-Jun-2026", "386.32", "0.09178959", "374.028795", "386.909", "386.21", "-0.1807", "12622475", "32589536.27", "1013.64", "132780222324.90"],
                ["12-Jun-2026", "US Holiday", "US Holiday", "US Holiday", "US Holiday", "US Holiday", "US Holiday", "US Holiday", "US Holiday", "US Holiday", "US Holiday"],
            ],
        ]
    )

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            content=workbook,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="GLD")

    assert FakeAsyncClient.requested[0][0] == (
        "https://api.spdrgoldshares.com/api/v1/historical-archive"
        "?product=gld&exchange=NYSE&lang=en"
    )
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.symbol is None
    assert row.name == "Gold Bullion"
    assert row.holding_type == "commodity"
    assert row.row_type == "commodity"
    assert row.weight == Decimal("1")
    assert row.shares == Decimal("32589536.27")
    assert row.market_value == Decimal("132780222324.90")
    assert row.extra_data["tonnes_of_gold"] == "1013.64"
    assert row.extra_data["composition_date"] == "2026-06-11"
    assert result.legal_metadata["source_provider"] == "world_gold_council"
    assert result.legal_metadata["route_resolution"] == "issuer_gold_trust_historical_archive"
    assert result.legal_metadata["composition_date"] == "2026-06-11"


@pytest.mark.asyncio
async def test_inspire_adapter_fetches_quarterly_holdings_json(monkeypatch):
    adapter = get_holdings_adapter("inspire")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text='''[
              {
                "as_of_date": "2026-02-27T00:00:00Z",
                "country": "US",
                "currency": "USD",
                "cusip": "149123101",
                "etfticker": "BIBL",
                "isin": "US1491231015",
                "market_value": 34575765.18,
                "px_usd": 742.83,
                "security_name": "CATERPILLAR INC",
                "security_number": "149123101",
                "shares_held": 46546.0,
                "ticker": "CAT",
                "weight": 0.08560419789457369
              },
              {
                "as_of_date": "2026-02-27T00:00:00Z",
                "country": "US",
                "currency": "USD",
                "cusip": "133131BB7",
                "etfticker": "BIBL",
                "isin": null,
                "market_value": 10657632.02,
                "px_usd": 1.0247723096153847,
                "security_name": "Camden Property Trust",
                "security_number": "133131BB7",
                "shares_held": 10400000.0,
                "ticker": "Camden Property Trust 4.9 01/15/34",
                "weight": 0.022370280921019062
              },
              {
                "as_of_date": "2026-02-27T00:00:00Z",
                "etfticker": "IBD",
                "security_name": "Other Fund Row",
                "ticker": "OTHER",
                "weight": 0.5
              }
            ]''',
            content_type="application/json",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(
        symbol="BIBL",
        identifiers={"holdings_date": "20260228"},
    )

    assert FakeAsyncClient.requested[0][0] == (
        "https://data.etflogic.io/prod?apikey=263752e3-765e-4dab-aa89-ab3d6a49d7dc"
        "&function=holdings&format=json&ticker=BIBL&date=20260228"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == (
        "https://www.inspireetf.com/"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "CAT"
    assert result.rows[0].name == "CATERPILLAR INC"
    assert result.rows[0].cusip == "149123101"
    assert result.rows[0].isin == "US1491231015"
    assert result.rows[0].weight == Decimal("0.08560419789457369")
    assert result.rows[0].shares == Decimal("46546.0")
    assert result.rows[0].market_value == Decimal("34575765.18")
    assert result.rows[1].symbol is None
    assert result.rows[1].holding_type == "fixed_income"
    assert result.rows[1].cusip == "133131BB7"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_page_public_quarterly_holdings_api"
    )
    assert result.legal_metadata["source_frequency"] == "quarterly"
    assert result.legal_metadata["composition_date"] == "2026-02-27"


@pytest.mark.asyncio
async def test_bny_mellon_adapter_discovers_daily_xls_and_parses_holdings(monkeypatch):
    adapter = get_holdings_adapter("bny_mellon")
    assert adapter is not None

    workbook_rows = [
        ["Fund Name: ", "BNYM Core Bond ETF"],
        ["Full Holdings (As of 2026-06-12)"],
        [],
        [
            "Ticker",
            "CUSIP",
            "Asset Class",
            "Security Description",
            "Weight of Holdings ",
            "Coupon Rate",
            "Shares/Par ",
            "Market Value",
        ],
        [
            "",
            "91282CPZ8",
            "TREASURY NOTE",
            "US TREASURY N/B 4.125 2/15/2036",
            "0.56%",
            "4.13",
            "12290000",
            "11978909.38",
        ],
    ]

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                "<a target='_blank' href='/content/dam/im/documents/holdings/"
                "daily/2026/06/12/13475353.xls'>Download Total Holdings</a>"
            ),
            content_type="text/html",
        ),
        FakeResponse(content=b"fake-xls", content_type="application/vnd.ms-excel"),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "app.services.etf_holdings_adapters.parse_holdings_xls",
        lambda raw: ([], workbook_rows),
    )

    result = await adapter.fetch_latest(symbol="BKAG")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.bny.com/investments/us/en/individual/products/etf/fund/"
        "bny-mellon-core-bond-etf.html"
    )
    assert FakeAsyncClient.requested[1][0] == (
        "https://www.bny.com/content/dam/im/documents/holdings/daily/2026/06/12/"
        "13475353.xls"
    )
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "US TREASURY N/B 4.125 2/15/2036"
    assert result.rows[0].cusip == "91282CPZ8"
    assert result.rows[0].weight == Decimal("0.0056")
    assert result.rows[0].shares == Decimal("12290000")
    assert result.rows[0].market_value == Decimal("11978909.38")
    assert result.rows[0].holding_type == "treasury note"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_daily_holdings_xls"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_harbor_adapter_parses_gatsby_page_data_full_holdings(monkeypatch):
    adapter = get_holdings_adapter("harbor")
    assert adapter is not None

    payload = {
        "result": {
            "data": {
                "contentstackProductV2": {
                    "product_tabs": [
                        {
                            "data_section": {
                                "section": [
                                    {
                                        "api_reference": [
                                            {
                                                "data": {
                                                    "fullHoldings": [
                                                        {
                                                            "calendar": {
                                                                "date": "2026-06-11T00:00:00.000Z",
                                                            },
                                                            "key": 3687147,
                                                            "ticker": "NVDA",
                                                            "sedol": "2379504",
                                                            "cusip": "67066G104",
                                                            "shares": 601110,
                                                            "weight": 0.1112670251,
                                                            "marketValue": 123149405.7,
                                                            "securityName": "NVIDIA CORP",
                                                            "assetGroup": "EQUITY",
                                                        }
                                                    ],
                                                }
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                    ],
                }
            }
        }
    }

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [FakeResponse(text=__import__("json").dumps(payload), content_type="application/json")]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="WINN")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.harborcapital.com/page-data/etf/winn/page-data.json"
    )
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].name == "NVIDIA CORP"
    assert result.rows[0].cusip == "67066G104"
    assert result.rows[0].sedol == "2379504"
    assert result.rows[0].weight == Decimal("0.1112670251")
    assert result.rows[0].shares == Decimal("601110")
    assert result.rows[0].market_value == Decimal("123149405.7")
    assert result.rows[0].holding_type == "equity"
    assert result.legal_metadata["route_resolution"] == "issuer_gatsby_page_data_full_holdings"
    assert result.legal_metadata["composition_date"] == "2026-06-11"


@pytest.mark.asyncio
async def test_grayscale_adapter_parses_embedded_holdings_data(monkeypatch):
    adapter = get_holdings_adapter("grayscale")
    assert adapter is not None

    html = (
        '<html><script>self.__next_f.push([1,"'
        '"productData":{"ticker":"GBTC","name":"Grayscale Bitcoin Trust ETF",'
        '"pricingDataDate":"06/12/2026","cusip":"389637109",'
        '"isin":"US3896371099","totalAssetInTrust":"142,551.1892"},'
        '"holdingsData":[{"id":1,"symbol":"BTC","name":"Bitcoin",'
        '"assetPerShare":"0.00077617","weight":1,'
        '"date":"2026-06-12"}]'
        '"])</script></html>'
    )

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [FakeResponse(text=html, content_type="text/html")]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="GBTC")

    assert FakeAsyncClient.requested[0][0] == "https://etfs.grayscale.com/gbtc"
    assert result.rows[0].symbol == "BTC"
    assert result.rows[0].name == "Bitcoin"
    assert result.rows[0].weight == Decimal("1")
    assert result.rows[0].currency == "USD"
    assert result.rows[0].holding_type == "crypto"
    assert result.rows[0].row_type == "crypto"
    assert result.rows[0].extra_data["asset_per_share"] == "0.00077617"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_embedded_json"
    assert result.legal_metadata["source_format"] == "embedded_json"
    assert result.legal_metadata["composition_date"] == "06/12/2026"


@pytest.mark.asyncio
async def test_gmo_adapter_fetches_symbol_holdings_workbook(monkeypatch):
    adapter = get_holdings_adapter("gmo")
    assert adapter is not None

    workbook_rows = [
        ["Holdings - Systematic Investment Grade Credit ETF"],
        ["As of 06/12/2026 (%)"],
        [
            "Ticker",
            "Name",
            "CUSIP",
            "Shares Held",
            "% of Net Assets",
            "Market Value",
            "Asset Class",
        ],
        ["", "STATE STR INSTL INVT TR", "85799J9Y2", "185080.1", "0.7", "185080.1", "Short Term"],
        ["", "GOLDMAN SACHS GROUP INC", "38141GXA7", "97000", "0.3", "87425.5", "Bond"],
    ]
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(content=b"fake-xlsx", content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "app.services.etf_holdings_adapters.parse_xlsx_table",
        lambda raw: workbook_rows,
    )

    result = await adapter.fetch_latest(symbol="INVG")

    requested_url, requested_kwargs = FakeAsyncClient.requested[0]
    assert requested_url == (
        "https://www.gmo.com/globalassets/documents---manually-loaded/"
        "documents/systematic-investment-grade-credit-etf_etf_holdings/"
    )
    assert requested_kwargs["headers"]["Referer"] == (
        "https://www.gmo.com/americas/product-index-page/fixed-income/"
        "systematic-investment-grade-credit-strategy/"
        "systematic-investment-grade-credit-etf/"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "STATE STR INSTL INVT TR"
    assert result.rows[0].cusip == "85799J9Y2"
    assert result.rows[0].shares == Decimal("185080.1")
    assert result.rows[0].market_value == Decimal("185080.1")
    assert result.rows[0].weight == Decimal("0.007")
    assert result.rows[0].holding_type == "short term"
    assert result.rows[1].holding_type == "bond"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_xlsx"
    assert result.legal_metadata["source_provider"] == "gmo"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_hashdex_adapter_fetches_product_page_linked_workbook(monkeypatch):
    adapter = get_holdings_adapter("hashdex")
    assert adapter is not None

    workbook_rows = [
        ["Reference Date", "06-12-2026"],
        ["Name", "Shares", "Price", "Weight"],
        ["Cash & Other", "298.56", "1", "-"],
        ["Bitcoin", "191.57", "63,600.05", "99.41%"],
        ["First American Government Obligations Fund 12/01/2031", "427.39", "100", "0.35%"],
    ]
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<a href="https://hdx-website-cms-prod-upload-bucket.s3.amazonaws.com/'
                'DEFI_Holdings.xlsx">Download Holdings</a>'
            ),
            content_type="text/html",
        ),
        FakeResponse(content=b"fake-xlsx", content_type="application/octet-stream"),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(
        "app.services.etf_holdings_adapters.parse_xlsx_table",
        lambda raw: workbook_rows,
    )

    result = await adapter.fetch_latest(symbol="DEFI")

    assert FakeAsyncClient.requested[0][0] == "https://hashdex-etfs.com/DEFI"
    assert FakeAsyncClient.requested[1][0] == (
        "https://hdx-website-cms-prod-upload-bucket.s3.amazonaws.com/DEFI_Holdings.xlsx"
    )
    assert result.rows[0].name == "Cash & Other"
    assert result.rows[0].row_type == "cash"
    assert result.rows[1].symbol == "BTC"
    assert result.rows[1].name == "Bitcoin"
    assert result.rows[1].holding_type == "crypto"
    assert result.rows[1].weight == Decimal("0.9941")
    assert result.rows[1].shares == Decimal("191.57")
    assert result.rows[1].market_value == Decimal("12183861.5785")
    assert result.rows[2].holding_type == "fund"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_discovery"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_kurv_adapter_fetches_public_holdings_csv_without_fake_cusips(monkeypatch):
    adapter = get_holdings_adapter("kurv")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Ticker,CUSIP,Description,Market Value,% of fund,Quantity",
                    "2AAPL 260918C00220000,2AAPL 260918C00220000,AAPL 09/18/2026 220 C,373352.50,6.47%,50.00000000",
                    "AAPL,037833100,Apple Inc,500000.00,8.66%,1000.00000000",
                    "CASH,,Cash,100.00,0.00%,100.00000000",
                ]
            ),
            content_type="text/csv",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="AAPY")

    assert FakeAsyncClient.requested[0][0] == (
        "https://web.services.kurvinvest.com/etfdata/AAPY/holdings.csv"
    )
    assert result.rows[0].symbol == "2AAPL 260918C00220000"
    assert result.rows[0].cusip is None
    assert result.rows[0].holding_type == "option"
    assert result.rows[0].weight == Decimal("0.0647")
    assert result.rows[1].symbol == "AAPL"
    assert result.rows[1].cusip == "037833100"
    assert result.rows[1].holding_type == "equity"
    assert result.rows[2].symbol is None
    assert result.rows[2].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == "issuer_public_holdings_csv"


@pytest.mark.asyncio
async def test_neos_adapter_fetches_ajax_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("neos")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag",
                    '06/12/2026,SPYI,A,00846U101,"Agilent Technologies Inc","45,190",$129.55,"$5,854,364.50",0.06%,"$10,017,366,830.00","189,590,000","18,959",',
                    '06/12/2026,QQQI,MSFT,594918104,"Microsoft Corp",10,$500.00,"$5,000.00",1.00%,"$500,000.00","10,000","1",',
                ]
            ),
            content_type="text/csv",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="SPYI")

    assert FakeAsyncClient.requested[0][0] == (
        "https://neosfunds.com/wp-admin/admin-ajax.php"
        "?action=download_holdings_csv&ticker=SPYI"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == "https://neosfunds.com/"
    assert len(result.rows) == 1
    assert result.rows[0].symbol == "A"
    assert result.rows[0].name == "Agilent Technologies Inc"
    assert result.rows[0].cusip == "00846U101"
    assert result.rows[0].weight == Decimal("0.0006")
    assert result.legal_metadata["route_resolution"] == "issuer_ajax_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-12"


@pytest.mark.asyncio
async def test_strive_adapter_fetches_public_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("strive")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "% Of Net Assets,Name,Ticker,CUSIP,Shares Held,Market Value",
                    "7.54%,NVIDIA Corp,NVDA,67066G104,403901.00000000,82747197.87",
                ]
            ),
            content_type="application/download",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="STXF")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.strivefunds.com/download-holdings?fund=STXF"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == (
        "https://www.strivefunds.com/"
    )
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].name == "NVIDIA Corp"
    assert result.rows[0].weight == Decimal("0.0754")
    assert result.legal_metadata["route_resolution"] == "issuer_public_holdings_csv"


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
