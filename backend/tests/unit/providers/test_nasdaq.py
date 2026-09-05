from unittest.mock import MagicMock, patch

from app.providers.nasdaq import NasdaqProvider, _parse_file


def test_official_nasdaq_file_parser_preserves_venue_and_etf_status():
    text = "|".join(["Symbol", "Security Name", "Market Category", "Test Issue", "Financial Status", "Round Lot Size", "ETF", "NextShares"]) + "\n"
    text += "AAPL|Apple Inc.|Q|N|N|100|N|N\n"
    text += "SPY|SPDR S&P 500 ETF|G|N|N|100|Y|N\n"
    text += "BANK|Bankrupt Listed|S|N|Q|100|N|N\n"
    text += "BAD|Test|G|Y|N|100|N|N\n"
    text += "File Creation Time: 0905202612:00|||||||\n"
    rows = _parse_file("nasdaqlisted", text)
    assert [row["symbol"] for row in rows] == ["AAPL", "SPY", "BANK"]
    assert rows[1]["quoteType"] == "ETF"
    assert rows[0]["exchange_mic"] == "XNAS"
    assert rows[2]["financial_status"] == "Q"


def test_official_otherlisted_file_maps_exchange_codes():
    text = "|".join(["ACT Symbol", "Security Name", "Exchange", "CQS Symbol", "ETF", "Round Lot Size", "Test Issue"]) + "\n"
    text += "IBM|International Business Machines|N|IBM|N|100|N\n"
    text += "VTI|Vanguard Total Stock|P|VTI|Y|100|N\n"
    rows = _parse_file("otherlisted", text)
    assert rows[0]["exchange_mic"] == "XNYS"
    assert rows[1]["exchange_mic"] == "ARCX"
    assert rows[1]["quoteType"] == "ETF"


def test_discovery_pages_filter_official_directory_and_keep_file_provenance():
    responses = []
    for text in (
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\nAAPL|Apple|Q|N|N|100|N|N\n",
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue\nSPY|SPDR|P|SPY|Y|100|N\n",
    ):
        response = MagicMock()
        response.text = text
        response.raise_for_status.return_value = None
        responses.append(response)
    with patch("app.providers.nasdaq.httpx.get", side_effect=responses) as get:
        provider = NasdaqProvider()
        equities = provider.discover_universe_page("EQUITY", 0)
        # The cache is populated by the first call, so no second network call
        # is expected for the ETF page.
        etfs = provider.discover_universe_page("ETF", 0)
    assert [row["symbol"] for row in equities["quotes"]] == ["AAPL"]
    assert [row["symbol"] for row in etfs["quotes"]] == ["SPY"]
    assert equities["source_files"] == ["nasdaqlisted", "otherlisted"]
    assert provider.supported_discovery_types() == ["EQUITY", "ETF"]
    assert get.call_args_list[0].kwargs["headers"]["User-Agent"]


def test_nasdaq_is_not_a_price_provider():
    from app.providers.registry import list_provider_capabilities

    assert list_provider_capabilities("nasdaq") == ["universe_discovery"]
