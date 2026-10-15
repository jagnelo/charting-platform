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
    text += "DDS|Dillard's, Inc.|F|DDS|N|100|N\n"
    text += "TEX|Nasdaq Texas listing|B|TEX|N|100|N\n"
    text += "NYTX|NYSE Texas listing|M|NYTX|N|100|N\n"
    text += "File Creation Time: 0905202612:00||||||\n"
    rows = _parse_file("otherlisted", text)
    assert rows[0]["exchange_mic"] == "XNYS"
    assert rows[1]["exchange_mic"] == "ARCX"
    assert rows[1]["quoteType"] == "ETF"
    assert rows[2]["exchange_mic"] == "TXSE"
    assert rows[3]["exchange_mic"] == "XBOS"
    assert rows[4]["exchange_mic"] == "XCHI"


@pytest.mark.parametrize(
    "source_name,text",
    [
        (
            "nasdaqlisted",
            "Symbol|Security Name|Market Category\nAAPL|Apple\n"
            "File Creation Time: 0905202612:00||\n",
        ),
        (
            "nasdaqlisted",
            "Symbol|Security Name|Market Category\nAAPL||Q\n"
            "File Creation Time: 0905202612:00|||\n",
        ),
        (
            "otherlisted",
            "ACT Symbol|Security Name|Exchange\nIBM|IBM|N|EXTRA\n"
            "File Creation Time: 0905202612:00||\n",
        ),
        (
            "otherlisted",
            "ACT Symbol|Security Name|Exchange\n|IBM|N\n" "File Creation Time: 0905202612:00||\n",
        ),
    ],
)
def test_nasdaq_parser_rejects_malformed_rows(source_name, text):
    with pytest.raises(ValueError, match="malformed row"):
        _parse_file(source_name, text)


def test_nasdaq_parser_requires_well_formed_terminal_creation_time():
    header = "Symbol|Security Name|Market Category|Test Issue|ETF\n"
    row = "AAPL|Apple Inc.|Q|N|N\n"
    with pytest.raises(ValueError, match="terminal file creation time"):
        _parse_file("nasdaqlisted", header + row)
    with pytest.raises(ValueError, match="invalid file creation time"):
        _parse_file("nasdaqlisted", header + row + "File Creation Time: 1399202612:00||||\n")
    with pytest.raises(ValueError, match="non-terminal file creation time"):
        _parse_file(
            "nasdaqlisted",
            header
            + "File Creation Time: 0905202612:00||||\n"
            + row
            + "File Creation Time: 0905202612:00||||\n",
        )


def test_discovery_pages_filter_official_directory_and_keep_file_provenance():
    nasdaq._cache = None
    nasdaq._file_cache.clear()
    responses = []
    for text in (
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\nAAPL|Apple|Q|N|N|100|N|N\nFile Creation Time: 0905202612:00|||||||\n",
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue\nSPY|SPDR|P|SPY|Y|100|N\nFile Creation Time: 0905202612:00||||||\n",
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
    assert equities["source_file_creation_times"] == {
        "nasdaqlisted": "2026-09-05T12:00:00",
        "otherlisted": "2026-09-05T12:00:00",
    }
    assert provider.supported_discovery_types() == ["EQUITY", "ETF"]
    assert get.call_args_list[0].kwargs["headers"]["User-Agent"]


def test_discovery_returns_entire_file_snapshot_as_one_two_request_operation():
    nasdaq._cache = None
    nasdaq._file_cache.clear()
    rows = [
        {
            "symbol": f"SYM{index:04d}",
            "quoteType": "EQUITY",
            "source_record": {"Symbol": f"SYM{index:04d}"},
        }
        for index in range(1_205)
    ]
    for source_name in nasdaq._FILES:
        nasdaq._file_cache[source_name] = ([], {}, "2026-10-13T12:00:00")

    with patch("app.providers.nasdaq._directory_rows", return_value=rows):
        page = NasdaqProvider().discover_universe_page("EQUITY", 0)

    assert len(page["quotes"]) == 1_205
    assert page["total"] == 1_205
    assert page["complete"] is True
    assert page.get("next_offset") is None
    assert page["quotes"][-1]["source_record"] == {"Symbol": "SYM1204"}


def test_directory_poll_uses_conditional_file_validators_and_304_cache():
    nasdaq._cache = None
    nasdaq._file_cache.clear()
    texts = (
        "Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares\n"
        "AAPL|Apple|Q|N|N|100|N|N\n"
        "File Creation Time: 0908202612:00|||||||\n",
        "ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue\n"
        "SPY|SPDR|P|SPY|Y|100|N\n"
        "File Creation Time: 0908202612:00||||||\n",
    )
    first = []
    for text in texts:
        response = MagicMock(status_code=200)
        response.text = text
        response.headers = {
            "ETag": '"directory-v1"',
            "Last-Modified": "Tue, 08 Sep 2026 12:00:00 GMT",
        }
        response.raise_for_status.return_value = None
        first.append(response)
    not_modified = [MagicMock(status_code=304, headers={}), MagicMock(status_code=304, headers={})]
    with patch("app.providers.nasdaq.httpx.get", side_effect=first + not_modified) as get:
        provider = NasdaqProvider()
        first_page = provider.discover_universe_page("EQUITY", 0)
        nasdaq._cache = None
        cached_page = provider.discover_universe_page("EQUITY", 0)
    assert [row["symbol"] for row in first_page["quotes"]] == ["AAPL"]
    assert [row["symbol"] for row in cached_page["quotes"]] == ["AAPL"]
    assert cached_page["source_file_creation_times"] == first_page["source_file_creation_times"]
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
        request=httpx.Request(
            "GET", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
        ),
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
