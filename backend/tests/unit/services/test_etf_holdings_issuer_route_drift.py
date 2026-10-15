"""Issuer-owned route changes observed in exact-source CI on 2026-10-15."""

import json
from decimal import Decimal

import httpx
import pytest

from app.services.etf_holdings_adapters import get_holdings_adapter

BARON_PAGE = "https://www.baroncapitalgroup.com/product-detail/baron-first-principles-etf-ronb"
BARON_CSV = (
    "https://www.baroncapitalgroup.com/api/product/media/csv/"
    "RONB-HOLDINGS-20261014-0.csv?product_type=etf-downloads&id=reviewed-media-id"
)


@pytest.fixture
def transport(monkeypatch):
    original_client = httpx.AsyncClient
    calls = []
    routes = {}

    def handler(request):
        key = (request.method, str(request.url))
        calls.append(key)
        assert key in routes, f"Unexpected issuer request: {key}"
        status, body = routes[key]
        return httpx.Response(status, text=body, request=request)

    monkeypatch.setattr(
        "app.services.etf_holdings_adapters.httpx.AsyncClient",
        lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return routes, calls


def global_x_props(**changes):
    return {
        "ticker": "QYLD",
        "fileName": "QYLD-holdings-Oct-14-2026.csv",
        "asOfDate": "Oct 14, 2026",
        "downloadFullHoldingsLabel": "Download All Holdings List",
        "columns": [
            {"key": key}
            for key in (
                "netAssets",
                "ticker",
                "name",
                "sedol",
                "marketPrice",
                "shares",
                "marketValue",
            )
        ],
        "holdings": [
            {
                "ticker": "AAPL",
                "name": "APPLE INC",
                "netAssets": "60%",
                "sedol": "2046251",
                "marketPrice": "$$200.00",
                "shares": "30",
                "marketValue": "$$6,000.00",
                "securityType": "Stock - Common",
            },
            {
                "ticker": "NDX US 10/16/26 C20000",
                "name": "NASDAQ 100 OPTION",
                "netAssets": "40%",
                "sedol": "",
                "marketPrice": "$$40.00",
                "shares": "100",
                "marketValue": "$$4,000.00",
                "securityType": "Option",
            },
        ],
        **changes,
    }


def global_x_page(props):
    flight = "ab:" + json.dumps(["$", "section", None, {"children": props}]) + "\n"
    return "<script>self.__next_f.push(" + json.dumps([1, flight]) + ")</script>"


@pytest.mark.asyncio
async def test_baron_uses_current_product_download_and_skips_preamble_and_date_footer(transport):
    routes, calls = transport
    routes[("GET", BARON_PAGE)] = (
        200,
        '<a href="' + BARON_CSV.replace("&", "&amp;") + '">Download Daily Holdings</a>'
        '<script>"https://live-baron-capital-cms.pantheonsite.io/sites/default/files/'
        'etf-downloads/RONB-HOLDINGS-20261012-0.csv"</script>',
    )
    routes[("GET", BARON_CSV)] = (
        200,
        '"Daily Holdings"\n'
        "Holding,Ticker,Weight (%),Market Value ($),Quantity,CUSIP,ISIN,SEDOL,Currency Code\n"
        "TESLA INC,TSLA,99.9%,999,10,88160R101,US88160R1014,B616C79,USD\n"
        "OTHER ASSETS AND LIABILITIES-NET,,0.1%,1,,,,,USD\n"
        '"as of date",2026-10-14\n',
    )
    result = await get_holdings_adapter("baron").fetch_latest(symbol="RONB")
    assert calls == [("GET", BARON_PAGE), ("GET", BARON_CSV)]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "TSLA"
    assert result.rows[0].weight == Decimal("0.999")
    assert result.rows[1].row_type == "cash"
    assert result.legal_metadata["composition_date"] == "2026-10-14"
    assert result.source_url == BARON_CSV
    assert result.legal_metadata["parser_version"] == "baron-csv-v2"
    assert result.legal_metadata["expected_cadence"] == "daily"


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter_key", ["global_x", "mirae_asset"])
async def test_global_x_reads_complete_fund_bound_payload_without_rotating_download_action(
    transport, adapter_key
):
    routes, calls = transport
    page_url = "https://www.globalxetfs.com/funds/qyld/"
    routes[("GET", page_url)] = (200, global_x_page(global_x_props()))
    result = await get_holdings_adapter(adapter_key).fetch_latest(symbol="QYLD")
    assert calls == [("GET", page_url)]
    assert len(result.rows) == 2
    assert result.rows[0].symbol == "AAPL"
    assert result.rows[0].market_value == Decimal("6000")
    assert result.rows[1].holding_type == "derivative"
    assert result.rows[1].symbol is None
    assert result.legal_metadata["composition_date"] == "2026-10-14"
    assert (
        result.legal_metadata["route_resolution"] == "global_x_fund_page_complete_holdings_payload"
    )
    assert result.legal_metadata["entitlement_review_required"] is True
    assert result.legal_metadata["expected_cadence"] == "daily"
    if adapter_key == "mirae_asset":
        assert result.legal_metadata["issuer_parent"] == "mirae_asset_global_investments"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"ticker": "QQQ"},
        {"fileName": "QQQ-holdings-Oct-14-2026.csv"},
        {"asOfDate": ""},
        {"holdings": []},
        {"columns": [{"key": "ticker"}]},
        {"downloadFullHoldingsLabel": ""},
    ],
)
async def test_global_x_rejects_wrong_fund_partial_or_undated_structured_payload(
    transport, changes
):
    routes, _ = transport
    routes[("GET", "https://www.globalxetfs.com/funds/qyld/")] = (
        200,
        global_x_page(global_x_props(**changes)),
    )
    with pytest.raises(ValueError):
        await get_holdings_adapter("global_x").fetch_latest(symbol="QYLD")


@pytest.mark.asyncio
async def test_wedbush_reads_identity_bound_complete_public_json_feed(transport):
    routes, calls = transport
    url = "https://wedbushfunds.com/assets/feeds/feeds.php?fund=TGLR"
    routes[("GET", url)] = (
        200,
        json.dumps(
            {
                "ticker": "TGLR",
                "holdings": {
                    "asof": "2026-10-14",
                    "rows": [
                        ["AAPL", "APPLE INC", "2046251", 30, 6000, 60],
                        ["MSFT", "MICROSOFT CORP", "2588173", 20, 4000, 40],
                    ],
                },
            }
        ),
    )
    result = await get_holdings_adapter("wedbush").fetch_latest(symbol="TGLR")
    assert calls == [("GET", url)]
    assert len(result.rows) == 2
    assert result.rows[0].sedol == "2046251"
    assert result.rows[0].shares == Decimal("30")
    assert result.rows[0].weight == Decimal("0.6")
    assert result.legal_metadata["composition_date"] == "2026-10-14"
    assert result.legal_metadata["route_resolution"] == "wedbush_public_symbol_holdings_feed"
    assert result.legal_metadata["parser_version"] == "wedbush-complete-feed-v1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"ticker": "IVRS", "holdings": {"asof": "2026-10-14", "rows": []}},
        {"ticker": "TGLR", "holdings": {"rows": [["AAPL", "Apple", "2046251", 1, 1, 100]]}},
        {
            "ticker": "TGLR",
            "holdings": {"asof": "2026-10-14", "rows": [["AAPL", "Apple", "2046251", 1, 1, 5]]},
        },
    ],
)
async def test_wedbush_rejects_wrong_fund_undated_or_top_holdings_only_feed(transport, payload):
    routes, _ = transport
    routes[("GET", "https://wedbushfunds.com/assets/feeds/feeds.php?fund=TGLR")] = (
        200,
        json.dumps(payload),
    )
    with pytest.raises(ValueError):
        await get_holdings_adapter("wedbush").fetch_latest(symbol="TGLR")


@pytest.mark.asyncio
async def test_pictet_migrates_only_the_exact_legacy_fund_page_to_canonical_identity(transport):
    routes, calls = transport
    canonical = "https://am.pictet.com/us/en/advisors/pqus"
    routes[("GET", canonical)] = (200, "<title>PQUS - Pictet AI Enhanced US Equity ETF</title>")
    routes[("POST", "https://api-eu.kurtosys.app/fund/getEntity")] = (
        200,
        json.dumps(
            {
                "clientCode": "PQUS",
                "allocations": [
                    {
                        "code": "fund_holdings",
                        "values": [
                            {
                                "security_name": "APPLE INC",
                                "security_ticker": "AAPL",
                                "as_at_date": "2026-10-14",
                                "allocation": 100,
                            }
                        ],
                    }
                ],
            }
        ),
    )
    result = await get_holdings_adapter("pictet").fetch_latest(
        symbol="PQUS", source_url="https://etf.am.pictet.com/pqus/"
    )
    assert calls[0] == ("GET", canonical)
    assert result.source_identifier == "PQUS"
    assert result.rows[0].symbol == "AAPL"
    assert result.legal_metadata["product_page_url"] == canonical


@pytest.mark.asyncio
async def test_global_x_complete_payload_takes_priority_over_stale_csv_link(transport):
    routes, calls = transport
    url = "https://www.globalxetfs.com/funds/qyld/"
    routes[("GET", url)] = (
        200,
        global_x_page(global_x_props()) + '<a href="https://assets.globalxetfs.com/funds/holdings/'
        'qyld_full-holdings_20260930.csv">Old CSV</a>',
    )
    result = await get_holdings_adapter("global_x").fetch_latest(symbol="QYLD")
    assert result.legal_metadata["composition_date"] == "2026-10-14"
    assert calls == [("GET", url)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value", [("netAssets", "NaN"), ("shares", "-"), ("marketValue", "Infinity")]
)
async def test_global_x_rejects_nonfinite_or_missing_numeric_holdings(transport, field, value):
    routes, _ = transport
    props = global_x_props()
    props["holdings"][0][field] = value
    routes[("GET", "https://www.globalxetfs.com/funds/qyld/")] = (200, global_x_page(props))
    with pytest.raises(ValueError, match="numeric"):
        await get_holdings_adapter("global_x").fetch_latest(symbol="QYLD")


@pytest.mark.asyncio
async def test_wedbush_preserves_cusip_instead_of_mislabelling_it_as_sedol(transport):
    routes, _ = transport
    routes[("GET", "https://wedbushfunds.com/assets/feeds/feeds.php?fund=TGLR")] = (
        200,
        json.dumps(
            {
                "ticker": "TGLR",
                "holdings": {
                    "asof": "2026-10-14",
                    "rows": [["DTRXX", "DREYFUS TR & AG CSH MGMT-INS", "261908107", 10, 10, 100]],
                },
            }
        ),
    )
    result = await get_holdings_adapter("wedbush").fetch_latest(symbol="TGLR")
    assert result.rows[0].cusip == "261908107"
    assert result.rows[0].sedol is None
    assert result.rows[0].holding_type == "fund"
    assert result.rows[0].extra_data["source_security_identifier"] == "261908107"


@pytest.mark.asyncio
async def test_wedbush_rejects_host_spoof_before_transport(transport):
    _, calls = transport
    with pytest.raises(ValueError, match="issuer-owned"):
        await get_holdings_adapter("wedbush").fetch_latest(
            symbol="TGLR", source_url="https://wedbushfunds.com.other.example/holdings.csv"
        )
    assert calls == []


@pytest.mark.asyncio
async def test_pictet_never_rewrites_a_sibling_fund_url_to_requested_fund(transport):
    routes, calls = transport
    url = "https://etf.am.pictet.com/pbot/"
    routes[("GET", url)] = (200, '<div data-input-client_code="PBOT"></div>')
    with pytest.raises(ValueError, match="identity"):
        await get_holdings_adapter("pictet").fetch_latest(symbol="PQUS", source_url=url)
    assert calls == [("GET", url)]


@pytest.mark.parametrize("weight", ["5", "5%"])
def test_global_x_legacy_csv_preserves_percent_points_and_percent_sign_units(weight):
    rows, _ = get_holdings_adapter("global_x")._parse_holdings_csv(
        "% of Net Assets,Ticker,Name,SEDOL,Market Price ($),Shares Held,Market Value ($)\n"
        f"{weight},AAPL,APPLE INC,2046251,100,1,100\n",
        symbol="QYLD",
    )
    assert rows[0].weight == Decimal("0.05")
