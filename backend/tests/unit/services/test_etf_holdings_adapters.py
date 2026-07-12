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


class MockDate(date):
    today_value = date(2026, 7, 6)

    @classmethod
    def today(cls) -> date:
        return cls.today_value


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
        url: str = "https://issuer.example/holdings.csv",
    ):
        self.text = text
        self.content = content if content is not None else text.encode()
        self.headers = {"content-type": content_type}
        self.status_code = status_code
        self.url = url

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


@pytest.mark.asyncio
async def test_eldridge_adapter_filters_combined_daily_holdings_and_preserves_cusips(monkeypatch):
    adapter = get_holdings_adapter("eldridge")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    (
                        "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,"
                        "MarketValue,Weightings,NetAssets"
                    ),
                    (
                        "07/10/2026,CLOX,00119CAN1,00119CAN1,"
                        "AGL CLO 20 Ltd 5.0452% 10/20/2037,2650000,100.1562,"
                        "2654139.30,0.86%,308539110"
                    ),
                    (
                        "07/10/2026,CLOZ,FXFXX,FXFXX,Cash & Other,1000,1,1000,"
                        "0.01%,100000000"
                    ),
                    (
                        "07/10/2026,CLOZ,00121DAA3,00121DAA3,"
                        "AGL CLO 33 Ltd 5.0221% 07/21/2037,2815000,100.0588,"
                        "2816655.22,0.91%,100000000"
                    ),
                ]
            )
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="CLOZ")

    assert FakeAsyncClient.requested[0][0] == (
        "https://clozfund.com/assets/data/"
        "FilepointPanagram.40P2.P2_Holdings.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].name == "Cash & Other"
    assert result.rows[0].symbol is None
    assert result.rows[0].holding_type == "cash"
    assert result.rows[1].symbol is None
    assert result.rows[1].cusip == "00121DAA3"
    assert result.rows[1].holding_type == "fixed_income"
    assert result.rows[1].weight == Decimal("0.0091")
    assert result.legal_metadata["route_resolution"] == "issuer_combined_daily_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-10"


@pytest.mark.asyncio
async def test_akre_adapter_parses_filepoint_daily_holdings_without_inventing_local_tickers(monkeypatch):
    adapter = get_holdings_adapter("akre")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    (
                        "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,"
                        "MarketValue,Weightings,NetAssets,MoneyMarketFlag"
                    ),
                    (
                        "07/10/2026,AKRE,ABNB,009066101,Airbnb Inc,1056122,146.89,"
                        "155133760.58,2.97%,5221106549.86,"
                    ),
                    (
                        "07/10/2026,AKRE,CSU CN,BR52TP7,Constellation Software Inc/Canada,"
                        "325225,2735.47,627724982.01,12.02%,5221106549.86,"
                    ),
                    (
                        "07/10/2026,AKRE,Cash&Other,Cash&Other,Cash & Other,-6150304.45,1,"
                        "-6150304.45,-0.12%,5221106549.86,Y"
                    ),
                    (
                        "07/10/2026,OTHER,MSFT,594918104,Microsoft Corp,10,1,10,1%,10,"
                    ),
                ]
            )
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="AKRE")

    assert FakeAsyncClient.requested[0][0] == (
        "https://akre.filepoint.live/assets/data/"
        "FilepointAkre.40B4.B4_ETF_Holdings.csv"
    )
    assert len(result.rows) == 3
    assert result.rows[0].symbol == "ABNB"
    assert result.rows[0].cusip == "009066101"
    assert result.rows[1].symbol is None
    assert result.rows[1].sedol == "BR52TP7"
    assert result.rows[2].symbol is None
    assert result.rows[2].holding_type == "cash"
    assert result.rows[2].weight == Decimal("-0.0012")
    assert result.legal_metadata["route_resolution"] == "issuer_filepoint_daily_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-10"


@pytest.mark.asyncio
async def test_rayliant_adapter_discovers_product_page_and_preserves_foreign_references(monkeypatch):
    adapter = get_holdings_adapter("rayliant")
    assert adapter is not None

    product_page_url = "https://funds.rayliant.com/cnqq/"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<?xml version="1.0"?><urlset><url><loc>'
                f"{product_page_url}"
                "</loc></url></urlset>"
            ),
            content_type="application/xml",
            url="https://funds.rayliant.com/page-sitemap.xml",
        ),
        FakeResponse(
            text="""
                <html><head><title>CNQQ Rayliant-ChinaAMC Transformative China Tech ETF</title></head>
                <body>
                  <p>(as of 07.09.2026) Holdings are subject to change.</p>
                  <a href="/cnqq/?download_csv=1">Download Full Holdings</a>
                </body></html>
            """,
            content_type="text/html",
            url=product_page_url,
        ),
        FakeResponse(
            text="\n".join(
                [
                    '"Ticker","Company Name","% of Net Assets","Security Identifier","Quantity"',
                    '"700 HK","Tencent Holdings Ltd.","7.70%","BMMV2K8","49,089"',
                    '"BABA","Alibaba Group Holding Ltd ADR","3.00%","BK6YZP5","2,000"',
                    '"CASH","Cash & Other","0.25%","","1"',
                ]
            ),
            url="https://funds.rayliant.com/cnqq/?download_csv=1",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="CNQQ")

    assert [request[0] for request in FakeAsyncClient.requested] == [
        "https://funds.rayliant.com/page-sitemap.xml",
        product_page_url,
        "https://funds.rayliant.com/cnqq/?download_csv=1",
    ]
    assert len(result.rows) == 3
    assert result.rows[0].symbol is None
    assert result.rows[0].sedol == "BMMV2K8"
    assert result.rows[0].extra_data["source_symbol"] == "700 HK"
    assert result.rows[1].symbol == "BABA"
    assert result.rows[2].holding_type == "cash"
    assert result.rows[2].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == "issuer_product_sitemap_full_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-09"


@pytest.mark.asyncio
async def test_astoria_adapter_discovers_page_and_normalizes_market_value_millions(monkeypatch):
    adapter = get_holdings_adapter("astoria")
    assert adapter is not None

    product_page_url = "https://astoriaadvisorsetfs.com/roe/"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<?xml version="1.0"?><urlset><url><loc>'
                f"{product_page_url}"
                "</loc></url></urlset>"
            ),
            content_type="application/xml",
            url="https://astoriaadvisorsetfs.com/wp-sitemap-posts-page-1.xml",
        ),
        FakeResponse(
            text="""
                <html><head><title>ROE ETF - Astoria Portfolio Advisors</title></head>
                <body><table>
                  <thead><tr>
                    <th>Ticker</th><th>Name</th><th>CUSIP</th><th>Shares</th>
                    <th>Price</th><th>Market Value ($mm)</th><th>% of Net Assets</th>
                    <th>EFFECTIVE_DATE</th>
                  </tr></thead>
                  <tbody>
                    <tr><td>AAPL</td><td>Apple Inc</td><td>037833100</td><td>9,404</td>
                    <td>294.30</td><td>2.77</td><td>1.07</td><td>07/10/2026</td></tr>
                    <tr><td>CASH</td><td>Cash & Other</td><td></td><td>1</td>
                    <td>1</td><td>0.10</td><td>0.04</td><td>07/10/2026</td></tr>
                  </tbody>
                </table></body></html>
            """,
            content_type="text/html",
            url=product_page_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="ROE")

    assert [request[0] for request in FakeAsyncClient.requested] == [
        "https://astoriaadvisorsetfs.com/wp-sitemap-posts-page-1.xml",
        product_page_url,
    ]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].cusip == "037833100"
    assert result.rows[0].market_value == Decimal("2770000")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].market_value == Decimal("100000")
    assert result.legal_metadata["route_resolution"] == "issuer_wordpress_sitemap_complete_holdings_table"
    assert result.legal_metadata["composition_date"] == "2026-07-10"


@pytest.mark.asyncio
async def test_natixis_adapter_parses_issuer_daily_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("groupe_bpce")
    assert adapter is not None

    holdings_url = "https://mkt.im.natixis.com/files/etfs/GQI_daily_full_holdings.csv"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "DAILY HOLDINGS",
                    "Natixis Gateway Quality Income ETF",
                    "Ticker: GQI",
                    "As Of Date: 07/09/2026",
                    (
                        "Ticker,CUSIP,ISIN,Security name,Quantity held,Percent of net assets,"
                        "Market value,Maturity date,Coupon rate"
                    ),
                    "------,-----,----,-------------,-------------,---------------------,------------,-------------,-----------",
                    "AAPL,037833100,US0378331005,APPLE INC,60866,7.315,19247046.52,,0.0",
                    ",, ,US DOLLAR,1000,0.004,1000.00,,0.0",
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="GQI")

    assert [request[0] for request in FakeAsyncClient.requested] == [holdings_url]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].cusip == "037833100"
    assert result.rows[0].isin == "US0378331005"
    assert result.rows[0].weight == Decimal("0.07315")
    assert result.rows[0].shares == Decimal("60866")
    assert result.rows[0].market_value == Decimal("19247046.52")
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_daily_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-09"


@pytest.mark.asyncio
async def test_gqg_adapter_parses_issuer_dated_filepoint_holdings_export(monkeypatch):
    adapter = get_holdings_adapter("gqg")
    assert adapter is not None

    holdings_url = (
        "https://gqg.filepoint.live/assets/data/"
        "SEI_GQG_Tradedate_Holdings_07092026.txt"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    (
                        "date|fund_id|fund_name|fund_cusip|fund_ticker|security_group|"
                        "security_type|security_number|security_cusip|security_sedol|security_isin|"
                        "security_ticker|security_description|quantity|market_value|notional_value|"
                        "percent_of_market_value|percent_of_net_assets"
                    ),
                    (
                        "07/09/2026|5415|GQG US Equity ETF|00775Y256|GQGU|Stock - Common||"
                        "00287Y109|00287Y109|B92SR70|US00287Y1091|ABBV|ABBVIE INC|45562.00|"
                        "11386399.42||1.92|1.87"
                    ),
                    (
                        "07/09/2026|5415|GQG US Equity ETF|00775Y256|GQGU|Cash|||||||Cash|"
                        "18942831.23|18942831.23||3.20|3.10"
                    ),
                    (
                        "07/09/2026|5416|Another GQG ETF|00775Y257|GQGJ|Stock - Common||"
                        "037833100|037833100|2046251|US0378331005|AAPL|APPLE INC|100|10000||1|1"
                    ),
                ]
            ),
            content_type="text/plain",
            url=holdings_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_for_date(symbol="GQGU", requested_date=date(2026, 7, 9))

    assert [request[0] for request in FakeAsyncClient.requested] == [holdings_url]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ABBV"
    assert result.rows[0].cusip == "00287Y109"
    assert result.rows[0].isin == "US00287Y1091"
    assert result.rows[0].sedol == "B92SR70"
    assert result.rows[0].weight == Decimal("0.0187")
    assert result.rows[0].shares == Decimal("45562.00")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_dated_daily_holdings_export"
    assert result.legal_metadata["composition_date"] == "2026-07-09"


@pytest.mark.asyncio
async def test_brown_advisory_adapter_filters_issuer_dated_filepoint_holdings_export(monkeypatch):
    adapter = get_holdings_adapter("brown_advisory")
    assert adapter is not None

    holdings_url = (
        "https://brownadvisory.filepoint.live/assets/data/"
        "SEI_Brown_Tradedate_Holdings_07092026.txt"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    (
                        "date|fund_ticker|security_group|security_type|security_cusip|"
                        "security_sedol|security_isin|security_ticker|security_description|"
                        "quantity|market_value|percent_of_net_assets"
                    ),
                    (
                        "07/09/2026|BAFE|Stock - Common|Common Stock|037833100|2046251|"
                        "US0378331005|AAPL|APPLE INC|1650|521763|4.51501"
                    ),
                    "07/09/2026|BAFE|Cash|Cash|||||Cash|1000|1000|0.01",
                    (
                        "07/09/2026|BASG|Stock - Common|Common Stock|67066G104|2379504|"
                        "US67066G1040|NVDA|NVIDIA CORP|20|4000|1"
                    ),
                ]
            ),
            content_type="text/plain",
            url=holdings_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_for_date(symbol="BAFE", requested_date=date(2026, 7, 9))

    assert [request[0] for request in FakeAsyncClient.requested] == [holdings_url]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].cusip == "037833100"
    assert result.rows[0].isin == "US0378331005"
    assert result.rows[0].weight == Decimal("0.0451501")
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == "issuer_dated_daily_holdings_export"
    assert result.legal_metadata["composition_date"] == "2026-07-09"


@pytest.mark.asyncio
async def test_first_pacific_adapter_filters_issuer_dated_multi_fund_holdings_export(monkeypatch):
    adapter = get_holdings_adapter("first_pacific")
    assert adapter is not None

    holdings_url = "https://fpag.fpa.com/assets/data/BBH_FPA_ETF_PVAL_WEB.20260709.csv"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    (
                        "ETF Ticker,Date,ISIN,CUSIP,SEDOL,Ticker,Description,Security Type,"
                        "Market Value,Shares,Market Value Weight"
                    ),
                    (
                        "FPAG,7/9/2026,US0378331005,037833100,2046251,AAPL,APPLE INC,COMMON STOCK,"
                        "19247046.52,60866,7.315%"
                    ),
                    "FPAG,7/9/2026,,,,,US DOLLARS,CASH,1000000,1000000,0.38%",
                    (
                        "FPAS,7/9/2026,US91282CQY47,91282CQY4,,,US TREASURY NOTE,GOVERNMENT BOND,"
                        "6715000,6715000,68.15%"
                    ),
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_for_date(symbol="FPAG", requested_date=date(2026, 7, 9))

    assert [request[0] for request in FakeAsyncClient.requested] == [holdings_url]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].cusip == "037833100"
    assert result.rows[0].isin == "US0378331005"
    assert result.rows[0].sedol == "2046251"
    assert result.rows[0].weight == Decimal("0.07315")
    assert result.rows[0].shares == Decimal("60866")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_dated_multi_fund_daily_holdings_export"
    assert result.legal_metadata["composition_date"] == "2026-07-09"


@pytest.mark.asyncio
async def test_gabelli_adapter_parses_per_fund_daily_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("gamco")
    assert adapter is not None

    holdings_url = "https://gabelli.com/wp-content/uploads/Holdings_GCAD.csv"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    (
                        '"Account Description","Position Date","Stock Ticker",'
                        '"Security Description(Long)","Shares/Par","Price","Security CUSIP",'
                        '"% of Net Assets","Sector Description","Clean/Dirty"'
                    ),
                    (
                        '"GABELLI CMRCL AERO & DEF","07/09/2026","AIN","ALBANY INTL CORP-CL A",'
                        '"41121","71.31","012348108","6.6632%","INDUSTRIAL",""'
                    ),
                    (
                        '"GABELLI CMRCL AERO & DEF","07/09/2026","","EURO",'
                        '"57.5","0.87504","","0.0001%","UNDEFINED",""'
                    ),
                    (
                        '"GABELLI CMRCL AERO & DEF","07/09/2026","","Net Current Assets",'
                        '"76513.24","1","","0.1739%","",""'
                    ),
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="GCAD")

    assert [request[0] for request in FakeAsyncClient.requested] == [holdings_url]
    assert len(result.rows) == 3
    assert result.rows[0].symbol == "AIN"
    assert result.rows[0].cusip == "012348108"
    assert result.rows[0].weight == Decimal("0.066632")
    assert result.rows[0].market_value == Decimal("2932338.51")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.rows[2].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == "issuer_per_fund_daily_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-09"


@pytest.mark.asyncio
async def test_agf_adapter_resolves_product_payload_and_parses_per_fund_holdings(monkeypatch):
    adapter = get_holdings_adapter("agf")
    assert adapter is not None

    payload_url = (
        "https://www.agf.com/fileDispatcherWeb/process/deliverFileResult.action?"
        "format=JSON&requestId=IQ_FUND_CARD_BTAL"
    )
    holdings_url = "https://www.agf.com/t2scr/sharedDistT2scrWeb/doc/reports/QSBTALUS.csv"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=json.dumps(
                {
                    "iq_fund": {
                        "iq_code": "BTAL",
                        "iq_fund_holdings_url": "/t2scr/sharedDistT2scrWeb/doc/reports/QSBTALUS.csv",
                    }
                }
            ),
            content_type="application/json",
            url=payload_url,
        ),
        FakeResponse(
            text="\n".join(
                [
                    "BTAL, as of 2026-07-09",
                    "",
                    '"Asset Type","Ticker","SEDOL","Issue Name","Currency","Quantity","Weight"',
                    '"EQUITY","ABBV","B92SR70","AbbVie Inc.","USD",5511,0.004739',
                    '"CASH","","","Cash and cash equivalents","USD",1000,0.000100',
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BTAL")

    assert [request[0] for request in FakeAsyncClient.requested] == [payload_url, holdings_url]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ABBV"
    assert result.rows[0].sedol == "B92SR70"
    assert result.rows[0].weight == Decimal("0.004739")
    assert result.rows[0].shares == Decimal("5511")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_product_payload_to_per_fund_holdings_csv"
    )
    assert result.legal_metadata["composition_date"] == "2026-07-09"


@pytest.mark.asyncio
async def test_acuitas_adapter_filters_daily_holdings_by_issuer_account(monkeypatch):
    adapter = get_holdings_adapter("acuitas")
    assert adapter is not None

    holdings_url = (
        "https://phpstack-1541365-5956782.cloudwaysapps.com/"
        "Acuitas_WEB.40B6.B6_ETF_Holdings.csv"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    (
                        "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,"
                        "Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag"
                    ),
                    (
                        "07/13/2026,AIMS,ACCO,00081T108,ACCO Brands Corp,51627,3.88,200312.76,"
                        "0.23%,88331710,3100000,124,"
                    ),
                    (
                        "07/13/2026,AIMS,,,Cash & Other,1000,1,1000,0.01%,88331710,3100000,124,Y"
                    ),
                    "07/13/2026,OTHER,AAPL,037833100,Apple Inc,1,1,1,1%,1,1,1,",
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="AIMS")

    assert [request[0] for request in FakeAsyncClient.requested] == [holdings_url]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ACCO"
    assert result.rows[0].cusip == "00081T108"
    assert result.rows[0].weight == Decimal("0.0023")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == "issuer_daily_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-13"


@pytest.mark.asyncio
async def test_alger_adapter_parses_per_fund_daily_holdings_and_cash_rows(monkeypatch):
    adapter = get_holdings_adapter("alger")
    assert adapter is not None

    holdings_url = (
        "https://www.alger.com/AlgerETFDailyHoldings/"
        "Daily_Holdings_Alger_Concentrated_Equity_ETF.csv"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Product Short Name,Effective Date,Ticker,CUSIP,Security Description,Quantity,Percentage Weight",
                    "CNEQ,07/09/2026,USD,,US Dollar,2251434.8800,0.29 %",
                    "CNEQ,07/09/2026,TSM,874039100,Taiwan Semiconductor ADR,100054.0000,5.69 %",
                    "OTHER,07/09/2026,AAPL,037833100,Apple Inc,1,1.00 %",
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="CNEQ")

    assert [request[0] for request in FakeAsyncClient.requested] == [holdings_url]
    assert len(result.rows) == 2
    assert result.rows[0].symbol is None
    assert result.rows[0].row_type == "cash"
    assert result.rows[1].symbol == "TSM"
    assert result.rows[1].cusip == "874039100"
    assert result.rows[1].weight == Decimal("0.0569")
    assert result.legal_metadata["route_resolution"] == "issuer_per_fund_daily_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-09"


@pytest.mark.asyncio
async def test_impax_adapter_parses_issuer_server_rendered_holdings_dataset(monkeypatch):
    adapter = get_holdings_adapter("impax")
    assert adapter is not None

    holdings_url = "https://etf.impaxam.com/"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="".join(
                [
                    'dg.componentId="bldximpax-BLDX-HoldingsComponent-1";',
                    'dg.date="07\\u002F09\\u002F2026";',
                    'dg.finData=[',
                    '{figi:"BBG000BW3299",ticker:"UNP",quantity:23023,description:',
                    '"UNION PACIFIC CORP",market_value:"6,562,475.92",percent_of_nav:"5.55%"},',
                    '{figi:"BBG0013HGBT3",ticker:"Cash-USD",quantity:2741899,description:',
                    '"CASH & OTHER",market_value:"2,741,899.89",percent_of_nav:"2.32%"}',
                    '];dg.btnLink="";',
                ]
            ),
            content_type="text/html",
            url=holdings_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BLDX")

    assert [request[0] for request in FakeAsyncClient.requested] == [holdings_url]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "UNP"
    assert result.rows[0].shares == Decimal("23023")
    assert result.rows[0].market_value == Decimal("6562475.92")
    assert result.rows[0].weight == Decimal("0.0555")
    assert result.rows[0].extra_data["figi"] == "BBG000BW3299"
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_server_rendered_product_page_holdings_dataset"
    )
    assert result.legal_metadata["composition_date"] == "2026-07-09"


@pytest.mark.asyncio
async def test_bbh_adapter_parses_complete_daily_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("brown_brothers_harriman")
    assert adapter is not None

    holdings_url = (
        "https://www.bbhfunds.com/us/en/our-funds/bbh-etfs/"
        "bbh-select-large-cap-etf.html"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="".join(
                [
                    '<span class="cmp-fundteaser__item-contentTicker">BBHL</span>',
                    '<h2>Daily Holdings</h2><p>as of 07/10/2026</p>',
                    "<table><thead><tr><th>Name</th><th>Ticker</th><th>Shares</th>",
                    "<th>CUSIP</th><th>Weight</th></tr></thead><tbody>",
                    "<tr><td>ABBOTT LABORATORIES</td><td>ABT</td><td>38,574</td>",
                    "<td>002824100</td><td>0.67%</td></tr>",
                    "<tr><td>Cash & Other</td><td></td><td>100</td><td></td><td>0.01%</td></tr>",
                    "</tbody></table>",
                ]
            ),
            content_type="text/html",
            url=holdings_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BBHL")

    assert [request[0] for request in FakeAsyncClient.requested] == [holdings_url]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ABT"
    assert result.rows[0].cusip == "002824100"
    assert result.rows[0].shares == Decimal("38574")
    assert result.rows[0].weight == Decimal("0.0067")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_product_page_complete_daily_holdings_table"
    )
    assert result.legal_metadata["composition_date"] == "2026-07-10"


@pytest.mark.asyncio
async def test_hedgeye_adapter_selects_the_latest_requested_fund_snapshot(monkeypatch):
    adapter = get_holdings_adapter("hedgeye")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<script>'
                '"date":"2026-07-10","holdings":{"data":['
                '{"SecurityName":"Apple Inc","StockTicker":"AAPL","CUSIP":"037833100",'
                '"Shares":10,"MarketValue":2000,"Weightings":"2.00%","MoneyMarketFlag":"",'
                '"Account":"HECA"}]},"account":"HECA","title":"2026-07-10-HECA"'
                '"date":"2026-07-11","holdings":{"data":['
                '{"SecurityName":"Microsoft Corp","StockTicker":"MSFT","CUSIP":"594918104",'
                '"Shares":12,"MarketValue":3000,"Weightings":"3.00%","MoneyMarketFlag":"",'
                '"Account":"HECA"},'
                '{"SecurityName":"Cash & Other","StockTicker":"Cash&Other","CUSIP":"Cash&Other",'
                '"Shares":50,"MarketValue":50,"Weightings":"0.05%","MoneyMarketFlag":"Y",'
                '"Account":"HECA"}]},"account":"HECA","title":"2026-07-11-HECA"'
                '"date":"2026-07-12","holdings":{"data":['
                '{"SecurityName":"Other Fund","StockTicker":"OTHER","CUSIP":"000000000",'
                '"Shares":1,"MarketValue":1,"Weightings":"1.00%","MoneyMarketFlag":"",'
                '"Account":"HGRO"}]},"account":"HGRO","title":"2026-07-12-HGRO"'
                "</script>"
            )
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="HECA")

    assert FakeAsyncClient.requested[0][0] == "https://www.hedgeyeam.com/heca"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_product_page_complete_daily_holdings_payload"
    )
    assert result.legal_metadata["composition_date"] == "2026-07-11"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "MSFT"
    assert result.rows[0].cusip == "594918104"
    assert result.rows[0].weight == Decimal("0.03")
    assert result.rows[1].symbol is None
    assert result.rows[1].holding_type == "cash"


@pytest.mark.asyncio
async def test_founder_adapter_parses_complete_holdings_pdf_text():
    adapter = get_holdings_adapter("founder")
    assert adapter is not None

    rows, composition_date = adapter._parse_holdings_text(
        "\n".join(
            [
                "Full Holdings",
                "As of 2026-07-10",
                "TICKER",
                "NAME",
                "FOUNDER(S)",
                "WEIGHT",
                "META",
                "META",
                "Mark Zuckerberg",
                "6.84%",
                "Cash&Other",
                "Cash & Other",
                "-0.23%",
            ]
        )
    )

    assert composition_date == date(2026, 7, 10)
    assert len(rows) == 2
    assert rows[0].symbol == "META"
    assert rows[0].weight == Decimal("0.0684")
    assert rows[0].extra_data["founder_names"] == "Mark Zuckerberg"
    assert rows[1].symbol is None
    assert rows[1].holding_type == "cash"


@pytest.mark.asyncio
async def test_polen_adapter_filters_issuer_multi_fund_export(monkeypatch):
    adapter = get_holdings_adapter("polen")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Output File Name:PolenHoldings_.csv Date and Time of Execution:2026-07-10 18:08:41",
                    (
                        "Basket Name,Security Description,Ticker,Fund Accounting Asset Group Code,"
                        "CUSIP,ISIN,Basket Quantity,Market Value or Unrealized (Base),"
                        "Constituent Weight (Base)"
                    ),
                    (
                        "Polen Focus Growth ETF,Microsoft Corp,MSFT,EQ(Equities),594918104,"
                        "US5949181045,100,50000,0.25"
                    ),
                    (
                        "Polen Focus Growth ETF,Cash & Other,Cash&Other,Cash,,"
                        ",10,10,0.00005"
                    ),
                    (
                        "POLEN HIGH INCOME ETF,Other Issuer,OTHER,EQ(Equities),000000000,"
                        "US0000000000,1,1,1"
                    ),
                ]
            )
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="PCLG")

    assert FakeAsyncClient.requested[0][0] == (
        "https://polen.filepoint.live/assets/data/PolenHoldings_.csv"
    )
    assert result.legal_metadata["route_resolution"] == "issuer_multi_fund_daily_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-10"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "MSFT"
    assert result.rows[0].weight == Decimal("0.25")
    assert result.rows[1].symbol is None
    assert result.rows[1].holding_type == "cash"


@pytest.mark.asyncio
async def test_wbi_adapter_parses_complete_daily_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("wbi")
    assert adapter is not None

    holdings_url = "https://wbietfs.com/bullbear-quality-3000-etf/"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="".join(
                [
                    "<p>WBIL</p>",
                    "<table><thead><tr><th>Date</th><th>Account</th><th>StockTicker</th>",
                    "<th>CUSIP</th><th>SecurityName</th><th>Shares</th><th>MarketValue</th>",
                    "<th>Weightings</th></tr></thead><tbody>",
                    "<tr><td>07/13/2026</td><td>WBIL</td><td>ALAB</td><td>04626A103</td>",
                    "<td>Astera Labs Inc</td><td>2,371</td><td>979151.87</td><td>3.26%</td></tr>",
                    "<tr><td>07/13/2026</td><td>WBIL</td><td>USD</td><td></td>",
                    "<td>Cash & Other</td><td>100</td><td>100.00</td><td>0.01%</td></tr>",
                    "<tr><td>07/13/2026</td><td>OTHER</td><td>AAPL</td><td>037833100</td>",
                    "<td>Apple Inc</td><td>1</td><td>1.00</td><td>1.00%</td></tr>",
                    "</tbody></table>",
                ]
            ),
            content_type="text/html",
            url=holdings_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="WBIL")

    assert [request[0] for request in FakeAsyncClient.requested] == [holdings_url]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ALAB"
    assert result.rows[0].cusip == "04626A103"
    assert result.rows[0].shares == Decimal("2371")
    assert result.rows[0].market_value == Decimal("979151.87")
    assert result.rows[0].weight == Decimal("0.0326")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_product_page_complete_daily_holdings_table"
    )
    assert result.legal_metadata["composition_date"] == "2026-07-13"


@pytest.mark.asyncio
async def test_mairs_power_adapter_parses_complete_municipal_bond_portfolio(monkeypatch):
    adapter = get_holdings_adapter("mairs_power")
    assert adapter is not None

    holdings_url = "https://www.mairsandpower.com/funds/mn-muni-bond-etf"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="".join(
                [
                    "<h1>Mairs & Power Minnesota Municipal Bond ETF MINN</h1>",
                    "<table><thead><tr><th>FULL PORTFOLIO AS OF 07/13/2026</th><th>CUSIP</th>",
                    "<th>SHARES</th><th>$ MARKET VALUE</th><th>% PORTFOLIO</th></tr></thead><tbody>",
                    "<tr><td>Stillwater Independent School District No 834 5% 02/01/2035</td>",
                    "<td>860758TP6</td><td>1,075,000</td><td>1,206,818</td><td>2.56%</td></tr>",
                    "<tr><td>State of Minnesota 5% 08/01/2037</td>",
                    "<td>60412AW33</td><td>1,000,000</td><td>1,143,166</td><td>2.43%</td></tr>",
                    "</tbody></table>",
                ]
            ),
            content_type="text/html",
            url=holdings_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="MINN")

    assert [request[0] for request in FakeAsyncClient.requested] == [holdings_url]
    assert len(result.rows) == 2
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "Stillwater Independent School District No 834 5% 02/01/2035"
    assert result.rows[0].cusip == "860758TP6"
    assert result.rows[0].shares == Decimal("1075000")
    assert result.rows[0].market_value == Decimal("1206818")
    assert result.rows[0].weight == Decimal("0.0256")
    assert result.rows[0].holding_type == "fixed_income"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_product_page_complete_portfolio_table"
    )
    assert result.legal_metadata["composition_date"] == "2026-07-13"


@pytest.mark.asyncio
async def test_tiaa_adapter_resolves_nuveen_symbol_and_parses_holdings(monkeypatch):
    adapter = get_holdings_adapter("tiaa")
    assert adapter is not None

    product_page_url = (
        "https://www.nuveen.com/en-us/exchange-traded-funds/"
        "nulg-nuveen-esg-large-cap-growth-etf"
    )
    holdings_url = "https://api.nuveen.com/ETF/v2/productdetail/bycusip/67092P201?tooltip=1"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=json.dumps(
                {
                    "productoverview": [
                        {
                            "fundcode": "NULG",
                            "legalname": "nuveen-esg-large-cap-growth",
                            "productpath": "exchange-traded-funds",
                        }
                    ]
                }
            ),
            content_type="application/json",
            url="https://api.nuveen.com/etf/products/findanotherfund/",
        ),
        FakeResponse(
            text='<nuv-api-table-container-tabs apiurl="https://api.nuveen.com/ETF/v2/productdetail/bycusip//67092P201?tooltip=1">',
            content_type="text/html",
            url=product_page_url,
        ),
        FakeResponse(
            text=json.dumps(
                {
                    "symbol": "NULG",
                    "holdings": [
                        {
                            "asofdate": "2026-07-09T00:00:00",
                            "name": "NVIDIA CORP",
                            "ticker": "NVDA US",
                            "cusip": "67066G104",
                            "portprcnt": 14.59,
                            "mkt_value": 402459493.8,
                            "sector": "SEMICONDUCTORS",
                        },
                        {
                            "asofdate": "2026-07-09T00:00:00",
                            "name": "U.S. DOLLARS",
                            "cusip": "USD",
                            "portprcnt": 0.18,
                            "mkt_value": 5017477.04,
                            "sector": "FOREIGN CURRENCY",
                        },
                    ],
                }
            ),
            content_type="application/json",
            url=holdings_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="NULG")

    assert [request[0] for request in FakeAsyncClient.requested] == [
        "https://api.nuveen.com/etf/products/findanotherfund/",
        product_page_url,
        holdings_url,
    ]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].cusip == "67066G104"
    assert result.rows[0].weight == Decimal("0.1459")
    assert result.rows[0].market_value == Decimal("402459493.8")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_catalog_product_page_product_api"
    assert result.legal_metadata["composition_date"] == "2026-07-09"


@pytest.mark.asyncio
async def test_pgim_adapter_discovers_product_page_document_and_parses_daily_holdings(monkeypatch):
    adapter = get_holdings_adapter("prudential")
    assert adapter is not None

    directory_url = "https://www.pgim.com/us/en/individual/investment-capabilities/products/etf.html"
    product_page_url = (
        "https://www.pgim.com/us/en/intermediary/investment-capabilities/products/etf/"
        "pgim-jennison-better-future-etf"
    )
    document_id = "7F37BD52813A42DBB4850377D797FD0B"
    document_url = f"https://www.pgim.com/api/pidms/RepositoryEntries/{document_id}/File"
    extracted_pdf_text = "\n".join(
        [
            (
                "ETF Ticker Date ISIN CUSIP SEDOL Ticker Description Security Type Market Value "
                "Maturity Date Shares Security Price Asset Currency Market Value Weight Trading Currency"
            ),
            (
                "PJBF 07/10/2026 US67066G1040 67066G104 2379504 NVDA NVIDIA CORP Common stock "
                "538380.900000000 2655.000000000 202.780000000 USD 4.658810000 USD"
            ),
            (
                "PJBF 07/10/2026 GBP British Pound Sterling Currency 4.550000000 "
                "3.390000000 0.745851000 USD 0.000039000 GBP"
            ),
        ]
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<table><tr><td>PGIM Jennison Better Future ETF</td><td><a href="'
                f'{product_page_url}">PJBF</a></td></tr></table>'
            ),
            content_type="text/html",
            url=directory_url,
        ),
        FakeResponse(
            text=(
                '<a class="documents-download-link" '
                f'href="/us/en/intermediary/pidoc?appId=aemshell&pdfId={document_id}" '
                'data-document-label="DAILY HOLDINGS">DAILY HOLDINGS</a>'
            ),
            content_type="text/html",
            url=product_page_url,
        ),
        FakeResponse(
            content=b"%PDF-placeholder",
            content_type="application/pdf",
            url=document_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(type(adapter), "_extract_pdf_text", staticmethod(lambda _raw: extracted_pdf_text))

    result = await adapter.fetch_latest(symbol="PJBF")

    assert [request[0] for request in FakeAsyncClient.requested] == [
        directory_url,
        product_page_url,
        document_url,
    ]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].isin == "US67066G1040"
    assert result.rows[0].cusip == "67066G104"
    assert result.rows[0].sedol == "2379504"
    assert result.rows[0].weight == Decimal("0.0465881")
    assert result.rows[0].market_value == Decimal("538380.900000000")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_catalog_product_page_daily_holdings_pdf"
    )
    assert result.legal_metadata["composition_date"] == "2026-07-10"


@pytest.mark.asyncio
async def test_tortoise_adapter_discovers_product_page_and_parses_daily_holdings(monkeypatch):
    adapter = get_holdings_adapter("tortoise")
    assert adapter is not None

    product_page_url = "https://tortoisecapital.com/etf/tortoise-electrification-infrastructure-etf/"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<?xml version="1.0"?><urlset><url><loc>'
                f"{product_page_url}"
                "</loc></url></urlset>"
            ),
            content_type="application/xml",
            url="https://tortoisecapital.com/etfs-sitemap.xml",
        ),
        FakeResponse(
            text="""
                <html><body>
                  <table><tr><th>Ticker</th><td>TPZ</td></tr></table>
                  <section id="holdings"><h2>Daily Fund Holdings</h2>
                    <p>As of 07/09/2026</p>
                    <table>
                      <thead><tr>
                        <th>Security Name</th><th>Stock Ticker</th><th>CUSIP</th>
                        <th>Shares</th><th>Market Value</th><th>Weight</th>
                      </tr></thead>
                      <tbody>
                        <tr><td>Energy Transfer LP</td><td>ET</td><td>29273V100</td>
                        <td>476,713</td><td>$9,434,150.27</td><td>7.33%</td></tr>
                        <tr><td>US Dollar</td><td>USD</td><td></td>
                        <td>10</td><td>$10</td><td>0.01%</td></tr>
                      </tbody>
                    </table>
                  </section>
                </body></html>
            """,
            content_type="text/html",
            url=product_page_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="TPZ")

    assert [request[0] for request in FakeAsyncClient.requested] == [
        "https://tortoisecapital.com/etfs-sitemap.xml",
        product_page_url,
    ]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ET"
    assert result.rows[0].cusip == "29273V100"
    assert result.rows[0].weight == Decimal("0.0733")
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_etf_sitemap_product_page_daily_holdings_table"
    )
    assert result.legal_metadata["composition_date"] == "2026-07-09"


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
async def test_coinshares_adapter_fetches_widget_holdings(monkeypatch):
    adapter = get_holdings_adapter("coinshares")
    assert adapter is not None

    payload = [
        {
            "code": "WGMI",
            "sections": [
                {
                    "key": "VALKYRIE_HOLDINGS_WGMI_0",
                    "source": "Coinshares TBA",
                    "updated": "2026-07-07T10:01:06Z",
                    "meta": [
                        {"key": "cusip", "value": "433921103"},
                        {"key": "date", "value": "2026/07/07"},
                        {"key": "marketvalue", "value": "11508021.20"},
                        {"key": "netassets", "value": "248831880.0"},
                        {"key": "price", "value": "3.38"},
                        {"key": "securityname", "value": "Hive Digital Technologies Ltd"},
                        {"key": "shares", "value": "3404740.0"},
                        {"key": "stockticker", "value": "HIVE"},
                        {"key": "weightpercentage", "value": "4.62%"},
                    ],
                },
                {
                    "key": "VALKYRIE_HOLDINGS_WGMI_1",
                    "meta": [
                        {"key": "cusip", "value": "Cash&Other"},
                        {"key": "date", "value": "2026/07/07"},
                        {"key": "marketvalue", "value": "1234302.01"},
                        {"key": "price", "value": "1.0"},
                        {"key": "securityname", "value": "Cash & Other"},
                        {"key": "shares", "value": "1234302.01"},
                        {"key": "stockticker", "value": "Cash&Other"},
                        {"key": "weightpercentage", "value": "0.50%"},
                    ],
                },
            ],
        }
    ]
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=json.dumps(payload),
            content_type="application/json",
            url=(
                "https://www-api.coinshares.com/api/v2/Widgets"
                "?ApiKey=094DA478-140C-4E3E-B394-7A19BBE8326B"
                "&names=VALKYRIE_HOLDINGS_WGMI"
            ),
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="WGMI")

    requested_url, request_kwargs = FakeAsyncClient.requested[0]
    assert requested_url.startswith("https://www-api.coinshares.com/api/v2/Widgets")
    assert "names=VALKYRIE_HOLDINGS_WGMI" in requested_url
    assert request_kwargs["headers"]["Referer"] == "https://coinshares.com/us/etf/wgmi/"
    assert len(result.rows) == 2
    equity_row = result.rows[0]
    assert equity_row.symbol == "HIVE"
    assert equity_row.name == "Hive Digital Technologies Ltd"
    assert equity_row.cusip == "433921103"
    assert equity_row.weight == Decimal("0.0462")
    assert equity_row.shares == Decimal("3404740.0")
    assert equity_row.market_value == Decimal("11508021.20")
    assert equity_row.holding_type == "equity"
    cash_row = result.rows[1]
    assert cash_row.symbol is None
    assert cash_row.row_type == "cash"
    assert cash_row.holding_type == "cash"
    assert result.legal_metadata["source_provider"] == "coinshares"
    assert result.legal_metadata["route_resolution"] == "issuer_public_widgets_api"
    assert result.legal_metadata["composition_date"] == "2026-07-07"


@pytest.mark.asyncio
async def test_castleark_adapter_fetches_recent_daily_holdings_text(monkeypatch):
    adapter = get_holdings_adapter("castleark")
    assert adapter is not None

    holdings_text = "\n".join(
        [
            (
                "date|fund_id|fund_name|fund_cusip|fund_ticker|security_group|"
                "security_type|security_number|security_cusip|security_sedol|"
                "security_isin|security_ticker|security_description|quantity|"
                "market_value|notional_value|percent_of_market_value|percent_of_net_assets"
            ),
            (
                "07/06/2026|4870|CastleArk Large Growth ETF|00791R608|CARK|Cash|||||||"
                "Cash|15699388.18|15699388.18||5.08|4.84"
            ),
            (
                "07/06/2026|4870|CastleArk Large Growth ETF|00791R608|CARK|Stock - Common||"
                "007903107|007903107|2007849|US0079031078|AMD|ADVANCED MICRO DEVICES|"
                "14248.00|7865608.40||2.55|2.42"
            ),
        ]
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(text="not found", content_type="text/html", status_code=404),
        FakeResponse(
            text=holdings_text,
            content_type="text/plain",
            url="http://castleark-etfs.com/assets/data/SEI_CRK_Tradedate_Holdings_07062026.txt",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)
    MockDate.today_value = date(2026, 7, 7)
    monkeypatch.setattr("app.services.etf_holdings_adapters.date", MockDate)

    result = await adapter.fetch_latest(symbol="CARK")

    requested_urls = [request[0] for request in FakeAsyncClient.requested]
    assert requested_urls == [
        "http://castleark-etfs.com/assets/data/SEI_CRK_Tradedate_Holdings_07072026.txt",
        "http://castleark-etfs.com/assets/data/SEI_CRK_Tradedate_Holdings_07062026.txt",
    ]
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == "http://castleark-etfs.com/"
    assert len(result.rows) == 2
    cash_row = result.rows[0]
    assert cash_row.symbol is None
    assert cash_row.row_type == "cash"
    assert cash_row.weight == Decimal("0.0484")
    equity_row = result.rows[1]
    assert equity_row.symbol == "AMD"
    assert equity_row.name == "ADVANCED MICRO DEVICES"
    assert equity_row.cusip == "007903107"
    assert equity_row.isin == "US0079031078"
    assert equity_row.sedol == "2007849"
    assert equity_row.shares == Decimal("14248.00")
    assert equity_row.market_value == Decimal("7865608.40")
    assert equity_row.weight == Decimal("0.0242")
    assert result.source_url.endswith("SEI_CRK_Tradedate_Holdings_07062026.txt")
    assert result.legal_metadata["source_provider"] == "castleark"
    assert result.legal_metadata["route_resolution"] == "issuer_public_daily_holdings_text"
    assert result.legal_metadata["composition_date"] == "2026-07-06"


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
async def test_goldman_sachs_adapter_fetches_public_holdings_workbook(monkeypatch):
    adapter = get_holdings_adapter("goldman_sachs")
    assert adapter is not None

    workbook = _xlsx_workbook(
        [
            ["Goldman Sachs Hedge Industry VIP ETF"],
            [
                "Date",
                "Ticker",
                "Cusip",
                "ISIN",
                "Sedol",
                "Description",
                "Market Value",
                "Number of Shares",
                "% Weighting",
            ],
            [
                "45847.0",
                "AAPL",
                "03783310",
                "US0378331005",
                "2046251",
                "Apple Inc",
                "6746767.56",
                "31954.00",
                "1.93",
            ],
            [
                "45847.0",
                "CRH",
                "G2550810",
                "IE0001827041",
                "B01ZKD6",
                "CRH PLC",
                "6662700.55",
                "69065.00",
                "1.90",
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
            url=(
                "https://www.gsam.com/content/dam/gsam/xls/us/en/etf/"
                "Goldman%20Sachs%20Hedge%20Industry%20VIP%20ETF_9532.xlsx"
            ),
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="GVIP")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.gsam.com/content/dam/gsam/xls/us/en/etf/"
        "Goldman%20Sachs%20Hedge%20Industry%20VIP%20ETF_9532.xlsx"
    )
    assert len(result.rows) == 2
    row = result.rows[0]
    assert row.symbol == "AAPL"
    assert row.name == "Apple Inc"
    assert row.cusip == "03783310"
    assert row.isin == "US0378331005"
    assert row.sedol == "2046251"
    assert row.weight == Decimal("0.0193")
    assert row.shares == Decimal("31954.00")
    assert row.market_value == Decimal("6746767.56")
    assert row.currency == "USD"
    assert result.legal_metadata["source_provider"] == "goldman_sachs"
    assert result.legal_metadata["source_format"] == "xlsx"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_xlsx"
    assert result.legal_metadata["composition_date"] == "2025-07-09"


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
async def test_beyond_investing_adapter_filters_public_aggregate_csv(monkeypatch):
    adapter = get_holdings_adapter("beyond_investing")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag",
                    "06/26/2026,VEGN,AAPL,037833100,Apple Inc,25107.00000000,275.150000,6908191.05,3.71%,186413152.50,2325000,93.000000000000,",
                    "06/26/2026,VEGN,USDOLLAR,,Cash,500,1,500,0.05%,186413152.50,2325000,93.000000000000,1",
                    "06/26/2026,OTHER,MSFT,594918104,Microsoft Corp,2,400,800,1.10%,100000,1,1,",
                ]
            ),
            content_type="text/csv",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="VEGN", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.veganetf-sftp.com/csvs/BeyondAdvisorsWEB.40XZ.XZ_Holdings.csv"
    )
    assert [row.symbol for row in result.rows] == ["AAPL", None]
    assert result.rows[0].cusip == "037833100"
    assert result.rows[0].weight == Decimal("0.0371")
    assert result.rows[0].shares == Decimal("25107.00000000")
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["source_provider"] == "beyond_investing"
    assert result.legal_metadata["route_resolution"] == "issuer_aggregate_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-26"


@pytest.mark.asyncio
async def test_swan_global_adapter_discovers_product_page_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("swan_global")
    assert adapter is not None

    holdings_url = (
        "https://etfs.swanglobalinvestments.com/wp-content/uploads/documents/"
        "swanweb1.40jr.jr_holdings.csv?1767228128"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=f'<a href="{holdings_url}">Download full holdings</a>',
            content_type="text/html",
            url="https://etfs.swanglobalinvestments.com/hedged-equity-etf/",
        ),
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag",
                    "06/29/2026,HEGD,SPY,78462F103,State Street SPDR S&P 500 ETF Trust,871868,728.99,635583053.32,91.48%,694781568,26520000,2652,",
                    "06/29/2026,HEGD,SPX   271217C07500000,SPX   271217C07500000,SPX US 12/17/27 C7500,219,787.65,17249535,2.48%,694781568,26520000,2652,",
                    "06/29/2026,HEGD,Cash&Other,Cash&Other,Cash & Other,1446158.19,1,1446158.19,0.21%,694781568,26520000,2652,Y",
                    "06/29/2026,OTHER,AAPL,037833100,Apple Inc,1,200,200,1%,20000,1,1,",
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="HEGD", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://etfs.swanglobalinvestments.com/hedged-equity-etf/"
    )
    assert FakeAsyncClient.requested[1][0] == holdings_url
    assert [row.holding_type for row in result.rows] == ["equity", "option", "cash"]
    assert result.rows[0].symbol == "SPY"
    assert result.rows[0].cusip == "78462F103"
    assert result.rows[0].weight == Decimal("0.9148")
    assert result.rows[1].symbol is None
    assert result.rows[1].name == "SPX US 12/17/27 C7500"
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.legal_metadata["source_provider"] == "swan_global"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_linked_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-29"


@pytest.mark.asyncio
async def test_running_oak_adapter_parses_filepoint_holdings_json(monkeypatch):
    adapter = get_holdings_adapter("running_oak")
    assert adapter is not None

    payload = [
        {
            "asOfDate": "2026-06-26T00:00:00",
            "portfolioNumber": "1363",
            "portfolioName": "Running Oak Efficient Growth ETF",
            "securityIdentifier": "78467J100",
            "securityTicker": "SSNC US",
            "securityDescriptionLong": "SS&C Technologies Holdings, Inc.",
            "shares": 82566.0,
            "marketValueBase": 5256151.56,
            "tradingCurrency": "USD",
            "country": "US",
            "segment": "COMMON STOCKS",
            "sector": "SOFTWARE",
            "marketValuePercent": 0.015860798135,
        },
        {
            "asOfDate": "2026-06-26T00:00:00",
            "portfolioNumber": "1363",
            "securityIdentifier": "USD",
            "securityTicker": "RECPAY",
            "securityDescriptionLong": "Receivable / payable",
            "shares": 1,
            "marketValueBase": 1000,
            "tradingCurrency": "USD",
            "segment": "CASH AND EQUIVALENTS",
            "marketValuePercent": 0.0001,
        },
    ]
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=json.dumps(payload),
            content_type="application/json",
            url="https://filepoint.live/runningoak_holdings_1363_data.json",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="ROEQ", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://filepoint.live/runningoak_holdings_1363_data.json"
    )
    assert result.rows[0].symbol == "SSNC"
    assert result.rows[0].exchange == "US"
    assert result.rows[0].name == "SS&C Technologies Holdings, Inc."
    assert result.rows[0].cusip == "78467J100"
    assert result.rows[0].weight == Decimal("0.015860798135")
    assert result.rows[0].shares == Decimal("82566.0")
    assert result.rows[0].market_value == Decimal("5256151.56")
    assert result.rows[0].currency == "USD"
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["source_provider"] == "running_oak"
    assert result.legal_metadata["route_resolution"] == "issuer_filepoint_holdings_json"
    assert result.legal_metadata["composition_date"] == "2026-06-26"


@pytest.mark.asyncio
async def test_hennessy_adapter_parses_product_page_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("hennessy")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <html>
              <table><tr><th>Ticker</th><th>STNC</th></tr></table>
              <table>
                <tr>
                  <th>Name</th><th>Ticker</th><th>CUSIP</th>
                  <th>Shares</th><th>Market Value</th><th>% of Net Assets</th>
                </tr>
                <tr>
                  <td>Short Table Holding</td><td>SHORT</td><td>999999999</td>
                  <td>1</td><td>$1</td><td>1.0%</td>
                </tr>
              </table>
              <table>
                <tr>
                  <th>Name</th><th>Ticker</th><th>CUSIP</th>
                  <th>Shares</th><th>Market Value</th><th>% of Net Assets</th>
                </tr>
                <tr>
                  <td>Intel Corp</td><td>INTC</td><td>458140100</td>
                  <td>40,218</td><td>$5,160,773.76</td><td>5.4%</td>
                </tr>
                <tr>
                  <td>Applied Materials Inc</td><td>AMAT</td><td>038222105</td>
                  <td>7,087</td><td>$4,442,415.08</td><td>4.7%</td>
                </tr>
              </table>
            </html>
            """,
            content_type="text/html",
            url="https://www.hennessyetfs.com/etfs/stnc",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="STNC", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.hennessyetfs.com/etfs/stnc"
    assert [row.symbol for row in result.rows] == ["INTC", "AMAT"]
    assert result.rows[0].name == "Intel Corp"
    assert result.rows[0].cusip == "458140100"
    assert result.rows[0].weight == Decimal("0.054")
    assert result.rows[0].shares == Decimal("40218")
    assert result.rows[0].market_value == Decimal("5160773.76")
    assert result.rows[0].currency == "USD"
    assert result.legal_metadata["source_provider"] == "hennessy"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_holdings_table"
    assert result.legal_metadata["source_format"] == "html"


@pytest.mark.asyncio
async def test_applied_finance_adapter_parses_etf_constituents_table(monkeypatch):
    adapter = get_holdings_adapter("applied_finance")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <html>
              <table id="etf_constituents">
                <tr>
                  <th>As Of Date</th><th>Ticker</th><th>Name</th>
                  <th>Weight</th><th>Market Value</th><th>FIGI</th>
                  <th>Shares Held</th>
                </tr>
                <tr>
                  <td>7/2/2026</td><td>2556706D</td>
                  <td>SYCAMORE PARTNERS LLC-CVR</td><td>0.00%</td>
                  <td>0.00</td><td></td><td>1,820</td>
                </tr>
                <tr>
                  <td>7/2/2026</td><td>A</td>
                  <td>AGILENT TECHNOLOGIES INC</td><td>0.08%</td>
                  <td>460,420.87</td><td>BBG000C2V3D6</td><td>3,523</td>
                </tr>
              </table>
            </html>
            """,
            content_type="text/html",
            url="https://appliedfinancefunds.com/ETF/ETFData/VSLU",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="VSLU", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://appliedfinancefunds.com/ETF/ETFData/VSLU"
    assert [row.symbol for row in result.rows] == ["2556706D", "A"]
    assert result.rows[1].name == "AGILENT TECHNOLOGIES INC"
    assert result.rows[1].weight == Decimal("0.0008")
    assert result.rows[1].shares == Decimal("3523")
    assert result.rows[1].market_value == Decimal("460420.87")
    assert result.rows[1].currency == "USD"
    assert result.rows[1].extra_data["FIGI"] == "BBG000C2V3D6"
    assert result.legal_metadata["source_provider"] == "applied_finance"
    assert result.legal_metadata["route_resolution"] == "issuer_public_product_page_holdings_table"
    assert result.legal_metadata["composition_date"] == "2026-07-02"
    assert result.legal_metadata["source_format"] == "html"


@pytest.mark.asyncio
async def test_first_eagle_adapter_parses_product_page_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("first_eagle")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <html>
              <section>ETF Holdings As of Jun 29, 2026</section>
              <table>
                <tr><th>Some</th><th>Other</th></tr>
                <tr><td>Not</td><td>Holdings</td></tr>
              </table>
              <table>
                <tr>
                  <th>Stock Ticker</th><th>CUSIP/Other</th><th>Security Name</th>
                  <th>Shares</th><th>Price</th><th>Market Value</th><th>Weightings</th>
                </tr>
                <tr>
                  <td>Cash&amp;Other</td><td>Cash&amp;Other</td><td>Cash &amp; Other</td>
                  <td>19,259,769</td><td>1.00</td><td>$19,259,769.10</td><td>0.95%</td>
                </tr>
                <tr>
                  <td>005930 KS</td><td>6771720</td><td>Samsung Electronics Co Ltd</td>
                  <td>327,243</td><td>339,133.00</td><td>$72,317,802.89</td><td>3.57%</td>
                </tr>
                <tr>
                  <td>GOOG</td><td>02079K107</td><td>Alphabet Inc</td>
                  <td>123,456</td><td>178.50</td><td>$22,036,416.00</td><td>2.62%</td>
                </tr>
              </table>
            </html>
            """,
            content_type="text/html",
            url="https://www.firsteagle.com/funds/global-equity-etf",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="FEGE", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.firsteagle.com/funds/global-equity-etf"
    assert [row.row_type for row in result.rows] == ["cash", "security", "security"]
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "Cash & Other"
    assert result.rows[0].weight == Decimal("0.0095")
    assert result.rows[0].market_value == Decimal("19259769.10")
    assert result.rows[1].symbol == "005930"
    assert result.rows[1].exchange == "KS"
    assert result.rows[1].sedol == "6771720"
    assert result.rows[1].cusip is None
    assert result.rows[1].weight == Decimal("0.0357")
    assert result.rows[1].shares == Decimal("327243")
    assert result.rows[1].market_value == Decimal("72317802.89")
    assert result.rows[2].symbol == "GOOG"
    assert result.rows[2].cusip == "02079K107"
    assert result.legal_metadata["source_provider"] == "first_eagle"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_holdings_table"
    assert result.legal_metadata["source_format"] == "html"
    assert result.legal_metadata["composition_date"] == "2026-06-29"


@pytest.mark.asyncio
async def test_tapp_adapter_discovers_google_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("tapp")
    assert adapter is not None

    holdings_url = (
        "https://docs.google.com/spreadsheets/export"
        "?id=1Q_N-DI9P4dj4QKioTXUcoXgL3NOC0nkzztJ4ntbuWfo&exportFormat=csv"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=f'<a href="{holdings_url}">Download Holdings CSV</a>',
            content_type="text/html",
            url="https://www.tappalphafunds.com/etfs/tdax",
        ),
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,Stock Ticker,CUSIP,Security Name,Shares,Price,Market Value,Weightings,Net Assets",
                    "06/29/2026,TDAX,26923N546-TRS-01/12/28-L,26923N546-TRS-01/12/28-L,ETF OPPORTUNITIES TRUST TAPPALPHA INNVTN SWAP CS,1955181,27.32,53415544.92,129.93%,41111448",
                    "06/29/2026,TDAX,FGXXX,31846V336,First American Government Obligations Fund 12/01/2031,27452452.06,100,27452452.06,66.78%,41111448",
                    "06/29/2026,TDAX,Cash&Other,Cash&Other,Cash & Other,-39761858.88,1,-39761858.88,-96.72%,41111448",
                    "06/29/2026,OTHER,AAPL,037833100,Apple Inc,1,200,200,1%,20000",
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="TDAX", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.tappalphafunds.com/etfs/tdax"
    assert FakeAsyncClient.requested[1][0] == holdings_url
    assert [row.holding_type for row in result.rows] == ["swap", "fund", "cash"]
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "ETF OPPORTUNITIES TRUST TAPPALPHA INNVTN SWAP CS"
    assert result.rows[0].cusip is None
    assert result.rows[0].weight == Decimal("1.2993")
    assert result.rows[1].symbol == "FGXXX"
    assert result.rows[1].cusip == "31846V336"
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.rows[2].weight == Decimal("-0.9672")
    assert result.legal_metadata["source_provider"] == "tapp"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_google_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-29"


@pytest.mark.asyncio
async def test_tuttle_adapter_discovers_income_blast_google_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("tuttle")
    assert adapter is not None

    holdings_url = (
        "https://docs.google.com/spreadsheets/export"
        "?id=14SlKR5cGsW3si8JKjQfDq-0tzVr_ZDk_lLYe9wyi9eo&exportFormat=csv"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=f'<a href="{holdings_url}">Download Holdings CSV</a>',
            content_type="text/html",
            url="https://www.incomeblastetfs.com/etf/mago",
        ),
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,Stock Ticker,CUSIP,Security Name,Shares,Price,Market Value,Weightings,Net Assets",
                    "07/02/2026,MAGO,2AAPL 260918C00245010,2AAPL 260918C00245010,AAPL 09/18/2026 245.01 C,10,null,53591.6,2.65%,2022201",
                    "07/02/2026,MAGO,912797RS8,912797RS8,United States Treasury Bill 09/03/2026,1739000,null,1727921.35,85.45%,2022201",
                    "07/02/2026,MAGO,Cash&Other,Cash&Other,Cash & Other,27571.98,null,27571.98,1.36%,2022201",
                    "07/02/2026,OTHER,AAPL,037833100,Apple Inc,1,200,200,1%,20000",
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="MAGO", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.incomeblastetfs.com/etf/mago"
    assert FakeAsyncClient.requested[1][0] == holdings_url
    assert [row.holding_type for row in result.rows] == ["option", "fixed_income", "cash"]
    assert result.rows[0].symbol is None
    assert result.rows[0].cusip is None
    assert result.rows[0].weight == Decimal("0.0265")
    assert result.rows[0].market_value == Decimal("53591.6")
    assert result.rows[1].symbol is None
    assert result.rows[1].cusip == "912797RS8"
    assert result.rows[1].weight == Decimal("0.8545")
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.rows[2].weight == Decimal("0.0136")
    assert result.legal_metadata["source_provider"] == "tuttle"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_google_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-02"


@pytest.mark.asyncio
async def test_yorkville_adapter_discovers_truth_social_google_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("yorkville")
    assert adapter is not None

    holdings_url = (
        "https://docs.google.com/spreadsheets/export"
        "?id=1j-Oe_ySv_nafdf6Ku1IWnPYqUy8RbnK7pyXM7YzPorQ&exportFormat=csv"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=f'<a href="{holdings_url}">Download Holdings CSV</a>',
            content_type="text/html",
            url="https://www.truthsocialfunds.com/etfs/tsic",
        ),
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,Stock Ticker,CUSIP,Security Name,Shares,Price,Market Value,Weightings,Net Assets",
                    "07/06/2026,TSIC,ACI,013091103,Albertsons Cos Inc,244,null,3447.72,0.15%,2314656",
                    "07/06/2026,TSIC,ADM,039483102,Archer-Daniels-Midland Co,353,null,27106.87,1.17%,2314656",
                    "07/06/2026,OTHER,AAPL,037833100,Apple Inc,1,200,200,1%,20000",
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="TSIC", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.truthsocialfunds.com/etfs/tsic"
    assert FakeAsyncClient.requested[1][0] == holdings_url
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ACI"
    assert result.rows[0].cusip == "013091103"
    assert result.rows[0].name == "Albertsons Cos Inc"
    assert result.rows[0].shares == Decimal("244")
    assert result.rows[0].market_value == Decimal("3447.72")
    assert result.rows[0].weight == Decimal("0.0015")
    assert result.rows[1].symbol == "ADM"
    assert result.rows[1].cusip == "039483102"
    assert result.rows[1].weight == Decimal("0.0117")
    assert result.legal_metadata["source_provider"] == "yorkville"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_google_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-06"


@pytest.mark.asyncio
async def test_true_shares_adapter_discovers_google_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("true_shares")
    assert adapter is not None

    holdings_url = (
        "https://docs.google.com/spreadsheets/export"
        "?id=17f1gPEVOaxXna1Vbr98Zhfxd208yS1xARzFV1SNTWqU&exportFormat=csv"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=f'<a href="{holdings_url}">Download Holdings CSV</a>',
            content_type="text/html",
            url="https://www.true-shares.com/etf/oneh",
        ),
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,Stock Ticker,CUSIP,Security Name,Shares,Price,Market Value,Weightings,Net Assets",
                    "7/6/2026,ONEH,912797UG0,912797UG0,TREASURY BILL B 09/17/26,7447000,99.265177,7392277.73,50.95,14509457",
                    "7/6/2026,ONEH,RCXTESHT,RCXTESHT,RECV RCXTESHT SHALLOW HEDGE,77211.9528,91.91,7096550.58,-1.4,14509457",
                    "7/6/2026,ONEH,RCXTESHT,RCXTESHT,PAYB RCXTESHT SHALLOW HEDGE,-7300006.64,100,-7300006.64,0,14509457",
                    "7/6/2026,OTHER,AAPL,037833100,Apple Inc,1,200,200,1,20000",
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="ONEH", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.true-shares.com/etf/oneh"
    assert FakeAsyncClient.requested[1][0] == holdings_url
    assert len(result.rows) == 3
    assert result.rows[0].symbol is None
    assert result.rows[0].cusip == "912797UG0"
    assert result.rows[0].row_type == "security"
    assert result.rows[0].holding_type == "fixed_income"
    assert result.rows[0].weight == Decimal("0.5095")
    assert result.rows[0].market_value == Decimal("7392277.73")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "other"
    assert result.rows[1].holding_type == "derivative"
    assert result.rows[1].weight == Decimal("-0.014")
    assert result.rows[2].symbol is None
    assert result.rows[2].row_type == "other"
    assert result.rows[2].holding_type == "derivative"
    assert result.rows[2].weight == Decimal("0")
    assert result.legal_metadata["source_provider"] == "true_shares"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_google_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-06"


@pytest.mark.asyncio
async def test_fm_investments_adapter_discovers_drupal_holdings_api(monkeypatch):
    adapter = get_holdings_adapter("fm_investments")
    assert adapter is not None

    listing_url = "https://www.fminvest.com/etfs"
    product_url = "https://www.fminvest.com/etfs/tbil-fm-us-treasury-3-month-bill-etf"
    api_url = "https://www.fminvest.com/api/v1/etfs/1/holdings"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text='<a href="/etfs/tbil-fm-us-treasury-3-month-bill-etf">TBIL</a>',
            content_type="text/html",
            url=listing_url,
        ),
        FakeResponse(
            text='<script type="application/json">{"etf":{"node_id":"1"}}</script>',
            content_type="text/html",
            url=product_url,
        ),
        FakeResponse(
            text=json.dumps(
                [
                    {
                        "field_as_of_date": (
                            '<time datetime="2026-06-29T12:00:00Z">06/29/2026</time>'
                        ),
                        "field_name": "United States Treasury Bill 09/24/2026",
                        "field_symbol": "912797UH8",
                        "field_par_value": "7,193,948,305.48",
                        "field_market_value": "$7,130,201,987.85",
                        "field_weightings": "100.30%\n",
                    },
                    {
                        "field_as_of_date": (
                            '<time datetime="2026-06-29T12:00:00Z">06/29/2026</time>'
                        ),
                        "field_name": "Cash &amp; Other",
                        "field_symbol": "Cash&amp;Other",
                        "field_par_value": "-21,593,305.48",
                        "field_market_value": "-$21,201,987.85",
                        "field_weightings": "-0.30%\n",
                    },
                ]
            ),
            content_type="application/json",
            url=api_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="TBIL", identifiers={})

    assert FakeAsyncClient.requested[0][0] == listing_url
    assert FakeAsyncClient.requested[1][0] == product_url
    assert FakeAsyncClient.requested[2][0] == api_url
    assert len(result.rows) == 2
    assert result.rows[0].symbol is None
    assert result.rows[0].cusip == "912797UH8"
    assert result.rows[0].name == "United States Treasury Bill 09/24/2026"
    assert result.rows[0].holding_type == "fixed_income"
    assert result.rows[0].weight == Decimal("1.0030")
    assert result.rows[0].shares == Decimal("7193948305.48")
    assert result.rows[0].market_value == Decimal("7130201987.85")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.rows[1].name == "Cash & Other"
    assert result.rows[1].weight == Decimal("-0.0030")
    assert result.legal_metadata["source_provider"] == "fm_investments"
    assert result.legal_metadata["route_resolution"] == "issuer_drupal_holdings_api"
    assert result.legal_metadata["node_id"] == "1"
    assert result.legal_metadata["composition_date"] == "2026-06-29"


@pytest.mark.asyncio
async def test_1251_capital_adapter_uses_owned_fm_investments_holdings_api(monkeypatch):
    adapter = get_holdings_adapter("1251_capital")
    assert adapter is not None

    api_url = "https://www.fminvest.com/api/v1/etfs/4/holdings"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=json.dumps(
                [
                    {
                        "field_as_of_date": (
                            '<time datetime="2026-07-13T12:00:00Z">07/13/2026</time>'
                        ),
                        "field_name": "United States Treasury Note/Bond 4.125% 06/30/2028",
                        "field_symbol": "91282CQY0",
                        "field_par_value": "481,947,000.00",
                        "field_market_value": "$481,212,783.87",
                        "field_weightings": "99.85%",
                    }
                ]
            ),
            content_type="application/json",
            url=api_url,
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(
        symbol="UTWO",
        issuer_product_id="4",
        source_url="https://www.fminvest.com/etfs/utwo-us-treasury-2-year-note-etf",
    )

    assert FakeAsyncClient.requested[0][0] == api_url
    assert result.rows[0].cusip == "91282CQY0"
    assert result.rows[0].holding_type == "fixed_income"
    assert result.legal_metadata["source_provider"] == "1251_capital"
    assert result.legal_metadata["route_resolution"] == (
        "1251_capital_fm_investments_holdings_api"
    )
    assert result.legal_metadata["issuer_relationship"] == (
        "1251 Capital parent / F-M Investments ETF issuer"
    )


@pytest.mark.asyncio
async def test_davis_adapter_parses_holdings_download_csv(monkeypatch):
    adapter = get_holdings_adapter("davis")
    assert adapter is not None

    holdings_url = "https://www.davisetfs.com/etfs/us_equity/holdings_download"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    '"Davis Select U.S. Equity ETF All Holdings as of 6/26/26"',
                    'Name,Ticker,"Weighting (%)",Shares,"Market Value ($)",Country,CUSIP',
                    '"Capital One Financial Corp.",COF,6.79,"405,995","82,822,980",,14040H105,2654461,0.20,"Capital One Financial",0.20',
                    '"Samsung Electronics Co., Ltd.","005930 KS",6.63,"83,089","18,381,803","Korea, Republic of (South Korea)",,6771720,2.83,"Samsung Electronics",3.15',
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="DUSA", identifiers={})

    assert FakeAsyncClient.requested[0][0] == holdings_url
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "COF"
    assert result.rows[0].name == "Capital One Financial Corp."
    assert result.rows[0].cusip == "14040H105"
    assert result.rows[0].weight == Decimal("0.0679")
    assert result.rows[0].shares == Decimal("405995")
    assert result.rows[0].market_value == Decimal("82822980")
    assert result.rows[0].extra_data["extra_column_1"] == "2654461"
    assert result.rows[1].symbol == "005930"
    assert result.rows[1].exchange == "KS"
    assert result.rows[1].country == "Korea, Republic of (South Korea)"
    assert result.legal_metadata["source_provider"] == "davis"
    assert result.legal_metadata["route_resolution"] == "issuer_holdings_download_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-26"


@pytest.mark.asyncio
async def test_t_rowe_price_adapter_discovers_product_page_and_fetches_graphql(monkeypatch):
    adapter = get_holdings_adapter("t_rowe_price")
    assert adapter is not None

    overview_url = "https://www.troweprice.com/financial-intermediary/us/en/investments/etfs.html"
    product_url = (
        "https://www.troweprice.com/financial-intermediary/us/en/investments/"
        "etfs/blue-chip-growth-etf.html"
    )
    graphql_url = "https://api.public.troweprice.com/ds-dada/graphql"
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<h3 slot="heading"><a href="/financial-intermediary/us/en/'
                'investments/etfs/blue-chip-growth-etf.html">TCHP</a></h3>'
            ),
            content_type="text/html",
            url=overview_url,
        ),
        FakeResponse(
            text='<script>window["_popConfiguration"] = { productCode: "BCX" };</script>',
            content_type="text/html",
            url=product_url,
        ),
        FakeResponse(
            text=json.dumps(
                {
                    "data": {
                        "fetchData": {
                            "type": "productRequest",
                            "fullHoldingsExhibit": [
                                {
                                    "effectiveDate": "2026-04-30T00:00:00Z",
                                    "currencyCode": "USD",
                                    "assetClass": "Equity",
                                    "holdings": [
                                        {
                                            "rank": 1,
                                            "tickerSymbol": "NVDA",
                                            "name": "NVIDIA",
                                            "cusip": "67066G104",
                                            "shareQuantity": 1610873,
                                            "marketValue": 321481924.61,
                                            "percentageTotalNetAssets": 15.338156,
                                            "sectorName": "Information Technology",
                                            "industryName": "Semiconductors",
                                        },
                                        {
                                            "rank": 2,
                                            "tickerSymbol": "MSFT",
                                            "name": "Microsoft",
                                            "cusip": "594918104",
                                            "shareQuantity": 493094,
                                            "marketValue": 201073871.32,
                                            "percentageTotalNetAssets": 9.593393,
                                        },
                                    ],
                                }
                            ],
                        }
                    }
                }
            ),
            content_type="application/json",
            url=graphql_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="TCHP", identifiers={})

    assert FakeAsyncClient.requested[0][0] == overview_url
    assert FakeAsyncClient.requested[1][0] == product_url
    assert FakeAsyncClient.requested[2][0] == graphql_url
    assert FakeAsyncClient.requested[2][1]["json"]["variables"]["productRequest"]["productRequest"] == {
        "productCode": "BCX"
    }
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].cusip == "67066G104"
    assert result.rows[0].weight == Decimal("0.15338156")
    assert result.rows[0].shares == Decimal("1610873")
    assert result.rows[0].market_value == Decimal("321481924.61")
    assert result.rows[0].currency == "USD"
    assert result.rows[0].holding_type == "equity"
    assert result.legal_metadata["source_provider"] == "t_rowe_price"
    assert result.legal_metadata["route_resolution"] == "issuer_public_product_graphql_full_holdings"
    assert result.legal_metadata["product_code"] == "BCX"
    assert result.legal_metadata["composition_date"] == "2026-04-30"


@pytest.mark.asyncio
async def test_baron_adapter_discovers_latest_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("baron")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<a href="https://live-baron-capital-cms.pantheonsite.io/sites/default/files/'
                'etf-downloads/RONB-HOLDINGS-20260624-0.csv">old</a>'
                '<a href="https://live-baron-capital-cms.pantheonsite.io/sites/default/files/'
                'etf-downloads/RONB-HOLDINGS-20260625-0.csv">new</a>'
            ),
            content_type="text/html",
        ),
        FakeResponse(
            text="\n".join(
                [
                    'Holding,Ticker,"Weight (%)","Market Value ($)",Quantity,CUSIP,ISIN,SEDOL,"Currency Code"',
                    '"SPACE EXPLORATION TECHN CL A",SPCX,29.77%,"$141,199,569.00","922,873",84615Q103,US84615Q1031,BXCVG25,USD',
                    '"TESLA INC",TSLA,11.66%,"$55,313,319.60","147,455",88160R101,US88160R1014,B616C79,USD',
                ]
            ),
            content_type="text/csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="RONB", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.baroncapitalgroup.com/"
    assert FakeAsyncClient.requested[1][0] == (
        "https://live-baron-capital-cms.pantheonsite.io/sites/default/files/"
        "etf-downloads/RONB-HOLDINGS-20260625-0.csv"
    )
    assert result.rows[0].symbol == "SPCX"
    assert result.rows[0].name == "SPACE EXPLORATION TECHN CL A"
    assert result.rows[0].cusip == "84615Q103"
    assert result.rows[0].isin == "US84615Q1031"
    assert result.rows[0].sedol == "BXCVG25"
    assert result.rows[0].weight == Decimal("0.2977")
    assert result.rows[0].market_value == Decimal("141199569.00")
    assert result.rows[0].shares == Decimal("922873")
    assert result.rows[0].currency == "USD"
    assert result.legal_metadata["source_provider"] == "baron"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_linked_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-25"


@pytest.mark.asyncio
async def test_brandes_adapter_filters_shared_iframe_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("brandes")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    (
                        "ETF Issuer,Basket Reporting Status,Basket Evaluation Date,"
                        "Basket Trade Date,Primary Basket ID,Basket Ticker,Official NAV,"
                        "Total Net Assets,ETF Base Currency,Ticker,CUSIP,ISIN,SEDOL,FIGI,"
                        "Security Description,Benchmark Quantity,Calculated Weight - Base,"
                        "Benchmark Market Value (Base),Cash Weight,"
                        "Fund Accounting Asset Group Code"
                    ),
                    (
                        "Tidal ETFs,Final,2026-07-06,2026-07-07,02P997717,BINV.P,"
                        "42.91,510628044.78,USD,TSM,874039100,US8740391003,2113382,"
                        "BBG000BD8ZK0,TAIWAN SEMICONDUCTOR M TWD 10.0 ADR,9322,"
                        "0.00824785560247097,4211586.38,0.020430643354676,"
                        "FS(Foreign Stock)"
                    ),
                    (
                        "Tidal ETFs,Final,2026-07-06,2026-07-07,02P997716,BUSA.P,"
                        "41.62,119392620.41,USD,GOOG,02079K107,US02079K1079,BYY88Y7,"
                        "BBG009S3NB30,ALPHABET INC-CL C,1289,0.018543132,"
                        "2213584.90,0.0091,CS(Common Stock)"
                    ),
                    (
                        "Tidal ETFs,Final,2026-07-06,2026-07-07,02P997716,BUSA.P,"
                        "41.62,119392620.41,USD,USD,,,,,US DOLLAR,1,"
                        "0.009100000,108649.28,0.0091,CU(Currency Security)"
                    ),
                ]
            ),
            content_type="text/csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BUSA", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://etfs.brandes.com/assets/data/6c11_Report.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "GOOG"
    assert result.rows[0].name == "ALPHABET INC-CL C"
    assert result.rows[0].cusip == "02079K107"
    assert result.rows[0].isin == "US02079K1079"
    assert result.rows[0].sedol == "BYY88Y7"
    assert result.rows[0].weight == Decimal("0.018543132")
    assert result.rows[0].market_value == Decimal("2213584.90")
    assert result.rows[0].shares == Decimal("1289")
    assert result.rows[0].currency == "USD"
    assert result.rows[0].holding_type == "equity"
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.legal_metadata["source_provider"] == "brandes"
    assert result.legal_metadata["route_resolution"] == "issuer_iframe_public_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-06"
    assert result.legal_metadata["product_page_url"] == (
        "https://www.brandes.com/etfs/fund-detail/brandes-us-value-etf"
    )


@pytest.mark.asyncio
async def test_ocean_park_adapter_posts_fund_id_and_parses_filepoint_json(monkeypatch):
    adapter = get_holdings_adapter("ocean_park")
    assert adapter is not None

    payload = [
        {
            "asOfDate": "2026-07-06T00:00:00",
            "portfolioNumber": "1356",
            "portfolioName": "Ocean Park Domestic ETF",
            "securityIdentifier": "BBHETFMM",
            "securityTicker": "9BBH",
            "securityDescriptionShort": "BBH SWEEP VEHICLE",
            "securityDescriptionLong": "BBH SWEEP VEHICLE",
            "shares": 67990.7,
            "priceLocal": 100.0,
            "marketValueBase": 67990.7,
            "tradingCurrency": "USD",
            "country": "US",
            "segment": "SHORT TERM INVESTMENTS - OTHER",
            "category": "BANKS SAVINGS-DEPOSIT ACCOUNT",
            "marketValuePercent": 0.005002365593,
        },
        {
            "asOfDate": "2026-07-06T00:00:00",
            "portfolioNumber": "1356",
            "portfolioName": "Ocean Park Domestic ETF",
            "securityIdentifier": "464287655",
            "securityTicker": "IWM US",
            "securityDescriptionShort": "ISHARES RUSSELL 2000 ETF",
            "securityDescriptionLong": "ISHARES RUSSELL 2000 ETF",
            "shares": 125.0,
            "priceLocal": 230.0,
            "marketValueBase": 28750.0,
            "tradingCurrency": "USD",
            "country": "US",
            "segment": "DOMESTIC SMALL CAP BLEND",
            "category": "EXCHANGE TRADED FUND",
            "marketValuePercent": 0.021145,
        },
    ]
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=json.dumps(payload),
            content_type="application/json",
            url="https://filepoint.live/oceanpark_getholdings_cached4.php",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="DUKQ")

    requested_url, request_kwargs = FakeAsyncClient.requested[0]
    assert requested_url == "https://filepoint.live/oceanpark_getholdings_cached4.php"
    assert request_kwargs["data"] == {"fundID": "1356"}
    assert request_kwargs["headers"]["Referer"] == "https://oceanparketfs.com/domestic-etf"
    assert request_kwargs["headers"]["X-Requested-With"] == "XMLHttpRequest"
    assert len(result.rows) == 2
    cash_row = result.rows[0]
    assert cash_row.symbol is None
    assert cash_row.row_type == "cash"
    assert cash_row.holding_type == "cash"
    assert cash_row.weight == Decimal("0.005002365593")
    fund_row = result.rows[1]
    assert fund_row.symbol == "IWM"
    assert fund_row.name == "ISHARES RUSSELL 2000 ETF"
    assert fund_row.cusip == "464287655"
    assert fund_row.shares == Decimal("125.0")
    assert fund_row.market_value == Decimal("28750.0")
    assert fund_row.weight == Decimal("0.021145")
    assert fund_row.currency == "USD"
    assert fund_row.country == "US"
    assert fund_row.holding_type == "fund"
    assert result.source_identifier == "1356"
    assert result.legal_metadata["source_provider"] == "ocean_park"
    assert result.legal_metadata["route_resolution"] == "issuer_public_filepoint_holdings_json"
    assert result.legal_metadata["composition_date"] == "2026-07-06"
    assert result.legal_metadata["product_page_url"] == "https://oceanparketfs.com/domestic-etf"


@pytest.mark.asyncio
async def test_cambiar_adapter_fetches_product_page_linked_workbook(monkeypatch):
    adapter = get_holdings_adapter("cambiar")
    assert adapter is not None

    workbook = _xlsx_workbook(
        [
            [
                "date",
                "fund_id",
                "fund_name",
                "fund_ticker",
                "security_group",
                "security_type",
                "security_isin",
                "security_ticker",
                "security_description",
                "quantity",
                "market_value",
                "notional_value",
                "percent_of_market_value",
                "percent_of_net_assets",
            ],
            [
                "06/25/2026",
                "6525",
                "Cambiar Aggressive Value ETF",
                "CAMX",
                "Cash",
                "",
                "",
                "",
                "Cash",
                "618733.47",
                "618733.47",
                "",
                "0.94",
                "0.93",
            ],
            [
                "06/25/2026",
                "6525",
                "Cambiar Aggressive Value ETF",
                "CAMX",
                "Stock - Foreign",
                "",
                "US0092791005",
                "EADSY",
                "AIRBUS SE - UNSP ADR",
                "54000.0",
                "2980260.0",
                "",
                "4.51",
                "4.47",
            ],
            [
                "06/25/2026",
                "9999",
                "Other Fund",
                "OTHR",
                "Stock - Common",
                "",
                "US0378331005",
                "AAPL",
                "APPLE INC",
                "1",
                "200",
                "",
                "1",
                "1",
            ],
        ]
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<a href="https://cambiar.com/wp-content/uploads/Secure/'
                'SEI_Cambiar_Tradedate_Holdings_06252026-viewall.xlsx">'
                "View all holdings</a>"
            ),
            content_type="text/html",
        ),
        FakeResponse(
            content=workbook,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="CAMX")

    assert FakeAsyncClient.requested[0][0] == "https://cambiar.com/etf/camx/"
    assert FakeAsyncClient.requested[1][0] == (
        "https://cambiar.com/wp-content/uploads/Secure/"
        "SEI_Cambiar_Tradedate_Holdings_06252026-viewall.xlsx"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "Cash"
    assert result.rows[0].row_type == "cash"
    assert result.rows[0].weight == Decimal("0.0093")
    assert result.rows[1].symbol == "EADSY"
    assert result.rows[1].name == "AIRBUS SE - UNSP ADR"
    assert result.rows[1].isin == "US0092791005"
    assert result.rows[1].cusip == "009279100"
    assert result.rows[1].holding_type == "equity"
    assert result.rows[1].shares == Decimal("54000.0")
    assert result.rows[1].market_value == Decimal("2980260.0")
    assert result.rows[1].weight == Decimal("0.0447")
    assert result.legal_metadata["source_provider"] == "cambiar"
    assert result.legal_metadata["source_format"] == "xlsx"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_linked_holdings_workbook"
    assert result.legal_metadata["composition_date"] == "2026-06-25"


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
async def test_burney_adapter_parses_product_page_wpdatatables_holdings(monkeypatch):
    adapter = get_holdings_adapter("burney")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <html>
              <body>
                <h2>Fund Holdings</h2>
                <table id="table_10">
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Name</th>
                      <th>CUSIP</th>
                      <th>Shares</th>
                      <th>Price (Local)</th>
                      <th>Market Value ($mm)</th>
                      <th>% of Net Assets</th>
                      <th>EFFECTIVE_DATE</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>ADTN</td>
                      <td>ADTRAN Holdings Inc</td>
                      <td>00486H105</td>
                      <td>184,606</td>
                      <td>12.71</td>
                      <td>2.35</td>
                      <td>0.40</td>
                      <td>07/06/2026</td>
                    </tr>
                    <tr>
                      <td>AMD</td>
                      <td>Advanced Micro Devices Inc</td>
                      <td>007903107</td>
                      <td>37,154</td>
                      <td>517.82</td>
                      <td>19.24</td>
                      <td>3.30</td>
                      <td>07/06/2026</td>
                    </tr>
                  </tbody>
                </table>
              </body>
            </html>
            """,
            content_type="text/html",
            url="https://burneyetfs.com/brny/",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BRNY", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://burneyetfs.com/brny/"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ADTN"
    assert result.rows[0].name == "ADTRAN Holdings Inc"
    assert result.rows[0].cusip == "00486H105"
    assert result.rows[0].shares == Decimal("184606")
    assert result.rows[0].market_value == Decimal("2350000")
    assert result.rows[0].weight == Decimal("0.004")
    assert result.rows[1].symbol == "AMD"
    assert result.rows[1].market_value == Decimal("19240000")
    assert result.rows[1].weight == Decimal("0.033")
    assert result.legal_metadata["source_provider"] == "burney"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_product_page_wpdatatables_holdings_table"
    )
    assert result.legal_metadata["composition_date"] == "2026-07-06"


@pytest.mark.asyncio
async def test_etf_architect_adapter_parses_alpha_architect_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("etf_architect")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <html>
              <body>
                <script>{"latest_effective_date":"2026-06-17"}</script>
                <section id="fund-holdings">
                  <table id="table_13">
                    <thead>
                      <tr>
                        <th>Ticker</th>
                        <th>Name</th>
                        <th>CUSIP</th>
                        <th>Shares</th>
                        <th>Price (Local)</th>
                        <th>Market Value ($mm)</th>
                        <th>% of Net Assets</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr>
                        <td>ADT</td>
                        <td>ADT Inc</td>
                        <td>00090Q103</td>
                        <td>1,717,080</td>
                        <td>6.83</td>
                        <td>11.73</td>
                        <td>2.14</td>
                      </tr>
                      <tr>
                        <td>T</td>
                        <td>AT&amp;T Inc</td>
                        <td>00206R102</td>
                        <td>483,156</td>
                        <td>20.58</td>
                        <td>9.94</td>
                        <td>1.81</td>
                      </tr>
                    </tbody>
                  </table>
                </section>
              </body>
            </html>
            """,
            content_type="text/html",
            url="https://funds.alphaarchitect.com/qval/",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="QVAL", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://funds.alphaarchitect.com/qval/"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ADT"
    assert result.rows[0].name == "ADT Inc"
    assert result.rows[0].cusip == "00090Q103"
    assert result.rows[0].shares == Decimal("1717080")
    assert result.rows[0].market_value == Decimal("11730000")
    assert result.rows[0].weight == Decimal("0.0214")
    assert result.rows[1].symbol == "T"
    assert result.rows[1].name == "AT&T Inc"
    assert result.rows[1].market_value == Decimal("9940000")
    assert result.rows[1].weight == Decimal("0.0181")
    assert result.legal_metadata["source_provider"] == "etf_architect"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_product_page_wpdatatables_holdings_table"
    )
    assert result.legal_metadata["composition_date"] == "2026-06-17"


@pytest.mark.asyncio
async def test_cullen_adapter_fetches_public_srp_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("cullen")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""Cullen Enhanced Equity Income ETF Holdings as at 2026-07-02

Security Name,Ticker,CUSIP,Shares,Market Value,Percentage
EOG RESOURCES INC,EOG,26875P101,"3,225","427,151.25",4.27
CISCO SYSTEMS INC,CSCO,17275R102,"7,648","414,904.00",4.15
ENERGY SELECT SECTOR SPDR,XLE,81369Y506,"3,559","330,310.79",3.30
""",
            content_type="text/csv",
            url=(
                "https://www.cullenfunds.com/srp/api/fund-holdings-csv-download/38/"
                "?fund_id=3156&as_at_date=2026-07-06"
            ),
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("app.services.etf_holdings_adapters.date", MockDate)
    MockDate.today_value = date(2026, 7, 6)

    result = await adapter.fetch_latest(symbol="DIVP", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.cullenfunds.com/srp/api/fund-holdings-csv-download/38/"
        "?fund_id=3156&as_at_date=2026-07-06"
    )
    assert len(result.rows) == 3
    assert result.rows[0].symbol == "EOG"
    assert result.rows[0].name == "EOG RESOURCES INC"
    assert result.rows[0].cusip == "26875P101"
    assert result.rows[0].shares == Decimal("3225")
    assert result.rows[0].market_value == Decimal("427151.25")
    assert result.rows[0].weight == Decimal("0.0427")
    assert result.rows[2].symbol == "XLE"
    assert result.rows[2].weight == Decimal("0.033")
    assert result.legal_metadata["source_provider"] == "cullen"
    assert result.legal_metadata["route_resolution"] == "issuer_public_srp_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-02"


def test_virtus_adapter_parses_positions_workbook_rows():
    adapter = get_holdings_adapter("virtus")
    assert adapter is not None

    table_rows = [
        ["Positions as of 7/6/2026"],
        ["", "", "", "", "", "", "", "Accrued Int", "", "Notional Value", "", "Market Value"],
        [
            "Account Name",
            "Security Id",
            "Name",
            "Ticker",
            "Security Type",
            "Quantity",
            "Price",
            "(Local)",
            "(Base)",
            "(Local)",
            "(Base)",
            "(Local)",
        ],
        [
            "Virtus Silvant Small/Mid Growth ETF",
            "EQ0010453400001000",
            "Sterling Infrastructure Inc",
            "STRL",
            "Common Stock",
            "161",
            "700.75",
            "0",
            "0",
            "",
            "",
            "112820.75",
        ],
        [
            "Virtus Silvant Small/Mid Growth ETF",
            "USD",
            "Cash/Cash equivalents",
            "",
            "Cash",
            "55295.27",
            "0",
            "0",
            "0",
            "",
            "",
            "55295.27",
        ],
    ]

    rows, composition_date = adapter._parse_positions_table(table_rows, fund_symbol="SSMG")

    assert composition_date == date(2026, 7, 6)
    assert len(rows) == 2
    equity = rows[0]
    assert equity.symbol == "STRL"
    assert equity.name == "Sterling Infrastructure Inc"
    assert equity.holding_type == "equity"
    assert equity.row_type == "security"
    assert equity.shares == Decimal("161")
    assert equity.market_value == Decimal("112820.75")
    assert equity.weight == Decimal("112820.75") / Decimal("168116.02")
    cash = rows[1]
    assert cash.symbol is None
    assert cash.name == "Cash/Cash equivalents"
    assert cash.holding_type == "cash"
    assert cash.row_type == "cash"
    assert cash.weight == Decimal("55295.27") / Decimal("168116.02")


@pytest.mark.asyncio
async def test_virtus_adapter_discovers_public_positions_xls(monkeypatch):
    adapter = get_holdings_adapter("virtus")
    assert adapter is not None

    product_page = """
    <html>
      <a href="/assets/files/a72/positions_ssmg.xls">Download Full Holdings</a>
    </html>
    """
    table_rows = [
        ["Positions as of 7/6/2026"],
        [
            "Account Name",
            "Security Id",
            "Name",
            "Ticker",
            "Security Type",
            "Quantity",
            "Price",
            "",
            "",
            "",
            "",
            "(Local)",
        ],
        [
            "Virtus Silvant Small/Mid Growth ETF",
            "EQ0010027700001000",
            "Carpenter Technology Corp",
            "CRS",
            "Common Stock",
            "172",
            "597.24",
            "0",
            "0",
            "",
            "",
            "102725.28",
        ],
    ]

    def fake_parse_holdings_xls(raw_workbook):
        assert raw_workbook == b"virtus-xls"
        return [], table_rows

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=product_page,
            content_type="text/html",
            url="https://www.virtus.com/products/virtus-silvant-small-mid-growth-etf",
        ),
        FakeResponse(
            content=b"virtus-xls",
            content_type="application/vnd.ms-excel",
            url="https://www.virtus.com/assets/files/a72/positions_ssmg.xls",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("app.services.etf_holdings_adapters.parse_holdings_xls", fake_parse_holdings_xls)

    result = await adapter.fetch_latest(symbol="SSMG")

    assert [request[0] for request in FakeAsyncClient.requested] == [
        "https://www.virtus.com/products/virtus-silvant-small-mid-growth-etf",
        "https://www.virtus.com/assets/files/a72/positions_ssmg.xls",
    ]
    assert len(result.rows) == 1
    assert result.rows[0].symbol == "CRS"
    assert result.rows[0].weight == Decimal("1")
    assert result.legal_metadata["source_provider"] == "virtus"
    assert result.legal_metadata["source_format"] == "xls"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_positions_xls"
    assert result.legal_metadata["composition_date"] == "2026-07-06"


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
async def test_clearshares_adapter_fetches_native_holdings_workbook(monkeypatch):
    adapter = get_holdings_adapter("clearshares")
    assert adapter is not None
    xls_payload = b"\xd0\xcf\x11\xe0clearshares-xls"

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

    result = await adapter.fetch_latest(symbol="OPER", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://clear-shares.com/download-holdings-usbanks.php?fund=oper"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == "https://clear-shares.com/"
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].cusip == "037833100"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_xls"
    assert result.legal_metadata["source_provider"] == "clearshares"
    assert result.legal_metadata["source_format"] == "xls"


@pytest.mark.asyncio
async def test_clough_adapter_fetches_native_holdings_json(monkeypatch):
    adapter = get_holdings_adapter("clough")
    assert adapter is not None

    payload = {
        "success": True,
        "data": {
            "asOfDate": "07/02/2026",
            "holdings": [
                {
                    "name": "Tenable Holdings Inc",
                    "hTicker": "TENB",
                    "cusip": "88025T102",
                    "sharesPar": "45,361",
                    "weight": "3.55%",
                    "marketValue": "$1,719,181.90",
                },
                {
                    "name": "BROKER SWEEP",
                    "hTicker": "GS.BROKER",
                    "cusip": "GS.BROKER",
                    "sharesPar": "22,297,187",
                    "weight": "36.46%",
                    "marketValue": "$22,297,187.32",
                },
            ],
        },
    }
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=json.dumps(payload),
            content_type="application/json",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="CBSE", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.cloughcapital.com/wp-admin/admin-ajax.php"
        "?action=get_holdings_json&slug=cbse"
    )
    assert result.rows[0].symbol == "TENB"
    assert result.rows[0].name == "Tenable Holdings Inc"
    assert result.rows[0].cusip == "88025T102"
    assert result.rows[0].shares == Decimal("45361")
    assert result.rows[0].weight == Decimal("0.0355")
    assert result.rows[0].market_value == Decimal("1719181.90")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.rows[1].extra_data["source_symbol"] == "GS.BROKER"
    assert result.legal_metadata["route_resolution"] == "issuer_wordpress_holdings_json"
    assert result.legal_metadata["source_provider"] == "clough"
    assert result.legal_metadata["source_format"] == "json"
    assert result.legal_metadata["composition_date"] == "2026-07-02"


@pytest.mark.asyncio
async def test_palmer_square_adapter_parses_embedded_holdings_json(monkeypatch):
    adapter = get_holdings_adapter("palmer_square")
    assert adapter is not None

    raw_html = """
    <html>
      <body>
        <h3>Full Investment Holdings as of Jul 1, 2026</h3>
        <script>
          var holdingsData = [
            {
              "cusip": "64755YAJ7",
              "name": "NEW MOUNTAIN FLT 04/39",
              "asset_type": "CDO/COLLATERALIZED DEBT OBLIGATION",
              "shares_par": "1,000,000.00000000",
              "market_value": "997,441.09",
              "weight_percent": "0.38"
            },
            {
              "cusip": "USD",
              "name": "Cash & Cash Equivalents",
              "asset_type": "Cash",
              "shares_par": "125.00",
              "market_value": "125.00",
              "weight_percent": "0.01"
            }
          ];
        </script>
      </body>
    </html>
    """
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_html,
            content_type="text/html",
            url="https://etf.palmersquarefunds.com/funds/us-etfs/palmer-square-credit-opportunities-etf",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="PSQO", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://etf.palmersquarefunds.com/funds/us-etfs/"
        "palmer-square-credit-opportunities-etf"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "NEW MOUNTAIN FLT 04/39"
    assert result.rows[0].cusip == "64755YAJ7"
    assert result.rows[0].holding_type == "fixed_income"
    assert result.rows[0].shares == Decimal("1000000.00000000")
    assert result.rows[0].market_value == Decimal("997441.09")
    assert result.rows[0].weight == Decimal("0.0038")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_embedded_holdings_json"
    assert result.legal_metadata["source_provider"] == "palmer_square"
    assert result.legal_metadata["composition_date"] == "2026-07-01"


@pytest.mark.asyncio
async def test_future_fund_adapter_parses_preamble_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("future_fund")
    assert adapter is not None

    raw_csv = """The Future Fund Long/Short ETF
Fund Holdings Data as of 07/01/2026
Name,Security Identifier,Symbol,Net Assets %,Market Price,Shares Held,Market Value,Market Value %
US DOLLAR BROKER,USDB,USDB,56.38,1.00,"24,497,621.85","24,497,621.85",56.40
NVIDIA CORP,67066G104,NVDA US,6.37,197.58,"14,011.00","2,768,293.38",6.37
"""
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_csv,
            url="https://futurefundetf.com/modules/mod_csvtables_copy/cron/holdings.csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="FFLS", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://futurefundetf.com/modules/mod_csvtables_copy/cron/holdings.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol is None
    assert result.rows[0].row_type == "cash"
    assert result.rows[0].holding_type == "cash"
    assert result.rows[0].weight == Decimal("0.564")
    assert result.rows[1].symbol == "NVDA"
    assert result.rows[1].exchange == "US"
    assert result.rows[1].name == "NVIDIA CORP"
    assert result.rows[1].cusip == "67066G104"
    assert result.rows[1].shares == Decimal("14011.00")
    assert result.rows[1].market_value == Decimal("2768293.38")
    assert result.rows[1].weight == Decimal("0.0637")
    assert result.legal_metadata["source_provider"] == "future_fund"
    assert result.legal_metadata["issuer_schema"] == "preamble_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-01"


@pytest.mark.asyncio
async def test_future_fund_adapter_parses_account_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("future_fund")
    assert adapter is not None

    raw_csv = """Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag
07/02/2026,FFOX,ADMA,000899104,ADMA Biologics Inc,248524.00000000,8.610000,2139791.64,0.89%,240000000,12000000,240,
07/02/2026,OTHER,ZZZ,000000000,Other Holding,1,1,1,1.00%,1,1,1,
07/02/2026,FFOX,CASH,CASH,Cash Sweep,1000,1,1000,0.01%,240000000,12000000,240,Y
"""
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_csv,
            url=(
                "https://futurefundetf.com/modules/mod_csvtables_ffox/cron/"
                "FundxFutureWeb.40F3.F3_Holdings.csv"
            ),
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="FFOX", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://futurefundetf.com/modules/mod_csvtables_ffox/cron/"
        "FundxFutureWeb.40F3.F3_Holdings.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ADMA"
    assert result.rows[0].name == "ADMA Biologics Inc"
    assert result.rows[0].cusip == "000899104"
    assert result.rows[0].shares == Decimal("248524.00000000")
    assert result.rows[0].market_value == Decimal("2139791.64")
    assert result.rows[0].weight == Decimal("0.0089")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.legal_metadata["source_provider"] == "future_fund"
    assert result.legal_metadata["issuer_schema"] == "account_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-02"


@pytest.mark.asyncio
async def test_counterpoint_adapter_parses_symbol_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("counterpoint")
    assert adapter is not None

    raw_csv = """asOfDate,portfolioNumber,portfolioName,securityIdentifier,securityTicker,securityDescriptionShort,securityDescriptionLong,shares,priceLocal,marketValueBase,fxRate,tradingCurrency,accruedIncome,incomeCurrency,country,longShortIndicator,segment,category,sector,industry,marketValuePercent,netAssetsPercent,grossAssetPercent
2026-06-30T00:00:00,1351,Counterpoint Quantitative Equity ETF,BBHETFMM,9BBH,BBH SWEEP VEHICLE,BBH SWEEP VEHICLE,653582.22,100,653582.22,1,USD,1279.03,USD,US,Long,SHORT TERM INVESTMENTS - OTHER,BANKS SAVINGS-DEPOSIT ACCOUNT,BANKS SAVINGS-DEPOSIT ACCOUNT,BANKS SAVINGS-DEPOSIT ACCOUNT,0.00176722665,0.001767192088,0
2026-06-30T00:00:00,1351,Counterpoint Quantitative Equity ETF,037833100,AAPL US,APPLE INC,Apple Inc.,25488,289.36,7375207.68,1,USD,0,USD,US,Long,COMMON STOCKS,TECHNOLOGY,TECHNOLOGY HARDWARE,COMMUNICATIONS EQUIPMENT,0.019941888206,0.019941498196,0
"""
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_csv,
            url="https://counterpointfunds.com/etfdata/holdings_cpai.csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="CPAI", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://counterpointfunds.com/etfdata/holdings_cpai.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol is None
    assert result.rows[0].row_type == "cash"
    assert result.rows[0].holding_type == "cash"
    assert result.rows[0].market_value == Decimal("653582.22")
    assert result.rows[0].weight == Decimal("0.001767192088")
    assert result.rows[1].symbol == "AAPL"
    assert result.rows[1].exchange == "US"
    assert result.rows[1].name == "Apple Inc."
    assert result.rows[1].cusip == "037833100"
    assert result.rows[1].shares == Decimal("25488")
    assert result.rows[1].market_value == Decimal("7375207.68")
    assert result.rows[1].weight == Decimal("0.019941498196")
    assert result.legal_metadata["source_provider"] == "counterpoint"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-30"


@pytest.mark.asyncio
async def test_howard_capital_adapter_parses_symbol_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("howard_capital")
    assert adapter is not None

    raw_csv = """asOfDate,portfolioNumber,portfolioName,securityIdentifier,securityTicker,securityDescriptionShort,securityDescriptionLong,shares,priceLocal,marketValueBase,fxRate,tradingCurrency,accruedIncome,incomeCurrency,country,longShortIndicator,segment,category,sector,industry,marketValuePercent,netAssetsPercent,grossAssetPercent
2026-07-02T00:00:00,1241,HCM Defender 100 Index ETF,74347X831,TQQQ US,PROSHARES UL QQQ,ProShares UltraPro QQQ USD Class,1857072,73.35,136216231.2,1,USD,0,USD,US,Long,EXCHANGE-TRADED FUNDS,EQUITY,EQUITY,EQUITY,0.183607908661,0.183590553948,0
2026-07-02T00:00:00,1241,HCM Defender 100 Index ETF,037833100,AAPL US,APPLE INC,Apple Inc.,237541,308.63,73312278.83,1,USD,0,USD,US,Long,COMMON STOCKS,TECHNOLOGY,TECHNOLOGY HARDWARE,COMMUNICATIONS EQUIPMENT,0.098818724293,0.098809383897,0
2026-07-02T00:00:00,1241,HCM Defender 100 Index ETF,CASHUSD,,US Dollar,US Dollar,100,1,100,1,USD,0,USD,US,Long,CASH,CASH,CASH,CASH,0.000001,0.000001,0
"""
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_csv,
            url="https://howardcmfunds.com/wp-content/themes/cms/assets/hcm-defender-100-holdings.csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="QQH", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://howardcmfunds.com/wp-content/themes/cms/assets/hcm-defender-100-holdings.csv"
    )
    assert len(result.rows) == 3
    assert result.rows[0].symbol == "TQQQ"
    assert result.rows[0].exchange == "US"
    assert result.rows[0].holding_type == "fund"
    assert result.rows[0].cusip == "74347X831"
    assert result.rows[0].shares == Decimal("1857072")
    assert result.rows[0].market_value == Decimal("136216231.2")
    assert result.rows[0].weight == Decimal("0.183590553948")
    assert result.rows[1].symbol == "AAPL"
    assert result.rows[1].holding_type == "equity"
    assert result.rows[1].name == "Apple Inc."
    assert result.rows[1].cusip == "037833100"
    assert result.rows[2].symbol is None
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].holding_type == "cash"
    assert result.legal_metadata["source_provider"] == "howard_capital"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-02"


@pytest.mark.asyncio
async def test_deepwater_adapter_parses_product_page_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("deepwater")
    assert adapter is not None

    raw_html = """
    <html>
      <body>
        <table class="table-top-holdings responsive" data-title="DBSC" data-asof="2026-04-23">
          <thead>
            <tr>
              <th>Name</th>
              <th>Symbol</th>
              <th>Shares</th>
              <th>Market Value</th>
              <th>Weightings (%)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Credo Technology Group Holding Ltd</td>
              <td>CRDO</td>
              <td>721.00</td>
              <td>$136,622.29</td>
              <td>3.02%</td>
            </tr>
            <tr>
              <td>SiTime Corp</td>
              <td>SITM</td>
              <td>238.00</td>
              <td>$124,833.38</td>
              <td>2.76%</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_html,
            url="https://etfs.deepwatermgmt.com/dbsc-2/",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="DBSC", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://etfs.deepwatermgmt.com/dbsc-2/"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "CRDO"
    assert result.rows[0].name == "Credo Technology Group Holding Ltd"
    assert result.rows[0].shares == Decimal("721.00")
    assert result.rows[0].market_value == Decimal("136622.29")
    assert result.rows[0].weight == Decimal("0.0302")
    assert result.rows[0].currency == "USD"
    assert result.rows[1].symbol == "SITM"
    assert result.rows[1].weight == Decimal("0.0276")
    assert result.legal_metadata["source_provider"] == "deepwater"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_holdings_table"
    assert result.legal_metadata["composition_date"] == "2026-04-23"


@pytest.mark.asyncio
async def test_zacks_adapter_parses_symbol_holdings_download(monkeypatch):
    adapter = get_holdings_adapter("zacks")
    assert adapter is not None

    raw_csv = """Zacks Earnings Consistent Portfolio ETF
Fund Holdings Data as of 07/02/2026
Name, Security Identifier, Symbol, Net Assets %, Market Price, Shares Held, Market Value, Market Value %
BBH SWEEP VEHICLE, BBHETFMM, 9BBH, 2.195982243500, 100.000000000000, 7839669.1900000, 7839669.19, 2.196097106700
RTX CORP, 75513E101, RTX US, 1.848780296500, 199.250000000000, 33125.0000000, 6600156.25, 1.848876998900
PROLOGIS INC, 74340W103, PLD US, 0.689259577400, 139.430000000000, 17648.0000000, 2460660.64, 0.689295629900
"""
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_csv,
            content_type="application/octet-stream",
            url="https://www.zacksetfs.com/webservices/holdings.php",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="ZECP", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.zacksetfs.com/webservices/holdings.php"
    assert len(result.rows) == 3
    assert result.rows[0].symbol is None
    assert result.rows[0].row_type == "cash"
    assert result.rows[0].holding_type == "cash"
    assert result.rows[0].shares == Decimal("7839669.1900000")
    assert result.rows[0].market_value == Decimal("7839669.19")
    assert result.rows[0].weight == Decimal("0.021959822435")
    assert result.rows[1].symbol == "RTX"
    assert result.rows[1].exchange == "US"
    assert result.rows[1].cusip == "75513E101"
    assert result.rows[1].holding_type == "equity"
    assert result.rows[1].shares == Decimal("33125.0000000")
    assert result.rows[1].market_value == Decimal("6600156.25")
    assert result.rows[1].weight == Decimal("0.018487802965")
    assert result.rows[2].symbol == "PLD"
    assert result.legal_metadata["source_provider"] == "zacks"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_download"
    assert result.legal_metadata["composition_date"] == "2026-07-02"
    assert result.legal_metadata["product_page_url"] == "https://www.zacksetfs.com/zecp.php"


@pytest.mark.asyncio
async def test_anfield_adapter_discovers_product_page_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("anfield")
    assert adapter is not None

    page_html = """
    <html>
      <body>
        <a href="/csv/holdings-2924-2026-07-03-06-10.csv">Download holdings</a>
      </body>
    </html>
    """
    raw_csv = """Anfield Enhanced Market ETF
Fund Holdings Data as of 07/02/2026
Name, Security Identifier, Symbol, Net Assets %, Market Price, Shares Held, Market Value, Market Value %
US DOLLAR FUTURE, USDF, USDF, 0.000491754400, 1.000000000000, 9.2700000, 9.27, 0.000492620600
US DOLLARS, USD, USD, 342.545442735900, 1.000000000000, 6457280.9200000, 6457280.92, 343.148803690300
Receivables/Payables, RECPAY, RECPAY, -242.721765193400, 1.000000000000, -4575517.3700000, -4575517.37, -243.149296310900
"""
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=page_html,
            content_type="text/html",
            url="https://anfieldfunds.com/our-funds/anfield-enhanced-market-strategy-etf/",
        ),
        FakeResponse(
            text=raw_csv,
            url="https://anfieldfunds.com/csv/holdings-2924-2026-07-03-06-10.csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="AEMS", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://anfieldfunds.com/our-funds/anfield-enhanced-market-strategy-etf/"
    )
    assert FakeAsyncClient.requested[1][0] == (
        "https://anfieldfunds.com/csv/holdings-2924-2026-07-03-06-10.csv"
    )
    assert len(result.rows) == 3
    assert all(row.symbol is None for row in result.rows)
    assert all(row.row_type == "cash" for row in result.rows)
    assert result.rows[0].name == "US DOLLAR FUTURE"
    assert result.rows[0].weight == Decimal("0.000004926206")
    assert result.rows[1].market_value == Decimal("6457280.92")
    assert result.rows[1].weight == Decimal("3.431488036903")
    assert result.rows[2].market_value == Decimal("-4575517.37")
    assert result.rows[2].weight == Decimal("-2.431492963109")
    assert result.legal_metadata["source_provider"] == "anfield"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_discovered_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-02"


@pytest.mark.asyncio
async def test_brookmont_adapter_discovers_product_page_all_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("brookmont")
    assert adapter is not None

    page_html = """
    <html>
      <body>
        <script src="https://retirementwealth.com/wp-content/themes/retirement-wealth/inc/gemini/etf-holding.js"></script>
        <a href="https://retirementwealth.com/wp-content/themes/retirement-wealth/inc/1485_all_holdings.csv">
          Download all holdings
        </a>
      </body>
    </html>
    """
    raw_csv = """Brookstone Active ETF
Fund Holdings Data as of 07/02/2026
Name, Security Identifier, Symbol, Net Assets %, Market Price, Shares Held, Market Value, Market Value %
BBH SWEEP VEHICLE, BBHETFMM, 9BBH, 0.961691962000, 100.000000000000, 485598.1400000, 485598.14, 0.961788776000
STATE STREET SPD, 78464A854, SPYM US, 22.785557219800, 87.670000000000, 131235.0000000, 11505372.45, 22.787851054100
Receivables/Payables, RECPAY, RECPAY, -0.020553590700, 1.000000000000, -10378.3600000, -10378.36, -0.020555659800
"""
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=page_html,
            content_type="text/html",
            url="https://www.brookstoneam.com/brookstone-active-etf",
        ),
        FakeResponse(
            text=raw_csv,
            url="https://retirementwealth.com/wp-content/themes/retirement-wealth/inc/1485_all_holdings.csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BAMA", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.brookstoneam.com/brookstone-active-etf"
    assert FakeAsyncClient.requested[1][0] == (
        "https://retirementwealth.com/wp-content/themes/retirement-wealth/inc/1485_all_holdings.csv"
    )
    assert len(result.rows) == 3
    assert result.rows[0].symbol is None
    assert result.rows[0].row_type == "cash"
    assert result.rows[0].holding_type == "cash"
    assert result.rows[0].weight == Decimal("0.00961788776")
    assert result.rows[1].symbol == "SPYM"
    assert result.rows[1].exchange == "US"
    assert result.rows[1].cusip == "78464A854"
    assert result.rows[1].holding_type == "fund"
    assert result.rows[1].shares == Decimal("131235.0000000")
    assert result.rows[1].market_value == Decimal("11505372.45")
    assert result.rows[1].weight == Decimal("0.227878510541")
    assert result.rows[2].symbol is None
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].market_value == Decimal("-10378.36")
    assert result.rows[2].weight == Decimal("-0.000205556598")
    assert result.legal_metadata["source_provider"] == "brookmont"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_all_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-02"


@pytest.mark.asyncio
async def test_madison_adapter_filters_account_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("madison")
    assert adapter is not None

    raw_csv = """Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag
07/06/2026,CVRD,8AMMF0JA0,8AMMF0JA0,US BANK MMDA - USBGFS 9 09/01/2037,1211418.43000000,100.000000,1211418.43,3.72%,32527522.50,1815000,181.500000000000,Y
07/06/2026,CVRD,A,00846U101,Agilent Technologies Inc,9500.00000000,130.690000,1241555.00,3.82%,32527522.50,1815000,181.500000000000,
07/06/2026,CVRD,A     260821C00140000,A     260821C00140000,A US 08/21/26 C140,-95.00000000,3.150000,-29925.00,-0.09%,32527522.50,1815000,181.500000000000,
07/06/2026,OTHER,MSFT,594918104,Microsoft Corp,100.00000000,497.450000,49745.00,1.00%,5000000.00,100000,10.000000000000,
"""
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_csv,
            url="https://madisonfunds.com/data/etf/MadisonAdvWeb.40M3.M3_ETF_Holdings.csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="CVRD", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://madisonfunds.com/data/etf/MadisonAdvWeb.40M3.M3_ETF_Holdings.csv"
    )
    assert len(result.rows) == 3
    assert result.rows[0].symbol is None
    assert result.rows[0].row_type == "cash"
    assert result.rows[0].holding_type == "cash"
    assert result.rows[0].weight == Decimal("0.0372")
    assert result.rows[1].symbol == "A"
    assert result.rows[1].name == "Agilent Technologies Inc"
    assert result.rows[1].cusip == "00846U101"
    assert result.rows[1].shares == Decimal("9500.00000000")
    assert result.rows[1].market_value == Decimal("1241555.00")
    assert result.rows[1].weight == Decimal("0.0382")
    assert result.rows[2].symbol is None
    assert result.rows[2].holding_type == "option"
    assert result.rows[2].row_type == "security"
    assert result.rows[2].market_value == Decimal("-29925.00")
    assert result.rows[2].weight == Decimal("-0.0009")
    assert result.legal_metadata["source_provider"] == "madison"
    assert result.legal_metadata["route_resolution"] == "issuer_aggregate_account_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-06"


@pytest.mark.asyncio
async def test_motley_fool_adapter_filters_filepoint_account_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("motley_fool")
    assert adapter is not None

    raw_csv = """Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag
07/06/2026,MFIG,AAPL,037833100,Apple Inc,1658.00000000,308.630000,511708.54,4.35%,11769296.00,560000,56.000000000000,
07/06/2026,TMFC,AMZN,023135106,Amazon.com Inc,2150.00000000,226.110000,486136.50,1.23%,39523292.55,1500000,150.000000000000,
07/06/2026,TMFC,CASH,CASH,Cash & Other,1000.00000000,1.000000,1000.00,0.01%,39523292.55,1500000,150.000000000000,Y
"""
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_csv,
            url="https://etfs.fooletfs.com/assets/data/FilepointMotleyF.40MU.FW_Holdings.csv",
            content_type="application/octet-stream",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="TMFC", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://etfs.fooletfs.com/assets/data/FilepointMotleyF.40MU.FW_Holdings.csv"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == "https://etfs.fooletfs.com/"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "AMZN"
    assert result.rows[0].name == "Amazon.com Inc"
    assert result.rows[0].cusip == "023135106"
    assert result.rows[0].shares == Decimal("2150.00000000")
    assert result.rows[0].market_value == Decimal("486136.50")
    assert result.rows[0].weight == Decimal("0.0123")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.rows[1].weight == Decimal("0.0001")
    assert result.legal_metadata["source_provider"] == "motley_fool"
    assert result.legal_metadata["route_resolution"] == "issuer_aggregate_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-06"


@pytest.mark.asyncio
async def test_leuthold_adapter_parses_product_page_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("leuthold")
    assert adapter is not None

    raw_html = """
    <html>
      <body>
        <section>ETF Summary As of July 2, 2026</section>
        <table class="table-striped w-100 table">
          <thead>
            <tr>
              <th>Percentage of Net Assets</th>
              <th>Name</th>
              <th>Identifier (Cusip)</th>
              <th>Shares Held</th>
              <th>Market Value</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>14.57%</td>
              <td>iShares 1-3 Year Treasury Bond ETF</td>
              <td>SHY (464287457)</td>
              <td>121,781</td>
              <td>$9,978,735.14</td>
            </tr>
            <tr>
              <td>14.26%</td>
              <td>State Street Technology Select Sector SPDR ETF</td>
              <td>XLK (81369Y803)</td>
              <td>54,085</td>
              <td>$9,767,210.15</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_html,
            content_type="text/html",
            url="https://funds.leutholdgroup.com/etf/LCR",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="LCR", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://funds.leutholdgroup.com/etf/LCR"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "SHY"
    assert result.rows[0].cusip == "464287457"
    assert result.rows[0].name == "iShares 1-3 Year Treasury Bond ETF"
    assert result.rows[0].holding_type == "fund"
    assert result.rows[0].weight == Decimal("0.1457")
    assert result.rows[0].shares == Decimal("121781")
    assert result.rows[0].market_value == Decimal("9978735.14")
    assert result.rows[1].symbol == "XLK"
    assert result.rows[1].cusip == "81369Y803"
    assert result.legal_metadata["source_provider"] == "leuthold"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_holdings_table"
    assert result.legal_metadata["composition_date"] == "2026-07-02"


@pytest.mark.asyncio
async def test_point_bridge_adapter_parses_maga_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("point_bridge")
    assert adapter is not None

    raw_html = """
    <html>
      <body>
        <table id="tablepress-4" class="tablepress tablepress-id-4 tablepress-responsive">
          <thead>
            <tr>
              <th>StockTicker</th>
              <th>CUSIP</th>
              <th>SecurityName</th>
              <th>Shares</th>
              <th>Weightings</th>
              <th>Date</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>ABT</td>
              <td>002824100</td>
              <td>Abbott Laboratories</td>
              <td>2251.00000000</td>
              <td>0.69%</td>
              <td>07/06/2026</td>
            </tr>
            <tr>
              <td>AMCR</td>
              <td>G0250X149</td>
              <td>Amcor PLC</td>
              <td>5336.00000000</td>
              <td>0.77%</td>
              <td>07/06/2026</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_html,
            content_type="text/html",
            url="https://www.investpolitically.com/maga-holdings/",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="MAGA", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.investpolitically.com/maga-holdings/"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ABT"
    assert result.rows[0].cusip == "002824100"
    assert result.rows[0].name == "Abbott Laboratories"
    assert result.rows[0].shares == Decimal("2251.00000000")
    assert result.rows[0].weight == Decimal("0.0069")
    assert result.rows[1].symbol == "AMCR"
    assert result.rows[1].cusip == "G0250X149"
    assert result.rows[1].weight == Decimal("0.0077")
    assert result.legal_metadata["source_provider"] == "point_bridge"
    assert result.legal_metadata["route_resolution"] == "issuer_holdings_page_tablepress_table"
    assert result.legal_metadata["composition_date"] == "2026-07-06"


@pytest.mark.asyncio
async def test_aptus_adapter_fetches_product_page_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("aptus")
    assert adapter is not None

    html = """
    <html>
      <body>
        <span class="currentdate">Current as of 06/25/2026</span>
        <table class="custom_tables fund_holdings_table">
          <thead>
            <tr>
              <th>Stock Ticker</th>
              <th>Cusip</th>
              <th>Security Desc</th>
              <th>Shares</th>
              <th>Price</th>
              <th>Market Value</th>
              <th>Weightings</th>
              <th>Effective Date</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>BSCU</td>
              <td>46138J460</td>
              <td>Invesco BulletShares 2030 Corporate Bond ETF</td>
              <td>9,353,234.00</td>
              <td>16.65</td>
              <td>155,731,346.10</td>
              <td>10.23%</td>
              <td>06/26/2026</td>
            </tr>
          </tbody>
        </table>
      </body>
    </html>
    """
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [FakeResponse(text=html, content_type="text/html")]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="DRSK")

    assert FakeAsyncClient.requested[0][0] == "https://aptusetfs.com/drsk/"
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == "https://aptusetfs.com/"
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.symbol == "BSCU"
    assert row.name == "Invesco BulletShares 2030 Corporate Bond ETF"
    assert row.cusip == "46138J460"
    assert row.weight == Decimal("0.1023")
    assert row.shares == Decimal("9353234.00")
    assert row.market_value == Decimal("155731346.10")
    assert result.legal_metadata["source_provider"] == "aptus"
    assert result.legal_metadata["source_format"] == "html"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_holdings_table"
    assert result.legal_metadata["composition_date"] == "2026-06-25"


@pytest.mark.asyncio
async def test_arrow_adapter_fetches_native_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("arrow")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    'SELECT "HoldingsEquityPercentage","HoldingsFixedIncomePercentage"<br>"Arrow Reserve Capital Management ETF","","","","","",""',
                    '"Ticker: ARCM","","","","","",""',
                    '"","","","","","",""',
                    '"Holdings as of 06/25/2026","","","","","",""',
                    '"","","","","","",""',
                    '"Symbol","Name","% Of Net Assets","Market Value ($)","Security ID","Country"',
                    '"","AT&T Inc. 4.25% Due 03/01/2027","1.013205","514643.3","00206RDQ2","US"',
                    '"MSFT","Microsoft Corp.","0.500000","250000","594918104","US"',
                ]
            ),
            content_type="text/csv",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="ARCM")

    assert FakeAsyncClient.requested[0][0] == (
        "https://arrowfunds.com/ArrowSharesExport.aspx?ProductID=4&type=holdings"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == (
        "https://arrowfunds.com/default.aspx?menuitemid=518"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol is None
    assert result.rows[0].name == "AT&T Inc. 4.25% Due 03/01/2027"
    assert result.rows[0].cusip == "00206RDQ2"
    assert result.rows[0].holding_type == "fixed_income"
    assert result.rows[0].weight == Decimal("0.01013205")
    assert result.rows[0].market_value == Decimal("514643.3")
    assert result.rows[0].country == "US"
    assert result.rows[1].symbol == "MSFT"
    assert result.rows[1].holding_type == "equity"
    assert result.legal_metadata["source_provider"] == "arrow"
    assert result.legal_metadata["source_format"] == "csv"
    assert result.legal_metadata["route_resolution"] == "issuer_product_id_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-25"


@pytest.mark.asyncio
async def test_alliancebernstein_adapter_fetches_model_linked_workbook(monkeypatch):
    adapter = get_holdings_adapter("alliancebernstein")
    assert adapter is not None

    workbook = _xlsx_workbook(
        [
            ["AB Disruptors ETF", "", "", "", "", "", "", ""],
            ["Full Holdings as of 04/30/2026", "", "", "", "", "", "", ""],
            ["Net Assets $2,478,960,606", "", "", "", "", "", "", ""],
            ["Base Currency: USD", "", "", "", "", "", "", ""],
            ["", "", "", "", "", "", "", ""],
            [" Securities", "", "", "", "", "", "", ""],
            [
                "Units/Par Value/ # of contracts",
                "Issue Description/Name",
                "Accounting Value (BC) ",
                "% of Net Assets",
                "ISIN (Primary ID)",
                "Cusip",
                "Sedol",
                "Ticker",
            ],
            [
                "203705",
                "Broadcom, Inc.",
                "85032578.15",
                "0.034301706104805",
                "US11135F1012",
                "11135F101",
                "BDZ78H9",
                "AVGO",
            ],
        ]
    )
    model_url = (
        "/content/alliancebernstein/us/en-us/investments/products/etf/equities/"
        "ab-disruptors-etf/jcr:content/root/wrapper/abde_section_1349391/"
        "responsiveGrid/abde_layout/column1/abde_holdings.model.json"
    )
    workbook_url = (
        "/content/dam/alliancebernstein/literature/us-holdings/2026/04/"
        "64FN_AB_DISRUPTORS_ETF_full_holdings_0426.xlsx"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=f'<div id="fund-detail-holdings" data-portfolio-holding="{model_url}"></div>',
            content_type="text/html",
        ),
        FakeResponse(
            text=json.dumps({"links": [{"url": workbook_url, "date": "April 2026"}]}),
            content_type="application/json",
        ),
        FakeResponse(
            content=workbook,
            content_type=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="FWD")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.alliancebernstein.com/us/en-us/investments/products/etf/"
        "equities/ab-disruptors-etf.-.00039J509.html"
    )
    assert FakeAsyncClient.requested[1][0].endswith("abde_holdings.model.json")
    assert FakeAsyncClient.requested[2][0].endswith(
        "64FN_AB_DISRUPTORS_ETF_full_holdings_0426.xlsx"
    )
    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.symbol == "AVGO"
    assert row.name == "Broadcom, Inc."
    assert row.isin == "US11135F1012"
    assert row.cusip == "11135F101"
    assert row.sedol == "BDZ78H9"
    assert row.weight == Decimal("0.034301706104805")
    assert row.shares == Decimal("203705")
    assert row.market_value == Decimal("85032578.15")
    assert row.currency == "USD"
    assert result.legal_metadata["source_provider"] == "alliancebernstein"
    assert result.legal_metadata["source_format"] == "xlsx"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_model_workbook"
    assert result.legal_metadata["composition_date"] == "2026-04-30"
    assert result.legal_metadata["net_assets"] == "2478960606"
    assert result.legal_metadata["base_currency"] == "USD"


@pytest.mark.asyncio
async def test_hartford_adapter_fetches_full_holdings_workbook(monkeypatch):
    adapter = get_holdings_adapter("hartford")
    assert adapter is not None

    workbook = _xlsx_workbook(
        [
            ["Hartford Disciplined US Equity ETF"],
            ["Fund holdings are unaudited and are subject to change."],
            [
                "As of Date",
                "Asset Class",
                "Security Description",
                "CUSIP",
                "Ticker/TRACE",
                "SEDOL",
                "ISIN",
                "Country of Issuer",
                "Coupon",
                "Contracts",
                "Base Price",
                "Shares/Par",
                "Original Face Value",
                "Notional Value",
                "Value",
                "% of Net Assets",
            ],
            [
                "06/26/26",
                "Common Stocks",
                "NVIDIA CORP COMMON STOCK USD.001",
                "67066G104",
                "NVDA",
                "2379504",
                "US67066G1040",
                "US",
                "0.00000000000",
                "0.000",
                "195.740000",
                "67028.000",
                "0.000",
                "0.00",
                "13120060.72",
                "0.0692896983",
            ],
            [
                "06/26/26",
                "Common Stocks",
                "APPLE INC COMMON STOCK USD.00001",
                "037833100",
                "AAPL",
                "2046251",
                "US0378331005",
                "US",
                "0.00000000000",
                "0.000",
                "275.150000",
                "34536.000",
                "0.000",
                "0.00",
                "9502580.40",
                "0.0501850519",
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
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="HDUS")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.hartfordfunds.com/dam/en/docs/pub/funddocuments/"
        "fullholdings/HDUS.xlsx"
    )
    assert len(result.rows) == 2
    row = result.rows[0]
    assert row.symbol == "NVDA"
    assert row.name == "NVIDIA CORP COMMON STOCK USD.001"
    assert row.cusip == "67066G104"
    assert row.isin == "US67066G1040"
    assert row.sedol == "2379504"
    assert row.country == "US"
    assert row.shares == Decimal("67028.000")
    assert row.market_value == Decimal("13120060.72")
    assert row.weight == Decimal("0.0692896983")
    assert result.legal_metadata["source_provider"] == "hartford"
    assert result.legal_metadata["source_format"] == "xlsx"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_full_holdings_xlsx"
    assert result.legal_metadata["composition_date"] == "2026-06-26"


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
async def test_bahl_gaynor_adapter_discovers_product_page_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("bahl_gaynor")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <html>
              <body>
                <a href="https://www.bahl-gaynor.com/wp-content/uploads/etf_holdings_csv/BGDV_holdings_2026-07-05.csv">
                  Previous Holdings
                </a>
                <a href="/wp-content/uploads/etf_holdings_csv/BGIG_holdings_2026-07-06.csv">
                  Download Holdings CSV
                </a>
              </body>
            </html>
            """,
            content_type="text/html",
            url="https://www.bahl-gaynor.com/etf/bgig/",
        ),
        FakeResponse(
            text="\n".join(
                [
                    "Name,Symbol/Ticker,CUSIP,Quantity,Weight (%)",
                    '"UnitedHealth Group Inc","UNH","91324P102","252,626","4.94%"',
                    '"Broadcom Inc","AVGO","11135F101","279,430","4.63%"',
                ]
            ),
            content_type="text/csv",
            url=(
                "https://www.bahl-gaynor.com/wp-content/uploads/etf_holdings_csv/"
                "BGIG_holdings_2026-07-06.csv"
            ),
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BGIG", identifiers={})

    assert FakeAsyncClient.requested[0][0] == "https://www.bahl-gaynor.com/etf/bgig/"
    assert FakeAsyncClient.requested[1][0] == (
        "https://www.bahl-gaynor.com/wp-content/uploads/etf_holdings_csv/"
        "BGIG_holdings_2026-07-06.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "UNH"
    assert result.rows[0].name == "UnitedHealth Group Inc"
    assert result.rows[0].cusip == "91324P102"
    assert result.rows[0].shares == Decimal("252626")
    assert result.rows[0].weight == Decimal("0.0494")
    assert result.rows[1].symbol == "AVGO"
    assert result.rows[1].weight == Decimal("0.0463")
    assert result.legal_metadata["source_provider"] == "bahl_gaynor"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_linked_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-06"


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


@pytest.mark.asyncio
async def test_ssc_alps_adapter_fetches_public_proxy_holdings_json(monkeypatch):
    adapter = get_holdings_adapter("ssc")
    assert adapter is not None

    payload = [
        {
            "fullpartial": "full",
            "fundid": "SDOG - ALPS Sector Dividend Dogs ETF",
            "fundsymbol": "SDOG",
            "cusip": "372460105",
            "name": "Genuine Parts Co.",
            "holdingsymbol": "GPC",
            "weight": 0.0255,
            "shares": 259100,
            "marketvalue": 34348887,
            "settlementprice": 132.57,
            "asofdate": "2026-07-02T05:00:00",
            "sedol": "2367480",
            "isin": "US3724601055",
            "primaryidentifier": "GPC",
            "primaryidentifiername": "SYMBOL",
            "identifiertodisplay": "GPC",
            "holdingtype": "Common Stock",
            "holdingtypeabbrev": "COMMON",
            "clientsector": "Consumer Discretionary",
            "clientcountry": "United States",
            "clientregion": "North America",
            "industry": "Distributors",
        },
        {
            "fullpartial": "full",
            "fundid": "SDOG - ALPS Sector Dividend Dogs ETF",
            "fundsymbol": "SDOG",
            "cusip": None,
            "name": "Cash & Other",
            "holdingsymbol": None,
            "weight": 0.0001,
            "shares": 1,
            "marketvalue": 1234.56,
            "asofdate": "2026-07-02T05:00:00",
            "holdingtype": "Cash",
            "holdingtypeabbrev": "CASH",
            "clientcountry": "United States",
        },
    ]
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=json.dumps(payload),
            content_type="application/json",
            url=(
                "https://www.alpsfunds.com/_hcms/api/getData?api_url="
                "https%3A%2F%2Fsecure.alpsinc.com%2FMarketingAPI%2Fapi%2Fv1"
                "%2FHolding%2FSDOG%2FFull"
            ),
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="SDOG", identifiers={})

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.alpsfunds.com/_hcms/api/getData?api_url="
        "https%3A%2F%2Fsecure.alpsinc.com%2FMarketingAPI%2Fapi%2Fv1"
        "%2FHolding%2FSDOG%2FFull"
    )
    assert FakeAsyncClient.requested[0][1]["headers"]["Referer"] == (
        "https://www.alpsfunds.com/exchange-traded-funds/sdog"
    )
    assert result.rows[0].symbol == "GPC"
    assert result.rows[0].name == "Genuine Parts Co."
    assert result.rows[0].cusip == "372460105"
    assert result.rows[0].isin == "US3724601055"
    assert result.rows[0].sedol == "2367480"
    assert result.rows[0].weight == Decimal("0.0255")
    assert result.rows[0].shares == Decimal("259100")
    assert result.rows[0].market_value == Decimal("34348887")
    assert result.rows[0].country == "United States"
    assert result.rows[0].holding_type == "equity"
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.legal_metadata["route_resolution"] == (
        "issuer_public_hubspot_proxy_holdings_json"
    )
    assert result.legal_metadata["composition_date"] == "2026-07-02"


@pytest.mark.asyncio
async def test_federated_hermes_adapter_fetches_daily_holdings_table(monkeypatch):
    adapter = get_holdings_adapter("federated_hermes")
    assert adapter is not None

    product_page = """
    <form id="form-product" action="/us/products/product.do" method="post">
      <input id="fundbasketid" name="fundbasketid" type="hidden" value="31023"/>
      <input id="shareclassid" name="shareclassid" type="hidden" value="18031"/>
      <input id="managedaccountid" name="managedaccountid" type="hidden" value=""/>
      <input id="compositeid" name="compositeid" type="hidden" value=""/>
      <input id="section" name="section" type="hidden" value=""/>
      <input id="tab" name="tab" type="hidden" value=""/>
      <input id="tokenW" name="tokenW" type="hidden" value="token"/>
      <input id="bonyClient" name="bonyClient" type="hidden" value="false"/>
    </form>
    """
    daily_section = """
    <span class="content-heading-3" role="heading">DAILY PORTFOLIO HOLDINGS</span>
    <table>
      <tr>
        <td><a href="/us/products/daily-portfolio-holdings/exchange-traded-funds/total-return-bond-etf.do">View Daily Portfolio Holdings</a></td>
      </tr>
    </table>
    """
    holdings_page = """
    <span class="as-of-date">AS OF <time datetime="2026-07-06">07-06-2026</time></span>
    <table id="daily-portfolio-holdings-table">
      <thead>
        <tr>
          <th>NAME</th>
          <th>SECURITY TYPE</th>
          <th>TICKER</th>
          <th>CUSIP</th>
          <th>ISIN</th>
          <th>SEDOL</th>
          <th>MATURITY /<br/>EXPIRATION DATE</th>
          <th>LONG /<br/>SHORT</th>
          <th>SHARES /<br/>NUMBER OF<br/>CONTRACTS</th>
          <th>PRICE</th>
          <th>NOTIONAL VALUE</th>
          <th>MARKET VALUE /<br/>UNREALIZED<br/>APPRECIATION<br/>OR DEPRECIATION</th>
          <th>MARKET VALUE<br/>WEIGHT (%)</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>US TREASURY N/B</td>
          <td>Bond</td>
          <td>91282CME8</td>
          <td>91282CME8</td>
          <td>US91282CME89</td>
          <td>BS82CME</td>
          <td>06-30-2031</td>
          <td>Long</td>
          <td>10,000</td>
          <td>$99.50</td>
          <td>$995,000.00</td>
          <td>$995,000.00</td>
          <td>1.68000000%</td>
        </tr>
        <tr>
          <td>AUD260715</td>
          <td>Forward</td>
          <td>&#8212;</td>
          <td>AUD260715</td>
          <td>&#8212;</td>
          <td>&#8212;</td>
          <td>07-15-2026</td>
          <td>Short</td>
          <td>0</td>
          <td>$1.445</td>
          <td>$1,038,062.273</td>
          <td>-$33,264.877</td>
          <td>-0.00560485%</td>
        </tr>
      </tbody>
    </table>
    """
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(text="<html>ETF listing</html>", content_type="text/html"),
        FakeResponse(
            text=product_page,
            content_type="text/html",
            url=(
                "https://www.federatedhermes.com/us/products/"
                "exchange-traded-funds/total-return-bond-etf.do"
            ),
        ),
        FakeResponse(text=daily_section, content_type="text/html"),
        FakeResponse(
            text=holdings_page,
            content_type="text/html",
            url=(
                "https://www.federatedhermes.com/us/products/daily-portfolio-holdings/"
                "exchange-traded-funds/total-return-bond-etf.do"
            ),
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="FTRB", identifiers={})

    assert [request[0] for request in FakeAsyncClient.requested] == [
        "https://www.federatedhermes.com/us/products.do?productType=12",
        (
            "https://www.federatedhermes.com/us/products/"
            "exchange-traded-funds/total-return-bond-etf.do"
        ),
        "https://www.federatedhermes.com/us/products/product.do",
        (
            "https://www.federatedhermes.com/us/products/daily-portfolio-holdings/"
            "exchange-traded-funds/total-return-bond-etf.do"
        ),
    ]
    section_request = FakeAsyncClient.requested[2][1]
    assert section_request["data"]["section"] == "section-characteristics-daily-holdings"
    assert section_request["data"]["fundbasketid"] == "31023"
    assert result.rows[0].name == "US TREASURY N/B"
    assert result.rows[0].cusip == "91282CME8"
    assert result.rows[0].isin == "US91282CME89"
    assert result.rows[0].weight == Decimal("0.0168000000")
    assert result.rows[0].shares == Decimal("10000")
    assert result.rows[0].market_value == Decimal("995000.00")
    assert result.rows[0].holding_type == "fixed_income"
    assert result.rows[1].symbol is None
    assert result.rows[1].holding_type == "derivative"
    assert result.rows[1].market_value == Decimal("-33264.877")
    assert result.legal_metadata["route_resolution"] == (
        "issuer_product_page_daily_holdings_table"
    )
    assert result.legal_metadata["composition_date"] == "2026-07-06"


@pytest.mark.asyncio
async def test_dimensional_adapter_discovers_product_page_and_fetches_full_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("dimensional")
    assert adapter is not None

    sitemap_xml = """
    <urlset>
      <url>
        <loc>https://www.dimensional.com/us-en/funds/dfac/us-core-equity-2-etf</loc>
      </url>
    </urlset>
    """
    product_page = """
    <html>
      <script>
        var servicesApiBaseUrl = "https://etf.dimensional.com/public";
        var portfolioName = "US Core Equity 2 ETF";
        var portfolioNumber = 350;
      </script>
    </html>
    """
    details_payload = {
        "data": {
            "lensGroups": [
                {
                    "data": {
                        "lenses": [
                            {
                                "data": {
                                    "slug": "charsEtfTopHoldingsDaily",
                                    "blends": [
                                        {
                                            "data": {
                                                "fullHoldingsCsvUrl": (
                                                    "https://tools-blob.dimensional.com/etf/20260706/DFAC.csv"
                                                )
                                            }
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                }
            ]
        }
    }
    holdings_csv = "\n".join(
        [
            "date,etf_ticker,ticker,description,weight,market_value,identifier,isin,sedol,shares,coupon_rate,maturity_date,principal",
            "2026-07-06,DFAC,AAPL US,APPLE INC.,0.0725,3456.78,037833100,US0378331005,2046251,10,0.0,,3456.78",
            "2026-07-06,DFAC,TREASURY,US TREASURY BILL,0.0125,1000.00,912797AB1,US912797AB12,BKT1234,1000,4.5,2026-12-31,1000.00",
        ]
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(text=sitemap_xml, content_type="application/xml"),
        FakeResponse(text='{"status":"success"}', content_type="application/json"),
        FakeResponse(text='{"status":"success","action":"reload"}', content_type="application/json"),
        FakeResponse(text=product_page, content_type="text/html"),
        FakeResponse(text=json.dumps(details_payload), content_type="application/json"),
        FakeResponse(text=holdings_csv, content_type="text/csv"),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="DFAC", identifiers={})

    assert [request[0] for request in FakeAsyncClient.requested] == [
        "https://www.dimensional.com/us-en/funds/sitemap.xml",
        "https://www.dimensional.com/audience-selector-api/get-splash-page-data-for-country",
        "https://www.dimensional.com/audience-selector-api/select-audience-type",
        "https://www.dimensional.com/us-en/funds/dfac/us-core-equity-2-etf",
        "https://etf.dimensional.com/public/v2/fundcenter/funddetail",
        "https://tools-blob.dimensional.com/etf/20260706/DFAC.csv",
    ]
    api_request = FakeAsyncClient.requested[4][1]
    assert api_request["json"] == {"portfolioNumber": "350"}
    assert api_request["headers"]["x-selected-country"] == "US"
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].exchange == "US"
    assert result.rows[0].cusip == "037833100"
    assert result.rows[0].isin == "US0378331005"
    assert result.rows[0].sedol == "2046251"
    assert result.rows[0].weight == Decimal("0.0725")
    assert result.rows[0].shares == Decimal("10")
    assert result.rows[0].market_value == Decimal("3456.78")
    assert result.rows[1].holding_type == "fixed_income"
    assert result.legal_metadata["route_resolution"] == "dimensional_public_fund_details_api"
    assert result.legal_metadata["composition_date"] == "2026-07-06"


@pytest.mark.asyncio
async def test_capital_group_adapter_fetches_public_daily_holdings_api(monkeypatch):
    adapter = get_holdings_adapter("capital_group")
    assert adapter is not None

    payload = {
        "fundId": "75565",
        "name": "Capital Group Growth ETF",
        "abbreviatedName": "CGGR",
        "dailyHoldings": {
            "asOfDate": "07/09/2026",
            "holdings": [
                {
                    "securityName": "NVIDIA CORP",
                    "ticker": "NVDA",
                    "cusip": "67066G104",
                    "isin": "US67066G1040",
                    "sedol": "2379504",
                    "assetClass": "Equity",
                    "sharesOrPrincipalAmount": "1234",
                    "notionalValue": "0",
                    "marketValue": "196483.44",
                    "percentageOfNetAssets": "6.70",
                },
                {
                    "securityName": "CASH IN U.S. DOLLARS",
                    "ticker": "CMQXX",
                    "assetClass": "Cash & Equivalent",
                    "sharesOrPrincipalAmount": "5000",
                    "marketValue": "5000",
                    "percentageOfNetAssets": "0.17",
                },
                {
                    "securityName": "SPOT FX - EUR/USD",
                    "ticker": None,
                    "assetClass": "Spot FX",
                    "notionalValue": "100000",
                    "marketValue": "-125.50",
                    "percentageOfNetAssets": "-0.01",
                },
            ],
        },
    }
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=json.dumps(payload),
            content_type="application/json",
            url=(
                "https://www.capitalgroup.com/api/investments/investment-service/v1/"
                "etfs/CGGR/holdings?audience=individual&redirect=true"
            ),
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="CGGR", identifiers={})

    request_url, request_kwargs = FakeAsyncClient.requested[0]
    assert request_url.endswith("etfs/CGGR/holdings?audience=individual&redirect=true")
    assert request_kwargs["headers"]["x-app-source"] == "dis-etf-web"
    assert request_kwargs["headers"]["Referer"].endswith("holdings?etf=CGGR")
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].cusip == "67066G104"
    assert result.rows[0].isin == "US67066G1040"
    assert result.rows[0].sedol == "2379504"
    assert result.rows[0].weight == Decimal("0.067")
    assert result.rows[0].shares == Decimal("1234")
    assert result.rows[0].market_value == Decimal("196483.44")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.rows[1].extra_data["source_ticker"] == "CMQXX"
    assert result.rows[2].symbol is None
    assert result.rows[2].row_type == "other"
    assert result.rows[2].holding_type == "forex"
    assert result.legal_metadata["route_resolution"] == "capital_group_daily_holdings_api"
    assert result.legal_metadata["composition_date"] == "2026-07-09"
    assert result.source_identifier == "75565"


@pytest.mark.asyncio
async def test_fidelity_adapter_fetches_complete_creation_basket(monkeypatch):
    adapter = get_holdings_adapter("fidelity")
    assert adapter is not None

    holdings_html = """
    <html><body>
      <h3 class="num-results">Basket Holdings: 3
        <span class="timestamp">AS OF 05/31/2026</span>
      </h3>
      <table class="results-table sortable">
        <thead><tr><th>Symbol</th><th>Company</th><th>Weight</th></tr></thead>
        <tbody>
          <tr><td>NVDA</td><td>NVIDIA Corp</td><td>14.69</td></tr>
          <tr><td>AAPL</td><td>Apple Inc</td><td>10.12</td></tr>
          <tr><td></td><td>Cash</td><td>0.20</td></tr>
        </tbody>
      </table>
    </body></html>
    """
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=holdings_html,
            content_type="text/html",
            url=(
                "https://research2.fidelity.com/fidelity/screeners/etf/etfholdings.asp"
                "?sortBy=Symbol&sortDir=asc&symbol=FBCG&view=Holdings"
            ),
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="FBCG", identifiers={})

    request_url, request_kwargs = FakeAsyncClient.requested[0]
    assert request_url.endswith("sortBy=Symbol&sortDir=asc&symbol=FBCG&view=Holdings")
    assert request_kwargs["headers"]["Referer"] == "https://www.fidelity.com/"
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].name == "NVIDIA Corp"
    assert result.rows[0].weight == Decimal("0.1469")
    assert result.rows[0].currency == "USD"
    assert result.rows[0].extra_data["basket_composition"] is True
    assert result.rows[2].symbol is None
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].holding_type == "cash"
    assert result.legal_metadata["composition_date"] == "2026-05-31"
    assert result.legal_metadata["declared_basket_holding_count"] == 3
    assert result.legal_metadata["portfolio_semantics"] == "daily_creation_redemption_basket"
    assert result.legal_metadata["route_resolution"] == (
        "fidelity_research_complete_basket_holdings"
    )


@pytest.mark.asyncio
async def test_voya_adapter_filters_symbol_daily_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("voya")
    assert adapter is not None

    raw_csv = """Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding
07/10/2026,VMSB,,95002YAE3,WELLS FARGO & COMPANY 6.125 PERPETL 6/15/2175,5011000.0,101.16,5069277.93,1.6318%,310430774.67,6280000.0
07/10/2026,VMSB,,FTCAUSDCT,CITI FUTURES CASH BALANCE - USD,5542664.0,100.00,5542663.64,1.7842%,310430774.67,6280000.0
07/10/2026,VMSB,,CCTMXN,MEXICAN NUEVO PESO,35177352.0,17.62,1996023.16,0.6425%,310430774.67,6280000.0
07/10/2026,VMSB,,7707194,ICE: (CDX.NA.HY.46.V1),-33334937.0,-8.08,2692063.00,0.8666%,310430774.67,6280000.0
07/10/2026,VCOB,,91282CQX2,US TREASURY N/B 4.125 6/30/2031,2120500.0,99.36,2106998.37,0.6783%,310430774.67,6280000.0
"""
    requested = []

    def fake_get(url, **kwargs):
        requested.append((url, kwargs))
        return FakeResponse(
            text=raw_csv,
            content_type="text/csv",
            url="https://vimetfs.com/vmsb/holdings",
        )

    monkeypatch.setattr("app.services.etf_holdings_adapters.requests.get", fake_get)

    result = await adapter.fetch_latest(symbol="VMSB", identifiers={})

    assert requested[0][0] == "https://vimetfs.com/vmsb/holdings"
    assert result.rows[0].cusip == "95002YAE3"
    assert result.rows[0].holding_type == "fixed_income"
    assert result.rows[0].weight == Decimal("0.016318")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.rows[1].extra_data["source_identifier"] == "FTCAUSDCT"
    assert result.rows[2].row_type == "other"
    assert result.rows[2].holding_type == "forex"
    assert result.rows[3].row_type == "other"
    assert result.rows[3].holding_type == "derivative"
    assert len(result.rows) == 4
    assert result.legal_metadata["composition_date"] == "2026-07-10"
    assert result.legal_metadata["route_resolution"] == "voya_symbol_daily_holdings_csv"


@pytest.mark.asyncio
async def test_lazard_adapter_discovers_product_id_and_parses_full_holdings(monkeypatch):
    adapter = get_holdings_adapter("lazard")
    assert adapter is not None

    directory_html = '''
    <a href="/us/en_us/investment-solutions/how-to-invest/108/6244">Japanese ETF</a>
    '''
    payload = [
        {
            "id": "6244",
            "data": {
                "etfg": {
                    "asOfDate": "2026-07-09",
                    "ticker": "JPY",
                    "discountPremiumCurrencyCode": "USD",
                    "constituents": [
                        {
                            "entityName": "MITSUBISHI UFJ FINANCIAL GROUP",
                            "constituentTicker": "8306",
                            "cusip": "633517909",
                            "isin": "JP3902900004",
                            "sedol": "6335171",
                            "weight": "5.41015898",
                            "sharesHeld": "205100",
                            "marketValue": "4312310.39",
                            "securityType": "S",
                            "securityTypeName": "Equity",
                        },
                        {
                            "entityName": "CASH AND OTHER",
                            "weight": "0.12",
                            "marketValue": "95340.51",
                            "securityType": "C",
                            "securityTypeName": "Cash",
                        },
                        {
                            "entityName": "JPY / USD FX FORWARD",
                            "weight": "-0.01",
                            "marketValue": "-1000.00",
                            "securityType": "D",
                            "securityTypeName": "Derivative",
                        },
                    ],
                }
            },
        }
    ]
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=directory_html,
            content_type="text/html",
            url="https://www.lazardassetmanagement.com/us/en_us/investment-solutions/how-to-invest/etfs",
        ),
        FakeResponse(
            text=json.dumps(payload),
            content_type="application/json",
            url="https://lazardassetmanagement.com/api/products?id=6244&type=Fund",
        ),
        FakeResponse(
            text=json.dumps(payload),
            content_type="application/json",
            url="https://lazardassetmanagement.com/api/products?id=6244&type=Fund",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="JPY", identifiers={})

    assert [request[0] for request in FakeAsyncClient.requested] == [
        "https://www.lazardassetmanagement.com/us/en_us/investment-solutions/how-to-invest/etfs",
        "https://lazardassetmanagement.com/api/products?id=6244&type=Fund",
        "https://lazardassetmanagement.com/api/products?id=6244&type=Fund",
    ]
    assert result.source_identifier == "6244"
    assert result.rows[0].symbol == "8306"
    assert result.rows[0].cusip == "633517909"
    assert result.rows[0].isin == "JP3902900004"
    assert result.rows[0].sedol == "6335171"
    assert result.rows[0].weight == Decimal("0.0541015898")
    assert result.rows[0].shares == Decimal("205100")
    assert result.rows[0].market_value == Decimal("4312310.39")
    assert result.rows[0].currency == "USD"
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.rows[2].row_type == "other"
    assert result.rows[2].holding_type == "forex"
    assert result.legal_metadata["composition_date"] == "2026-07-09"
    assert result.legal_metadata["route_resolution"] == "lazard_etf_directory_product_api"


@pytest.mark.asyncio
async def test_rex_adapter_posts_product_form_for_complete_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("rex")
    assert adapter is not None

    raw_csv = """Symbol,Name,Security Identifier,Weighting,Net Value,Shares Held
AAPL,APPLE INC,037833100,7.41%,"$50,290,680.14",159037
FGXXX,FIRST AMERICAN GOVERNMENT OBLIG X,31846V336,0.12%,"$820,000.00",820000
,"AAPL US 07/17/26 C220",,0.08%,"$530,000.00",100
46438R105-TRS-11/05/26-L,ISHARES ETHEREUM TRUST SWAP-L,,200.00%,"$16,551,484.69",1254851
Cash&Other,Cash & Other,,-109.50%,"$-9,062,237.02",-9062237
"""
    requested = []

    def fake_post(url, **kwargs):
        requested.append((url, kwargs))
        return FakeResponse(
            text=raw_csv,
            content_type="text/csv",
            url="https://www.rexshares.com/fepi/",
        )

    monkeypatch.setattr("app.services.etf_holdings_adapters.requests.post", fake_post)

    result = await adapter.fetch_latest(symbol="FEPI", identifiers={})

    request_url, request_kwargs = requested[0]
    assert request_url == "https://www.rexshares.com/fepi/"
    assert request_kwargs["data"] == {"CSV": "Download CSV", "symbol": "FEPI"}
    assert request_kwargs["headers"]["Referer"] == "https://www.rexshares.com/fepi/"
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].cusip == "037833100"
    assert result.rows[0].weight == Decimal("0.0741")
    assert result.rows[1].symbol == "FGXXX"
    assert result.rows[1].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.rows[2].holding_type == "derivative"
    assert result.rows[3].symbol is None
    assert result.rows[3].holding_type == "derivative"
    assert result.rows[4].symbol is None
    assert result.rows[4].row_type == "cash"
    assert result.legal_metadata["route_resolution"] == (
        "rex_product_page_complete_holdings_csv_form"
    )


@pytest.mark.asyncio
async def test_victory_adapter_fetches_public_all_holdings_json(monkeypatch):
    adapter = get_holdings_adapter("victory")
    assert adapter is not None

    product_page = """
    <html>
      <input type="hidden" id="fundID" value="VFLO"/>
      <input type="hidden" id="fundApiKey" value="test-victory-key"/>
    </html>
    """
    payload = [
        {
            "holding_name": "CASH AND CASH EQUIVALENTS",
            "as_of_date": "07/07/2026",
            "market_value": "17358096.390000000000",
            "portfolio_percentage": "0.216199860000",
            "shares": "17358096.390000000000",
        },
        {
            "holding_name": "ADOBE INC",
            "stock_symbol": "ADBE US",
            "as_of_date": "07/07/2026",
            "isin": "US00724F1012",
            "security_type": "COMMON STOCK",
            "market_value": "280661759.820000000000",
            "portfolio_percentage": "3.495719370000",
            "shares": "1287026.000000000000",
        },
    ]
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(text=product_page, content_type="text/html"),
        FakeResponse(text=json.dumps(payload), content_type="application/json"),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(
        symbol="VFLO",
        identifiers={
            "product_url": (
                "https://advisor.vcm.com/products/victoryshares-etfs/"
                "victoryshares-etfs-list/victoryshares-free-cash-flow-etf"
            )
        },
    )

    assert [request[0] for request in FakeAsyncClient.requested] == [
        (
            "https://advisor.vcm.com/products/victoryshares-etfs/"
            "victoryshares-etfs-list/victoryshares-free-cash-flow-etf"
        ),
        "https://investorapi.vcm.com/search/product/VFLO/AllHoldings",
    ]
    assert FakeAsyncClient.requested[1][1]["headers"]["x-api-key"] == "test-victory-key"
    assert result.rows[0].symbol is None
    assert result.rows[0].row_type == "cash"
    assert result.rows[0].holding_type == "cash"
    assert result.rows[0].weight == Decimal("0.0021619986")
    assert result.rows[1].symbol == "ADBE"
    assert result.rows[1].exchange == "US"
    assert result.rows[1].name == "ADOBE INC"
    assert result.rows[1].isin == "US00724F1012"
    assert result.rows[1].weight == Decimal("0.0349571937")
    assert result.rows[1].market_value == Decimal("280661759.820000000000")
    assert result.legal_metadata["route_resolution"] == "issuer_public_product_api_all_holdings"
    assert result.legal_metadata["composition_date"] == "07/07/2026"


@pytest.mark.asyncio
async def test_angel_oak_adapter_filters_combined_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("angel_oak")
    assert adapter is not None

    raw_csv = """Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag
07/07/2026,AOHY,00404AAQ2,00404AAQ2,Acadia Healthcare Co Inc 7.375% 03/15/2033,1030000.00000000,103.479900,1065842.97,0.87%,122675304.94,11110384,444.420000000000,
07/07/2026,AOHY,CASH,,Cash & Cash Equivalents,100.00000000,1.000000,100.00,0.01%,122675304.94,11110384,444.420000000000,Y
07/07/2026,CARY,123456789,123456789,Other Fund Bond,10.00000000,99.000000,990.00,0.50%,1000,100,1,
"""
    requested = []

    def fake_get(url, **kwargs):
        requested.append((url, kwargs))
        return FakeResponse(text=raw_csv, content_type="text/csv", url=url)

    monkeypatch.setattr("app.services.etf_holdings_adapters.requests.get", fake_get)

    result = await adapter.fetch_latest(symbol="AOHY", identifiers={})

    assert requested[0][0] == (
        "https://angeloakcapital.com/secure-gs/Angel_Oak_ETF_Holdings.csv"
    )
    assert result.rows[0].symbol is None
    assert result.rows[0].cusip == "00404AAQ2"
    assert result.rows[0].name == "Acadia Healthcare Co Inc 7.375% 03/15/2033"
    assert result.rows[0].holding_type == "fixed_income"
    assert result.rows[0].weight == Decimal("0.0087")
    assert result.rows[0].shares == Decimal("1030000.00000000")
    assert result.rows[0].market_value == Decimal("1065842.97")
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert len(result.rows) == 2
    assert result.legal_metadata["route_resolution"] == "issuer_combined_account_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-07-07"


def test_doubleline_adapter_parses_pdf_extracted_text():
    adapter = get_holdings_adapter("doubleline")
    assert adapter is not None

    raw_text = """
% of Net
Assets
Security Name
Security Id
Ticker
Coupon
Maturity
Market Value
Quantity
Contract Size
Asset Class
4.68
T 0 5/8 08/15/30
91282CAE1
T
0.625
8/15/2030
34,423,464.98
39,700,000
1
TREASURY
2.93
DoubleLine Emerging
Markets Lo
258620582
DBELX
5.9173
21,585,164.05
2,239,124.66
1
MUTUAL FUND
1.36
CASH
USD
0
10,008,256.70
10,008,253.15
1
CASH
DBND - DoubleLine Opportunistic Core Bond ETF
Holdings as of 7/6/2026
"""

    rows, composition_date = adapter._parse_doubleline_pdf_text(raw_text, symbol="DBND")

    assert composition_date == date(2026, 7, 6)
    assert len(rows) == 3
    assert rows[0].symbol is None
    assert rows[0].name == "T 0 5/8 08/15/30"
    assert rows[0].cusip == "91282CAE1"
    assert rows[0].weight == Decimal("0.0468")
    assert rows[0].market_value == Decimal("34423464.98")
    assert rows[0].shares == Decimal("39700000")
    assert rows[0].holding_type == "fixed_income"
    assert rows[0].extra_data["issuer_ticker"] == "T"
    assert rows[1].symbol == "DBELX"
    assert rows[1].holding_type == "fund"
    assert rows[1].name == "DoubleLine Emerging Markets Lo"
    assert rows[2].row_type == "cash"
    assert rows[2].currency == "USD"
    assert rows[2].symbol is None


def test_tcw_adapter_selects_only_requested_fund_from_combined_holdings_pdf():
    adapter = get_holdings_adapter("tcw")
    assert adapter is not None

    raw_text = """
TCW AAA CLO ETF
SCHEDULE OF INVESTMENTS January 31, 2026 (Unaudited)
FIXED INCOME SECURITIES — 96.3% of Net Assets
AB BSL CLO 6 Ltd. Series 2025-6A, Class A
5.10% (3 mo. USD Term SOFR + 1.430%)(1),(2)    07/20/37   $ 500,000   $ 501,693
AGL CLO 16 Ltd. Series 2021-16A, Class AR
4.62% (3 mo. USD Term SOFR + 0.950%)(1),(2)    01/20/35   5,000,000   5,000,965
\f
TCW Core Plus Bond ETF
SCHEDULE OF INVESTMENTS January 31, 2026 (Unaudited)
OTHER SECURITIES — 1.0% of Net Assets
Other issuer position    01/20/35   $ 10,000   $ 10,001
"""

    rows, composition_date = adapter._parse_pdf_text(raw_text, symbol="ACLO")

    assert composition_date == date(2026, 1, 31)
    assert len(rows) == 2
    assert rows[0].symbol is None
    assert rows[0].name == "AB BSL CLO 6 Ltd. Series 2025-6A, Class A 5.10% (3 mo. USD Term SOFR + 1.430%)(1),(2)"
    assert rows[0].shares == Decimal("500000")
    assert rows[0].market_value == Decimal("501693")
    assert rows[0].holding_type == "fixed_income"
    assert rows[0].extra_data["maturity_date"] == "07/20/37"
    assert rows[0].weight > Decimal("0")
    assert sum(row.weight or Decimal("0") for row in rows) == Decimal("1")


@pytest.mark.asyncio
async def test_exchange_traded_concepts_adapter_parses_only_requested_bluemonte_payload(monkeypatch):
    adapter = get_holdings_adapter("exchange_traded_concepts")
    assert adapter is not None

    raw_html = '''
    <script>
    ql.componentId="bluemonte-bluc-HoldingsComponent-1";
    ql.titleText="Holdings as of 07/09/2026";
    ql.finData=[
      {figi:"BBG000KMT5K3",ticker:"SPYM",quantity:1536158,description:"STATE STREET SPDR PORTFOLIO S&P 500 ETF",market_value:"135,903,898.26",percent_of_nav:"40.08%"},
      {figi:"BBG000HT2CB6",ticker:"VUG",quantity:1342106,description:"VANGUARD GROWTH ETF",market_value:"116,736,379.88",percent_of_nav:"34.43%"},
      {ticker:"TBD",description:"TBD",quantity:0,market_value:"0",percent_of_nav:"0.00%"}
    ];ql.btnLink="";
    other.componentId="bluemonte-bval-HoldingsComponent-1";
    other.finData=[{ticker:"SHOULD_NOT_APPEAR",description:"Other ETF",quantity:1,market_value:"1",percent_of_nav:"100%"}];other.btnLink="";
    </script>
    '''
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_html,
            content_type="text/html",
            url="https://bluemontefunds.com/bluc",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BLUC")

    assert FakeAsyncClient.requested[0][0] == "https://bluemontefunds.com/bluc"
    assert [row.symbol for row in result.rows] == ["SPYM", "VUG"]
    assert result.rows[0].weight == Decimal("0.4008")
    assert result.rows[0].shares == Decimal("1536158")
    assert result.rows[0].market_value == Decimal("135903898.26")
    assert result.rows[0].extra_data["figi"] == "BBG000KMT5K3"
    assert result.legal_metadata["route_resolution"] == (
        "exchange_traded_concepts_bluemonte_fund_page_payload"
    )


@pytest.mark.asyncio
async def test_aot_adapter_parses_issuer_product_page_holdings_and_scales_millions(monkeypatch):
    adapter = get_holdings_adapter("aot")
    assert adapter is not None

    raw_html = '''
    <h2>AOTG</h2>
    <table>
      <tr><th>TICKER</th><th>NAME</th><th>CUSIP</th><th>SHARES</th><th>PRICE</th><th>Market Value ($mm)</th><th>% OF NET ASSETS</th><th>EFFECTIVE_DATE</th></tr>
      <tr><td>NVDA</td><td>NVIDIA Corp</td><td>67066G104</td><td>51,886.00</td><td>202.78</td><td>10.52</td><td>10.11</td><td>07/10/2026</td></tr>
      <tr><td>Cash&Other</td><td>Cash & Other</td><td></td><td>-2,927.16</td><td>1.00</td><td>0.00</td><td>0.00</td><td>07/10/2026</td></tr>
    </table>
    '''
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=raw_html,
            content_type="text/html",
            url="https://aotetf.com/aotg/",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="AOTG")

    assert FakeAsyncClient.requested[0][0] == "https://aotetf.com/aotg/"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].cusip == "67066G104"
    assert result.rows[0].shares == Decimal("51886.00")
    assert result.rows[0].market_value == Decimal("10520000")
    assert result.rows[0].weight == Decimal("0.1011")
    assert result.rows[1].symbol is None
    assert result.rows[1].holding_type == "cash"
    assert result.legal_metadata["composition_date"] == "2026-07-10"
    assert result.legal_metadata["route_resolution"] == (
        "aot_invest_public_product_page_holdings_table"
    )


def test_holdings_adapter_catalog_and_inference_cover_known_routes():
    catalog = holdings_adapter_catalog()
    vaneck = next(item for item in catalog if item["adapter_key"] == "vaneck")

    assert "configured_csv_url" not in {item["adapter_key"] for item in catalog}
    assert vaneck["supports_product_page_discovery"] is True
    assert any("product_url" in item["route_identifiers"] for item in catalog if item["adapter_key"] == "global_x")

    mirae_asset = get_holdings_adapter("mirae_asset")
    assert mirae_asset is not None
    assert type(mirae_asset).__name__ == "MiraeAssetHoldingsAdapter"
    assert mirae_asset.resolve_product_page_url(symbol="QYLD") == "https://www.globalxetfs.com/funds/qyld/"

    ameriprise = get_holdings_adapter("ameriprise")
    assert ameriprise is not None
    assert type(ameriprise).__name__ == "AmeripriseHoldingsAdapter"
    assert ameriprise.resolve_source_url(
        symbol="XCEM",
        identifiers={"cusip": "19762B202"},
    ) == (
        "https://www.columbiathreadneedleus.com/cmg.svc/exportETFholdings"
        "?fundGroupName=ETF&fileType=csv&cusip=19762B202"
    )
    assert ameriprise.probe(symbol="XCEM", name="", identifiers={}).status == "needs_issuer_route"

    rafferty = get_holdings_adapter("rafferty")
    assert rafferty is not None
    assert type(rafferty).__name__ == "RaffertyHoldingsAdapter"
    assert rafferty.resolve_source_url(symbol="COM") == "https://www.direxion.com/holdings/COM.csv"

    exchange_traded_concepts = get_holdings_adapter("exchange_traded_concepts")
    assert exchange_traded_concepts is not None
    assert type(exchange_traded_concepts).__name__ == "ExchangeTradedConceptsHoldingsAdapter"
    assert exchange_traded_concepts.resolve_source_url(symbol="BLUC") == "https://bluemontefunds.com/bluc"

    aot = get_holdings_adapter("aot")
    assert aot is not None
    assert type(aot).__name__ == "AotHoldingsAdapter"
    assert aot.resolve_source_url(symbol="AOTG") == "https://aotetf.com/aotg/"

    sei = get_holdings_adapter("sei")
    assert sei is not None
    assert type(sei).__name__ == "SeiHoldingsAdapter"
    probe = sei.probe(symbol="SEIS", name="SEI Select Small Cap ETF", identifiers={})
    assert probe.status == "ready"
    assert probe.source_url == (
        "https://seietfs.filepoint.live/assets/data/"
        f"SEI_IMU_Tradedate_Holdings_{date.today():%m%d%Y}.txt"
    )

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
    assert adapters["abrdn"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["abrdn"]["support_route_types"]
    assert adapters["clearshares"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["clearshares"]["support_route_types"]
    assert adapters["clough"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["clough"]["support_route_types"]
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
    assert adapters["adaptive_investments"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["adaptive_investments"]["support_route_types"]
    assert adapters["applied_finance"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["applied_finance"]["support_route_types"]
    assert adapters["alliancebernstein"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["alliancebernstein"]["support_route_types"]
    assert adapters["aptus"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["aptus"]["support_route_types"]
    assert adapters["arrow"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["arrow"]["support_route_types"]
    assert adapters["teucrium"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["teucrium"]["support_route_types"]
    assert adapters["us_global_investors"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["us_global_investors"]["support_route_types"]
    assert adapters["burney"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["burney"]["support_route_types"]
    assert adapters["cullen"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["cullen"]["support_route_types"]
    assert adapters["ssc"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["ssc"]["support_route_types"]
    assert adapters["virtus"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["virtus"]["support_route_types"]
    assert adapters["voya"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["voya"]["support_route_types"]
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
    assert adapters["beyond_investing"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["beyond_investing"]["support_route_types"]
    assert adapters["castleark"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["castleark"]["support_route_types"]
    assert adapters["baron"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["baron"]["support_route_types"]
    assert adapters["brandes"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["brandes"]["support_route_types"]
    assert adapters["ocean_park"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["ocean_park"]["support_route_types"]
    assert adapters["grayscale"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["grayscale"]["support_route_types"]
    assert adapters["gmo"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["gmo"]["support_route_types"]
    assert adapters["hashdex"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["hashdex"]["support_route_types"]
    assert adapters["hartford"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["hartford"]["support_route_types"]
    assert adapters["hennessy"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["hennessy"]["support_route_types"]
    assert adapters["cambiar"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["cambiar"]["support_route_types"]
    assert adapters["kurv"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["kurv"]["support_route_types"]
    assert adapters["tapp"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["tapp"]["support_route_types"]
    assert adapters["tuttle"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["tuttle"]["support_route_types"]
    assert adapters["yorkville"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["yorkville"]["support_route_types"]
    assert adapters["true_shares"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["true_shares"]["support_route_types"]
    assert adapters["t_rowe_price"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["t_rowe_price"]["support_route_types"]
    assert adapters["fm_investments"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["fm_investments"]["support_route_types"]
    assert adapters["davis"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["davis"]["support_route_types"]
    assert adapters["deutsche_bank"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["deutsche_bank"]["support_route_types"]
    assert adapters["deepwater"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["deepwater"]["support_route_types"]
    assert adapters["zacks"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["zacks"]["support_route_types"]
    assert adapters["eventide"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["eventide"]["support_route_types"]
    assert adapters["etf_architect"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["etf_architect"]["support_route_types"]
    assert adapters["bahl_gaynor"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["bahl_gaynor"]["support_route_types"]
    assert adapters["coinshares"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["coinshares"]["support_route_types"]
    assert adapters["federated_hermes"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["federated_hermes"][
        "support_route_types"
    ]
    assert adapters["first_eagle"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["first_eagle"]["support_route_types"]
    assert adapters["allspring"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["allspring"]["support_route_types"]
    assert adapters["howard_capital"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["howard_capital"]["support_route_types"]
    assert adapters["timothy_plan"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["timothy_plan"]["support_route_types"]
    assert adapters["spear"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["spear"]["support_route_types"]
    assert adapters["palmer_square"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["palmer_square"]["support_route_types"]
    assert adapters["future_fund"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["future_fund"]["support_route_types"]
    assert adapters["counterpoint"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["counterpoint"]["support_route_types"]
    assert adapters["anfield"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["anfield"]["support_route_types"]
    assert adapters["madison"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["madison"]["support_route_types"]
    assert adapters["brookmont"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["brookmont"]["support_route_types"]
    assert adapters["goldman_sachs"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["goldman_sachs"]["support_route_types"]
    assert adapters["motley_fool"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["motley_fool"]["support_route_types"]
    assert adapters["leuthold"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["leuthold"]["support_route_types"]
    assert adapters["point_bridge"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["point_bridge"]["support_route_types"]
    assert adapters["main_management"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["main_management"]["support_route_types"]
    assert adapters["texas_capital"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["texas_capital"]["support_route_types"]
    assert adapters["dimensional"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["dimensional"]["support_route_types"]
    assert adapters["capital_group"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["capital_group"]["support_route_types"]
    assert adapters["fidelity"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["fidelity"]["support_route_types"]
    assert adapters["lazard"]["live_tested_default_route"] is True
    assert "issuer_native_live_route" in adapters["lazard"]["support_route_types"]
    for adapter_key in [
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
    adapter = get_holdings_adapter("3edge")
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
async def test_allspring_adapter_parses_symbol_total_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("allspring")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "\ufeffTotal holdings as of 6/26/2026",
                    "Portfolio holdings are subject to change and may have changed since the date specified.",
                    "",
                    "SecurityName,Ticker,CUSIP,ISIN,SEDOL,AssetClass,SharesPrincipalAmount,MarketValue,NotionalValue,PercentOfNetAssets",
                    '"Amazon.com, Inc.",AMZN,023135106,US0231351067,2000019,Equity Security,"59,011.00","$13,731,270",,6.04%',
                    "Labcorp Holdings Inc.,LH-US,504922105,US5049221055,BSBK800,Equity Security,\"24,612.00\",\"$6,681,420\",,2.94%",
                    "U.S. Treasuries,,912810UT3,US912810UT33,BT3F9G3,Fixed Income Security,\"9,865,000.00\",\"$9,559,802\",,4.37%",
                    'Net Other Assets,,NETOTHASS,NETOTHASS,NETOTHASS,Other Asset,0.00,"-$1,144,838",,-0.52%',
                    "© 2026 Allspring Global Investments Holdings, LLC. All rights reserved.",
                ]
            ),
            content_type="text/csv",
            url="https://www.allspringglobal.com/globalassets/data/total-holdings/ASLV.csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="ASLV")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.allspringglobal.com/globalassets/data/total-holdings/ASLV.csv"
    )
    assert len(result.rows) == 4
    assert result.rows[0].symbol == "AMZN"
    assert result.rows[0].name == "Amazon.com, Inc."
    assert result.rows[0].cusip == "023135106"
    assert result.rows[0].isin == "US0231351067"
    assert result.rows[0].sedol == "2000019"
    assert result.rows[0].shares == Decimal("59011.00")
    assert result.rows[0].market_value == Decimal("13731270")
    assert result.rows[0].weight == Decimal("0.0604")
    assert result.rows[1].symbol == "LH"
    assert result.rows[1].exchange == "US"
    assert result.rows[2].holding_type == "fixed_income"
    assert result.rows[2].symbol is None
    assert result.rows[2].shares == Decimal("9865000.00")
    assert result.rows[3].row_type == "other"
    assert result.rows[3].cusip is None
    assert result.rows[3].isin is None
    assert result.rows[3].sedol is None
    assert result.rows[3].market_value == Decimal("-1144838")
    assert result.rows[3].weight == Decimal("-0.0052")
    assert result.legal_metadata["source_provider"] == "allspring"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_total_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-26"


@pytest.mark.asyncio
async def test_deutsche_bank_adapter_parses_dws_holdings_json(monkeypatch):
    adapter = get_holdings_adapter("deutsche_bank")
    assert adapter is not None

    payload = {
        "tablesHeadlineText": "Fund holdings",
        "headlineText": "",
        "asOfDate": "",
        "tables": [
            {
                "values": [
                    {
                        "ISIN": {
                            "ISIN_0": {"value": "NVDA.O"},
                            "ISIN_1": {"value": "67066G104"},
                            "ISIN_2": {"value": "US67066G1040"},
                            "ISIN_3": {"value": "2379504"},
                        },
                        "Name": {"value": "NVIDIA Corp"},
                        "Weighting": {"value": "13.55%", "sortValue": 13.54763711},
                        "MarketValue": {"value": "77.33 M", "sortValue": 77326581.31},
                        "NotionalValue": {"value": "--", "sortValue": None},
                        "Quantity": {"value": "386,459", "sortValue": 386459},
                        "Country": {"value": "US"},
                        "IndustryClassName": {"value": "Information Technology"},
                        "AssetClass": {"value": "Equity"},
                    },
                    {
                        "ISIN": {
                            "ISIN_0": {"value": ""},
                            "ISIN_1": {"value": ""},
                            "ISIN_2": {"value": ""},
                            "ISIN_3": {"value": ""},
                        },
                        "Name": {"value": "Cash & Cash Equivalents"},
                        "Weighting": {"value": "0.26%"},
                        "MarketValue": {"value": "1.50 M", "sortValue": 1500000},
                        "Quantity": {"value": "--"},
                        "Country": {"value": "US"},
                        "IndustryClassName": {"value": ""},
                        "AssetClass": {"value": "Cash"},
                    },
                ]
            }
        ],
    }
    requested = []

    def fake_get(url, **kwargs):
        requested.append((url, kwargs))
        return FakeResponse(
            text=json.dumps(payload),
            content_type="application/json",
            url="https://etf.dws.com/api/pdp/en-us/etf/USSG/holdings",
        )

    monkeypatch.setattr("app.services.etf_holdings_adapters.requests.get", fake_get)

    result = await adapter.fetch_latest(symbol="USSG")

    assert requested[0][0] == (
        "https://etf.dws.com/api/pdp/en-us/etf/USSG/holdings"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].exchange == "O"
    assert result.rows[0].name == "NVIDIA Corp"
    assert result.rows[0].cusip == "67066G104"
    assert result.rows[0].isin == "US67066G1040"
    assert result.rows[0].sedol == "2379504"
    assert result.rows[0].weight == Decimal("0.1355")
    assert result.rows[0].shares == Decimal("386459")
    assert result.rows[0].market_value == Decimal("77326581.31")
    assert result.rows[0].currency == "USD"
    assert result.rows[0].extra_data["raw_ticker"] == "NVDA.O"
    assert result.rows[0].extra_data["sector"] == "Information Technology"
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.rows[1].symbol is None
    assert result.rows[1].weight == Decimal("0.0026")
    assert result.rows[1].market_value == Decimal("1500000")
    assert result.legal_metadata["source_provider"] == "deutsche_bank"
    assert result.legal_metadata["route_resolution"] == "issuer_public_pdp_holdings_json"
    assert result.legal_metadata["source_format"] == "json"


@pytest.mark.asyncio
async def test_principal_adapter_parses_symbol_holdings_workbook(monkeypatch):
    adapter = get_holdings_adapter("principal")
    assert adapter is not None

    requested = []
    response = FakeResponse(
        content=_xlsx_workbook(
                [
                    [
                        "As of: 07/01/2026",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "Capital Shares Outstanding:",
                        "33600001",
                    ],
                    [
                        "% of Net Assets",
                        "Market Value",
                        "Security Type",
                        "Description",
                        "Ticker",
                        "CUSIP/Identifier",
                        "ISIN",
                        "SEDOL",
                        "Coupon Rate",
                        "Maturity Date",
                        "Par Value/Quantity/Notional",
                        "Contracts",
                        "Security Price",
                        "Issue Date",
                        "Currency",
                        "Underlying Asset Identifier",
                    ],
                    [
                        "0.013942990371",
                        "32416440",
                        "Equity",
                        "CREDO TECHNOLOGY GROUP HOLDI COMMON STOCK USD.00005",
                        "CRDO",
                        "G25457105",
                        "KYG254571055",
                        "BLD13F2",
                        "",
                        "",
                        "119200",
                        "",
                        "271.95",
                        "",
                        "USD",
                        "",
                    ],
                    [
                        "0.0001",
                        "1000",
                        "Cash",
                        "Cash Collateral",
                        "USD",
                        "",
                        "",
                        "",
                        "",
                        "",
                        "1000",
                        "",
                        "1",
                        "",
                        "USD",
                        "",
                    ],
                ]
            ),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        url="https://api.assetmgmt.principalam.com/public/files?key=PSC.xlsx",
    )

    def fake_get(url, **kwargs):
        requested.append((url, kwargs))
        return response

    monkeypatch.setattr("app.services.etf_holdings_adapters.requests.get", fake_get)

    result = await adapter.fetch_latest(symbol="PSC")

    assert requested[0][0] == (
        "https://api.assetmgmt.principalam.com/public/files?key=PSC.xlsx"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "CRDO"
    assert result.rows[0].name == "CREDO TECHNOLOGY GROUP HOLDI COMMON STOCK USD.00005"
    assert result.rows[0].cusip == "G25457105"
    assert result.rows[0].isin == "KYG254571055"
    assert result.rows[0].sedol == "BLD13F2"
    assert result.rows[0].weight == Decimal("0.013942990371")
    assert result.rows[0].shares == Decimal("119200")
    assert result.rows[0].market_value == Decimal("32416440")
    assert result.rows[0].currency == "USD"
    assert result.rows[0].holding_type == "equity"
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.rows[1].currency == "USD"
    assert result.legal_metadata["source_provider"] == "principal"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_xlsx"
    assert result.legal_metadata["composition_date"] == "2026-07-01"


@pytest.mark.asyncio
async def test_diamond_hill_adapter_parses_symbol_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("diamond_hill")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Diamond Hill Large Cap Concentrated ETF",
                    "Fund Holdings Data as of 06/30/2026",
                    "Name, Security Identifier, Symbol, Net Assets %, Market Price, Shares Held, Market Value, Market Value %",
                    "AON PLC-CLASS A, G0403H108, AON US, 5.856984202900, 331.690000000000, 15379.0000000, 5101060.51, 5.857067299500",
                    "STATE ST GOVT MM, 857492706, , 1.335040930200, 100.000000000000, 1162735.6900000, 1162735.69, 1.335059871300",
                ]
            ),
            content_type="application/octet-stream",
            url=(
                "https://www.diamond-hill.com/sitefiles/live/documents/etfs/holdings/"
                "diamond-hill-DHLX-holdings.csv"
            ),
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="DHLX")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.diamond-hill.com/sitefiles/live/documents/etfs/holdings/"
        "diamond-hill-DHLX-holdings.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "AON"
    assert result.rows[0].exchange == "US"
    assert result.rows[0].name == "AON PLC-CLASS A"
    assert result.rows[0].cusip == "G0403H108"
    assert result.rows[0].weight == Decimal("0.058569842029")
    assert result.rows[0].shares == Decimal("15379.0000000")
    assert result.rows[0].market_value == Decimal("5101060.51")
    assert result.rows[0].extra_data["source_symbol"] == "AON US"
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.legal_metadata["source_provider"] == "diamond_hill"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-30"


@pytest.mark.asyncio
async def test_miller_value_adapter_parses_embedded_holdings_payload(monkeypatch):
    adapter = get_holdings_adapter("miller_value")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<html><script>var a={};'
                'dg.id=261;dg.componentId="milleretf-mvpa-holdings-1";'
                'dg.titleText="Holdings";'
                'dg.finData=['
                '{figi:"BBG002VZ68Y2",ticker:"BLMN",quantity:416324,'
                'description:"BLOOMIN BRANDS INC",market_value:"3,805,201.36",'
                'percent_of_nav:"5.76%"},'
                '{figi:"BBG01RRDN7W5",ticker:"VRMWW",quantity:5720,'
                'description:"VROOM INC WARRANTS",market_value:"3,604.17",'
                'percent_of_nav:"0.01%"}'
                '];dg.btnLink=null;'
                'ns.componentId="milleretf-mvpl-holdings-1";'
                'ns.finData=['
                '{figi:"OTHER",ticker:"MSFT",quantity:1,description:"MICROSOFT CORP",'
                'market_value:"500",percent_of_nav:"1.00%"}'
                '];ns.btnLink=null;</script></html>'
            ),
            content_type="text/html",
            url="https://etf.millervaluefunds.com/mvpa",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="MVPA")

    assert FakeAsyncClient.requested[0][0] == "https://etf.millervaluefunds.com/mvpa"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "BLMN"
    assert result.rows[0].name == "BLOOMIN BRANDS INC"
    assert result.rows[0].weight == Decimal("0.0576")
    assert result.rows[0].shares == Decimal("416324")
    assert result.rows[0].market_value == Decimal("3805201.36")
    assert result.rows[0].extra_data["figi"] == "BBG002VZ68Y2"
    assert result.rows[1].symbol == "VRMWW"
    assert result.rows[1].holding_type == "warrant"
    assert result.legal_metadata["source_provider"] == "miller_value"
    assert result.legal_metadata["route_resolution"] == "issuer_public_fund_page_embedded_holdings"
    assert result.legal_metadata["source_format"] == "nuxt_payload"


@pytest.mark.asyncio
async def test_adaptive_investments_adapter_parses_variable_embedded_holdings_payload(monkeypatch):
    adapter = get_holdings_adapter("adaptive_investments")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<html><script>window.__NUXT__='
                '(function(a,pl,datev,fig1,ticker1,qty1,desc1,mv1,pct1,fig2,ticker2,qty2,desc2,mv2,pct2){'
                'pl.componentId="adpvetf-adpv-holdings-1";'
                'pl.date=datev;'
                'pl.finData=['
                '{figi:fig1,ticker:ticker1,quantity:qty1,description:desc1,market_value:mv1,percent_of_nav:pct1},'
                '{figi:fig2,ticker:ticker2,quantity:qty2,description:desc2,market_value:mv2,percent_of_nav:pct2}'
                '];'
                'pl.created_at="2026-07-07T09:45:44.758Z";'
                'return {}}'
                '(null,{},"07/07/2026","BBG01R388JG1","SNDK","8502",'
                '"SANDISK CORP","14,831,143.86","7.26%","BBG000C0G1D1","INTC","116260",'
                '"INTEL CORP","14,206,972.00","6.96%"));</script></html>'
            ),
            content_type="text/html",
            url="https://adpvetf.com/adpv",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="ADPV")

    assert FakeAsyncClient.requested[0][0] == "https://adpvetf.com/adpv"
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "SNDK"
    assert result.rows[0].name == "SANDISK CORP"
    assert result.rows[0].weight == Decimal("0.0726")
    assert result.rows[0].shares == Decimal("8502")
    assert result.rows[0].market_value == Decimal("14831143.86")
    assert result.rows[0].extra_data["figi"] == "BBG01R388JG1"
    assert result.rows[1].symbol == "INTC"
    assert result.legal_metadata["source_provider"] == "adaptive_investments"
    assert result.legal_metadata["route_resolution"] == "issuer_public_fund_page_embedded_holdings"
    assert result.legal_metadata["source_format"] == "nuxt_payload"
    assert result.legal_metadata["composition_date"] == "2026-07-07"


@pytest.mark.asyncio
async def test_texas_capital_adapter_parses_static_holdings_json(monkeypatch):
    adapter = get_holdings_adapter("texas_capital")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=json.dumps(
                [
                    {
                        "asOfDate_1": "April 29, 2025",
                        "securityDescription_1": "CROWDSTRIKE HO-A",
                        "securityDescriptionLong_1": "Crowdstrike Holdings, Inc.",
                        "securityIdentifier_1": "22788C105",
                        "ticker_1": "CRWD",
                        "symbol_1": "CRWD",
                        "marketValuePercentage_1": "5.63",
                        "sharesHeldOfSecurity_1": "3,587.00",
                        "marketValueOfHolding_1": "1,545,961.13",
                        "segment_1": "COMMON STOCKS",
                        "category_1": "TECHNOLOGY",
                        "country_1": "US",
                        "tradingCurrency_1": "USD",
                    },
                    {
                        "asOfDate_2": "April 29, 2025",
                        "securityDescription_2": "TF FLOAT 07/31/25",
                        "securityIdentifier_2": "91282CHS3",
                        "ticker_2": "",
                        "symbol_2": "",
                        "marketValuePercentage_2": "10.11",
                        "sharesHeldOfSecurity_2": "1,000,000.00",
                        "marketValueOfHolding_2": "1,001,230.00",
                        "segment_2": "U.S. TREASURY",
                        "category_2": "TREASURY",
                        "country_2": "US",
                        "tradingCurrency_2": "USD",
                    },
                    {
                        "asOfDate_3": "April 29, 2025",
                        "securityDescription_3": "US DOLLARS",
                        "securityIdentifier_3": "USD",
                        "ticker_3": "USD",
                        "symbol_3": "USD",
                        "marketValuePercentage_3": "0.25",
                        "sharesHeldOfSecurity_3": "2,500.00",
                        "marketValueOfHolding_3": "2,500.00",
                        "segment_3": "CURRENCY",
                        "category_3": "CURRENCY",
                        "country_3": "US",
                        "tradingCurrency_3": "USD",
                    },
                ]
            ),
            content_type="application/json",
            url=(
                "https://texascapitalbank.com/sites/default/files/documents/"
                "etf-funds-management/txs/data/holdings-data.json"
            ),
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="TXS")

    assert FakeAsyncClient.requested[0][0].endswith("/txs/data/holdings-data.json")
    assert len(result.rows) == 3
    assert result.rows[0].symbol == "CRWD"
    assert result.rows[0].name == "Crowdstrike Holdings, Inc."
    assert result.rows[0].cusip == "22788C105"
    assert result.rows[0].weight == Decimal("0.0563")
    assert result.rows[0].shares == Decimal("3587.00")
    assert result.rows[0].market_value == Decimal("1545961.13")
    assert result.rows[0].holding_type == "equity"
    assert result.rows[1].symbol is None
    assert result.rows[1].holding_type == "fixed_income"
    assert result.rows[1].cusip == "91282CHS3"
    assert result.rows[2].symbol is None
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].holding_type == "cash"
    assert result.legal_metadata["source_provider"] == "texas_capital"
    assert result.legal_metadata["route_resolution"] == "issuer_static_holdings_json"
    assert result.legal_metadata["source_format"] == "json"
    assert result.legal_metadata["composition_date"] == "2025-04-29"


@pytest.mark.asyncio
async def test_spear_adapter_parses_fixed_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("spear")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="\n".join(
                [
                    "Date,Account,StockTicker,CUSIP,SecurityName,Shares,Price,MarketValue,Weightings,NetAssets,SharesOutstanding,CreationUnits,MoneyMarketFlag",
                    "06/29/2026,SPRX,ALAB,04626A103,Astera Labs Inc,61346.00000000,391.740000,24031682.04,9.84%,244106360.000000,4600000,184.000000000000,",
                    "06/29/2026,SPRX,COHR,19247G107,Coherent Corp,56999.00000000,380.560000,21691539.44,8.89%,244106360.000000,4600000,184.000000000000,",
                    "06/29/2026,OTHER,MSFT,594918104,Microsoft Corp,1,500,500,0.01%,244106360.000000,4600000,184.000000000000,",
                ]
            ),
            content_type="text/csv",
            url="https://spear-funds.com/archivos/SpearAdv.40FU.FU_Holdings.csv",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="SPRX")

    assert FakeAsyncClient.requested[0][0] == (
        "https://spear-funds.com/archivos/SpearAdv.40FU.FU_Holdings.csv"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ALAB"
    assert result.rows[0].name == "Astera Labs Inc"
    assert result.rows[0].cusip == "04626A103"
    assert result.rows[0].shares == Decimal("61346.00000000")
    assert result.rows[0].market_value == Decimal("24031682.04")
    assert result.rows[0].weight == Decimal("0.0984")
    assert result.rows[1].symbol == "COHR"
    assert result.rows[1].weight == Decimal("0.0889")
    assert result.legal_metadata["source_provider"] == "spear"
    assert result.legal_metadata["route_resolution"] == "issuer_fixed_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-29"


@pytest.mark.asyncio
async def test_timothy_plan_adapter_parses_holdings_page_table(monkeypatch):
    adapter = get_holdings_adapter("timothy_plan")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text="""
            <html>
              <body>
                <h5>As of 06/29/2026 </h5>
                <table>
                  <thead>
                    <tr>
                      <td>Name</td>
                      <td>Symbol</td>
                      <td>ISIN</td>
                      <td>Shares Held</td>
                      <td>Market Value %</td>
                      <td>Market Value $</td>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>AFLAC INC</td>
                      <td>AFL U</td>
                      <td>US0010551028</td>
                      <td>26,982</td>
                      <td>2.67%</td>
                      <td>$2,653,238</td>
                    </tr>
                    <tr>
                      <td>1261229 B 10. 041532</td>
                      <td></td>
                      <td></td>
                      <td>120,000</td>
                      <td>1.25%</td>
                      <td>$118,450</td>
                    </tr>
                  </tbody>
                </table>
              </body>
            </html>
            """,
            content_type="text/html",
            url="https://timothyplan.com/our-etfs/summary-etf-hds-holdings.php",
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="TPHD")

    assert FakeAsyncClient.requested[0][0] == (
        "https://timothyplan.com/our-etfs/summary-etf-hds-holdings.php"
    )
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "AFL"
    assert result.rows[0].exchange == "U"
    assert result.rows[0].name == "AFLAC INC"
    assert result.rows[0].isin == "US0010551028"
    assert result.rows[0].shares == Decimal("26982")
    assert result.rows[0].weight == Decimal("0.0267")
    assert result.rows[0].market_value == Decimal("2653238")
    assert result.rows[1].symbol is None
    assert result.rows[1].holding_type == "fixed_income"
    assert result.rows[1].shares == Decimal("120000")
    assert result.rows[1].market_value == Decimal("118450")
    assert result.legal_metadata["source_provider"] == "timothy_plan"
    assert result.legal_metadata["route_resolution"] == "issuer_symbol_holdings_page_table"
    assert result.legal_metadata["composition_date"] == "2026-06-29"


@pytest.mark.asyncio
async def test_eventide_adapter_discovers_contentful_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("eventide")
    assert adapter is not None

    csv_url = (
        "https://assets.ctfassets.net/tiol9r5yvqqu/4IYE4vPqDpYNlrGE3NHg7r/"
        "ab89966c9cbd0e16fc60a2561f63adf2/ESUM_etfHoldingsCsv.csv"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<script>{"etfHoldingsCsv":{"url":"//assets.ctfassets.net/tiol9r5yvqqu/'
                '60EaH1oFwn5cSTkB0g5KSV/07376e153b4b7ebc75d13adabccddb05/'
                'ESIM_etfHoldingsCsv.csv"},"other":"ignored"}</script>'
                f'<script>{{"etfHoldingsCsv":{{"url":"{csv_url}"}}}}</script>'
            ),
            content_type="text/html",
            url="https://www.eventideinvestments.com/etfs",
        ),
        FakeResponse(
            text="\n".join(
                [
                    'Product,"Eventide US Market ETF"',
                    "Ticker,ESUM",
                    '"As-of Date",2026-06-26',
                    ",",
                    "Ticker,Description,Shares,Weight",
                    'NVDA,"NVIDIA CORP",59449.0,0.065416',
                    '"HY9H GR","SK HYNIX INC",363.0,0.036176',
                    ',"CASH AND CASH EQUIVALENTS",227746.91,0.007712',
                ]
            ),
            content_type="text/csv",
            url=csv_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="ESUM")

    assert FakeAsyncClient.requested[0][0] == "https://www.eventideinvestments.com/etfs"
    assert FakeAsyncClient.requested[1][0] == csv_url
    assert len(result.rows) == 3
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].name == "NVIDIA CORP"
    assert result.rows[0].weight == Decimal("0.065416")
    assert result.rows[0].shares == Decimal("59449.0")
    assert result.rows[1].symbol == "HY9H"
    assert result.rows[1].exchange == "GR"
    assert result.rows[2].row_type == "cash"
    assert result.rows[2].symbol is None
    assert result.rows[2].holding_type == "cash"
    assert result.legal_metadata["source_provider"] == "eventide"
    assert result.legal_metadata["route_resolution"] == "issuer_listing_page_contentful_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-26"
    assert result.legal_metadata["product_name"] == "Eventide US Market ETF"


@pytest.mark.asyncio
async def test_faith_investor_services_adapter_discovers_next_data_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("faith_investor_services")
    assert adapter is not None

    csv_url = "https://faithinvestorservices.flywheelsites.com/wp-content/uploads/FaithInvSvrs.40KF.Holdings.BRIF_.csv"
    next_data_payload = {
        "props": {
            "pageProps": {
                "data": {
                    "distributionsCopy": {
                        "download": {
                            "url": csv_url,
                            "title": "Download Full Holdings",
                        }
                    }
                }
            }
        }
    }
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                '<script id="__NEXT_DATA__" type="application/json">'
                f"{json.dumps(next_data_payload)}"
                "</script>"
            ),
            content_type="text/html",
            url="https://faithinvestorservices.com/etfs/brif",
        ),
        FakeResponse(
            text="\n".join(
                [
                    "02/03/2025,BRIF,ABBV,00287Y109,AbbVie Inc,17336.000000,183.900000,3188090.40,3.95%,80747095.800000,3122000,312.200000000000,",
                    "02/03/2025,BRIF,FXFXX,31846V328,First American Treasury Obligations Fund 01/01/2040,2800092.150000,100.000000,2800092.15,3.47%,80747095.800000,3122000,312.200000000000,Y",
                    "02/03/2025,OTHER,MSFT,594918104,Microsoft Corp,1,500,500,0.01%,80747095.800000,3122000,312.200000000000,",
                ]
            ),
            content_type="text/csv",
            url=csv_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="BRIF")

    assert FakeAsyncClient.requested[0][0] == "https://faithinvestorservices.com/etfs/brif"
    assert FakeAsyncClient.requested[1][0] == csv_url
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "ABBV"
    assert result.rows[0].name == "AbbVie Inc"
    assert result.rows[0].cusip == "00287Y109"
    assert result.rows[0].weight == Decimal("0.0395")
    assert result.rows[0].shares == Decimal("17336.000000")
    assert result.rows[0].market_value == Decimal("3188090.40")
    assert result.rows[1].symbol is None
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].holding_type == "cash"
    assert result.rows[1].extra_data["money_market_flag"] == "Y"
    assert result.legal_metadata["source_provider"] == "faith_investor_services"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_next_data_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2025-02-03"


@pytest.mark.asyncio
async def test_oneascent_adapter_discovers_ajax_holdings_csv(monkeypatch):
    adapter = get_holdings_adapter("oneascent")
    assert adapter is not None

    holdings_url = (
        "https://oneascent.com/wp-admin/admin-ajax.php?"
        "action=pds_download_holdings_csv&portfolio=1340"
    )
    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=f'<a href="{holdings_url}">Download holdings</a>',
            content_type="text/html",
            url="https://oneascent.com/investment-solutions/public-markets/etfs/oalc/",
        ),
        FakeResponse(
            text="\n".join(
                [
                    '"As Of Date",Ticker,"Security Name",CUSIP,Shares,"Market Value","Weight (%)",Sector,Category,Country',
                    '06/30/2026,"NVDA US","NVIDIA Corporation",67066G104,88450,17697960.5,7.1633,SEMICONDUCTORS,TECHNOLOGY,US',
                    '06/30/2026,"USD CASH","Cash",,100,100,0.0100,CASH,CASH,US',
                ]
            ),
            content_type="text/csv",
            url=holdings_url,
        ),
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="OALC")

    assert FakeAsyncClient.requested[0][0] == (
        "https://oneascent.com/investment-solutions/public-markets/etfs/oalc/"
    )
    assert FakeAsyncClient.requested[1][0] == holdings_url
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "NVDA"
    assert result.rows[0].exchange == "US"
    assert result.rows[0].name == "NVIDIA Corporation"
    assert result.rows[0].cusip == "67066G104"
    assert result.rows[0].weight == Decimal("0.071633")
    assert result.rows[0].shares == Decimal("88450")
    assert result.rows[0].market_value == Decimal("17697960.5")
    assert result.rows[0].country == "US"
    assert result.rows[0].extra_data["Sector"] == "SEMICONDUCTORS"
    assert result.rows[1].row_type == "cash"
    assert result.rows[1].symbol is None
    assert result.rows[1].holding_type == "cash"
    assert result.legal_metadata["source_provider"] == "oneascent"
    assert result.legal_metadata["route_resolution"] == "issuer_product_page_ajax_holdings_csv"
    assert result.legal_metadata["composition_date"] == "2026-06-30"


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
async def test_abrdn_adapter_verifies_physical_metal_product_page(monkeypatch):
    adapter = get_holdings_adapter("abrdn")
    assert adapter is not None

    FakeAsyncClient.requested = []
    FakeAsyncClient.queue = [
        FakeResponse(
            text=(
                "<html><head><title>abrdn funds</title></head>"
                "<body>abrdn Gold ETF Trust (SGOL)</body></html>"
            ),
            content_type="text/html",
            url="https://www.aberdeeninvestments.com/en-us/investor/funds/view-all-funds",
        )
    ]
    monkeypatch.setattr("app.services.etf_holdings_adapters.httpx.AsyncClient", FakeAsyncClient)

    result = await adapter.fetch_latest(symbol="SGOL")

    assert FakeAsyncClient.requested[0][0] == (
        "https://www.aberdeeninvestments.com/en-us/investor/funds/view-all-funds"
    )
    assert result.rows[0].name == "Gold Bullion"
    assert result.rows[0].weight == Decimal("1")
    assert result.rows[0].holding_type == "commodity"
    assert result.rows[0].row_type == "commodity"
    assert result.rows[0].extra_data["commodity"] == "gold"
    assert result.legal_metadata["route_resolution"] == "issuer_fund_centre_physical_commodity_trust"
    assert result.legal_metadata["source_provider"] == "abrdn"


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
