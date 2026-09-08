"""Ensure direct provider transports feed the durable runtime measurement."""

from unittest.mock import MagicMock, patch

from app.providers.alpaca import AlpacaProvider
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.coingecko import CoinGeckoProvider
from app.providers.crypto_market_data import CoinbaseProvider, KrakenProvider
from app.providers.edgar import _ensure_ticker_map
from app.providers.finra_otc_directory import _fetch_dapi_rows
from app.providers.massive import MassiveProvider
from app.providers.nasdaq import NasdaqProvider
from app.providers.telemetry import activate, deactivate


def _response(payload, *, text: str | None = None, headers: dict[str, str] | None = None):
    response = MagicMock()
    response.content = b"provider-payload"
    response.headers = headers or {"x-ratelimit-remaining": "1"}
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    response.text = text if text is not None else "payload"
    return response


def _assert_transport(call, expected_requests: int = 1):
    measurement, token = activate()
    try:
        call()
    finally:
        deactivate(token)
    assert measurement.http_requests == expected_requests
    assert measurement.response_bytes == expected_requests * len(b"provider-payload")


def test_direct_provider_adapters_report_http_usage(monkeypatch):
    alpha_response = _response({"bestMatches": []})
    with patch("app.providers.alpha_vantage.settings") as configured, patch(
        "app.providers.alpha_vantage.httpx.get", return_value=alpha_response
    ):
        configured.ALPHA_VANTAGE_API_KEY = "key"
        _assert_transport(lambda: AlphaVantageProvider()._get("SYMBOL_SEARCH"))

    massive_response = _response({"results": []})
    with patch("app.providers.massive.settings") as configured, patch(
        "app.providers.massive.httpx.get", return_value=massive_response
    ):
        configured.MASSIVE_API_KEY = "key"
        configured.MARKETDATA_API_KEY = ""
        _assert_transport(lambda: MassiveProvider()._get({}))

    coingecko_response = _response({"coins": []})
    with patch("app.providers.coingecko.settings") as configured, patch(
        "app.providers.coingecko.httpx.get", return_value=coingecko_response
    ):
        configured.COINGECKO_API_KEY = "key"
        _assert_transport(lambda: CoinGeckoProvider()._get("/search", {"query": "A"}))

    coinbase_response = _response({"price": "1"})
    with patch("app.providers.crypto_market_data.httpx.get", return_value=coinbase_response):
        _assert_transport(lambda: CoinbaseProvider().get_current_price("BTC-USD"))

    kraken_response = _response({"result": {"XXBTZUSD": {"c": ["1"]}}})
    with patch("app.providers.crypto_market_data.httpx.get", return_value=kraken_response):
        _assert_transport(lambda: KrakenProvider().get_current_price("BTC-USD"))

    alpaca_response = _response({"bars": {"AAPL": {"c": "1"}}})
    with patch("app.providers.alpaca.settings") as configured, patch(
        "app.providers.alpaca.httpx.get", return_value=alpaca_response
    ):
        configured.ALPACA_API_KEY = "key"
        configured.ALPACA_SECRET_KEY = "secret"
        configured.ALPACA_DATA_FEED = "iex"
        _assert_transport(lambda: AlpacaProvider().get_current_price("AAPL"))

    edgar_response = _response({"0": {"ticker": "AAPL", "cik_str": 320193, "title": "Apple"}})
    with patch("app.providers.edgar._ticker_map", {}), patch(
        "app.providers.edgar._ticker_map_ts", 0.0
    ), patch("app.providers.edgar.httpx.get", return_value=edgar_response):
        _assert_transport(lambda: _ensure_ticker_map({"User-Agent": "test"}))

    nasdaq_response = _response(
        None,
        text="Symbol|Security Name|ETF|Test Issue|Financial Status|Market Category|Round Lot Size\nAAPL|Apple Inc.|N|N|N|Q|100\n",
    )
    with patch("app.providers.nasdaq._cache", None), patch(
        "app.providers.nasdaq.httpx.get", return_value=nasdaq_response
    ):
        _assert_transport(
            lambda: NasdaqProvider().discover_universe_page("EQUITY", 0), expected_requests=2
        )

    partitions_response = _response({"availablePartitions": [{"partitions": ["2026-09-08"]}]})
    page_response = _response(
        [{"issueSymbolIdentifier": "TEST", "securityDescription": "Test"}],
        headers={"record-total": "1"},
    )
    with patch("app.providers.finra_otc_directory.settings") as configured, patch(
        "app.providers.finra_otc_directory.httpx.get", return_value=partitions_response
    ), patch("app.providers.finra_otc_directory.httpx.post", return_value=page_response):
        configured.NASDAQ_USER_AGENT = "test"
        measurement, token = activate()
        try:
            _fetch_dapi_rows("https://example.test/api")
        finally:
            deactivate(token)
        assert measurement.http_requests == 2
        assert measurement.response_bytes == 2 * len(b"provider-payload")
