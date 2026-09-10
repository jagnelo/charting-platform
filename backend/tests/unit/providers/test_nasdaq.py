from unittest.mock import MagicMock, patch

import httpx
import pytest

import app.providers.nasdaq as nasdaq
from app.providers.errors import ProviderResponseError
from app.providers.nasdaq import NasdaqProvider, _parse_file


def test_official_nasdaq_file_parser_preserves_venue_and_etf_status():
    text = (
        "|".join(
            [
                "Symbol",
                "Security Name",
                "Market Category",
                "Test Issue",
                "Financial Status",
                "Round Lot Size",
                "ETF",
                "NextShares",
            ]
        )
        + "\n"
    )
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
    text = (
        "|".join(
            [
                "ACT Symbol",
                "Security Name",
                "Exchange",
                "CQS Symbol",
                "ETF",
                "Round Lot Size",
                "Test Issue",
            ]
        )
        + "\n"
    )
    text += "IBM|International Business Machines|N|IBM|N|100|N\n"
    text += "VTI|Vanguard Total Stock|P|VTI|Y|100|N\n"
    rows = _parse_file("otherlisted", text)
    assert rows[0]["exchange_mic"] == "XNYS"
    assert rows[1]["exchange_mic"] == "ARCX"
    assert rows[1]["quoteType"] == "ETF"


def test_discovery_pages_filter_official_directory_and_keep_file_provenance():
    nasdaq._cache = None
    nasdaq._file_cache.clear()
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


def test_directory_poll_uses_conditional_file_validators_and_304_cache():
    nasdaq._cache = None
    nasdaq._file_cache.clear()
    texts = (
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
        "AAPL|Apple|Q|N|N|100|N|N\n",
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue\n"
        "SPY|SPDR|P|SPY|Y|100|N\n",
    )
    first = []
    for text in texts:
        response = MagicMock(status_code=200)
        response.text = text
        response.headers = {"ETag": '"directory-v1"', "Last-Modified": "Tue, 08 Sep 2026 12:00:00 GMT"}
        response.raise_for_status.return_value = None
        first.append(response)
    not_modified = [MagicMock(status_code=304, headers={}), MagicMock(status_code=304, headers={})]
    with patch("app.providers.nasdaq.httpx.get", side_effect=first + not_modified) as get:
        first_rows = nasdaq._directory_rows()
        nasdaq._cache = None
        cached_rows = nasdaq._directory_rows()
    assert [row["symbol"] for row in first_rows] == ["AAPL", "SPY"]
    assert [row["symbol"] for row in cached_rows] == ["AAPL", "SPY"]
    second_headers = get.call_args_list[2].kwargs["headers"]
    assert second_headers["If-None-Match"] == '"directory-v1"'
    assert second_headers["If-Modified-Since"] == "Tue, 08 Sep 2026 12:00:00 GMT"


def test_nasdaq_is_not_a_price_provider():
    from app.providers.registry import list_provider_capabilities

    assert list_provider_capabilities("nasdaq") == ["universe_discovery"]


def test_nasdaq_transport_failure_is_typed():
    nasdaq._cache = None
    nasdaq._file_cache.clear()
    failure = httpx.ConnectError(
        "connection failed",
        request=httpx.Request("GET", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"),
    )
    with patch("app.providers.nasdaq.httpx.get", side_effect=failure):
        with pytest.raises(ProviderResponseError) as exc_info:
            NasdaqProvider().discover_universe_page("EQUITY", 0)
    assert exc_info.value.provider_name == "nasdaq"


def test_nasdaq_malformed_directory_is_typed():
    nasdaq._cache = None
    nasdaq._file_cache.clear()
    response = MagicMock(status_code=200, text="not a Nasdaq directory")
    response.raise_for_status.return_value = None
    with patch("app.providers.nasdaq.httpx.get", return_value=response):
        with pytest.raises(ProviderResponseError) as exc_info:
            NasdaqProvider().discover_universe_page("EQUITY", 0)
    assert exc_info.value.provider_name == "nasdaq"
