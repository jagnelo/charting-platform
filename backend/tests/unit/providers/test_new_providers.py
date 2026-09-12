"""
Unit tests for the five new data providers added in the provider-abstraction feature.
All tests are pure-Python / no-network: HTTP calls are mocked where needed.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.models.instrument_event import EventTimeHint, InstrumentEventType
from app.models.ohlcv import Timeframe
from app.providers.alpaca import (
    AlpacaProvider,
    _is_crypto,
    _to_alpaca_crypto,
    _trading_base_url,
    estimate_latest_ohlcv_request_count,
    estimate_ohlcv_request_count,
)
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.binance import (
    BinanceProvider,
    _from_binance,
    _to_binance,
    estimate_latest_ohlcv_request_weight,
    estimate_ohlcv_request_weight,
)
from app.providers.coingecko import CoinGeckoProvider
from app.providers.crypto_market_data import (
    CoinbaseProvider,
    KrakenProvider,
    estimate_coinbase_latest_ohlcv_request_count,
    estimate_coinbase_ohlcv_request_count,
    estimate_kraken_latest_ohlcv_request_count,
    estimate_kraken_ohlcv_request_count,
)
from app.providers.edgar import EdgarProvider, _ensure_ticker_map
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from app.providers.fred import FREDProvider, fred_series_for, is_fred_symbol
from app.providers.massive import MassiveProvider
from app.providers.optional_market_data import (
    TwelveDataProvider,
    estimate_twelve_data_latest_ohlcv_request_count,
    estimate_twelve_data_ohlcv_request_count,
)
from app.providers.registry import (
    get_discovery_provider,
    get_event_provider,
    get_metadata_provider,
    get_price_history_provider,
    get_search_provider,
    list_provider_capabilities,
    provider_supports_adjustment,
)

# ── Registry capability detection ────────────────────────────────────────────


class TestRegistryCapabilities:
    def test_provider_adjustment_contract_is_explicit(self):
        assert provider_supports_adjustment("alpha_vantage", True) is False
        assert provider_supports_adjustment("ibkr", True) is False
        assert provider_supports_adjustment("tiingo", True) is False
        assert provider_supports_adjustment("twelve_data", True) is False
        assert provider_supports_adjustment("binance", True) is False
        assert provider_supports_adjustment("alpaca", True) is True
        assert provider_supports_adjustment("alpha_vantage", False) is True
        assert provider_supports_adjustment("alpha_vantage", None) is True

    def test_alpaca_capabilities(self):
        caps = set(list_provider_capabilities("alpaca"))
        assert "price_history" in caps
        assert "adjusted_price_history" in caps
        assert "latest_price" in caps
        assert "instrument_events" in caps
        assert "universe_discovery" in caps
        assert "option_chain" not in caps
        assert "instrument_metadata" not in caps

    def test_fred_capabilities(self):
        caps = set(list_provider_capabilities("fred"))
        assert "price_history" in caps
        assert "latest_price" in caps
        assert "universe_discovery" not in caps
        assert "instrument_metadata" not in caps

    def test_binance_capabilities(self):
        caps = set(list_provider_capabilities("binance"))
        assert "price_history" in caps
        assert "adjusted_price_history" not in caps
        assert "latest_price" in caps
        assert "universe_discovery" in caps
        assert "instrument_metadata" not in caps
        assert "option_chain" not in caps

    def test_coingecko_capabilities(self):
        caps = set(list_provider_capabilities("coingecko"))
        assert "instrument_search" in caps
        assert "instrument_metadata" in caps
        assert "universe_discovery" in caps
        assert "price_history" not in caps
        assert "option_chain" not in caps

    def test_edgar_capabilities(self):
        caps = set(list_provider_capabilities("edgar"))
        assert "instrument_search" in caps
        assert "instrument_metadata" in caps
        assert "instrument_events" in caps
        assert "market_events" in caps
        assert "price_history" not in caps
        assert "universe_discovery" in caps

    def test_alpaca_is_price_history_provider(self):
        provider = get_price_history_provider("alpaca")
        assert provider.name == "alpaca"

    def test_alpaca_is_event_provider(self):
        provider = get_event_provider("alpaca")
        assert provider.name == "alpaca"

    def test_alpaca_is_discovery_provider(self):
        provider = get_discovery_provider("alpaca")
        assert provider.name == "alpaca"

    def test_fred_is_price_history_provider(self):
        provider = get_price_history_provider("fred")
        assert provider.name == "fred"

    def test_binance_is_price_history_provider(self):
        provider = get_price_history_provider("binance")
        assert provider.name == "binance"

    def test_coingecko_is_search_provider(self):
        provider = get_search_provider("coingecko")
        assert provider.name == "coingecko"

    def test_coingecko_is_metadata_provider(self):
        provider = get_metadata_provider("coingecko")
        assert provider.name == "coingecko"

    def test_edgar_is_metadata_provider(self):
        provider = get_metadata_provider("edgar")
        assert provider.name == "edgar"

    def test_edgar_is_event_provider(self):
        provider = get_event_provider("edgar")
        assert provider.name == "edgar"

    def test_massive_reference_capabilities(self):
        caps = set(list_provider_capabilities("massive"))
        assert caps == {"instrument_search", "universe_discovery", "market_events"}
        assert get_search_provider("massive").name == "massive"
        assert get_discovery_provider("massive").name == "massive"

    def test_alpha_vantage_capabilities(self):
        caps = set(list_provider_capabilities("alpha_vantage"))
        assert {
            "instrument_search",
            "price_history",
            "latest_price",
            "universe_discovery",
            "market_events",
            "earnings",
        } <= caps
        assert get_event_provider("alpha_vantage").name == "alpha_vantage"


# ── Alpaca symbol helpers ─────────────────────────────────────────────────────


class TestAlpacaSymbolHelpers:
    @pytest.mark.parametrize(
        "symbol,expected",
        [
            ("BTC-USD", True),
            ("ETH-USD", True),
            ("BTC/USD", True),
            ("ETH-BTC", True),
            ("AAPL", False),
            ("MSFT", False),
            ("SPY", False),
            ("BRK-A", False),  # equity with hyphen — quote side is "A", not in crypto list
        ],
    )
    def test_is_crypto(self, symbol, expected):
        assert _is_crypto(symbol) == expected

    @pytest.mark.parametrize(
        "symbol,expected",
        [
            ("BTC-USD", "BTC/USD"),
            ("ETH-USD", "ETH/USD"),
            ("SOL-USD", "SOL/USD"),
            ("BTCUSDT", "BTCUSDT"),  # no hyphen — passthrough
        ],
    )
    def test_to_alpaca_crypto(self, symbol, expected):
        assert _to_alpaca_crypto(symbol) == expected


# ── Alpaca credential warning ─────────────────────────────────────────────────


class TestAlpacaCredentialWarning:
    def test_ok_returns_false_and_warns_when_keys_missing(self, caplog):
        provider = AlpacaProvider()
        with patch("app.providers.alpaca.settings") as mock_settings:
            mock_settings.ALPACA_API_KEY = ""
            mock_settings.ALPACA_SECRET_KEY = ""
            with caplog.at_level(logging.WARNING, logger="app.providers.alpaca"):
                result = provider._ok()
        assert result is False
        assert "ALPACA_API_KEY" in caplog.text

    def test_ok_returns_true_when_keys_present(self):
        provider = AlpacaProvider()
        with patch("app.providers.alpaca.settings") as mock_settings:
            mock_settings.ALPACA_API_KEY = "key"
            mock_settings.ALPACA_SECRET_KEY = "secret"
            assert provider._ok() is True

    def test_fetch_ohlcv_raises_when_no_credentials(self):
        provider = AlpacaProvider()
        with patch("app.providers.alpaca.settings") as mock_settings:
            mock_settings.ALPACA_API_KEY = ""
            mock_settings.ALPACA_SECRET_KEY = ""
            with pytest.raises(ProviderNotConfiguredError):
                provider.fetch_ohlcv(
                    "AAPL",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 2, 1, tzinfo=UTC),
                )

    def test_discover_universe_page_raises_when_no_credentials(self):
        provider = AlpacaProvider()
        with patch("app.providers.alpaca.settings") as mock_settings:
            mock_settings.ALPACA_API_KEY = ""
            mock_settings.ALPACA_SECRET_KEY = ""
            with pytest.raises(ProviderNotConfiguredError):
                provider.discover_universe_page("EQUITY", 0)

    def test_assets_use_paper_trading_host_for_paper_credentials(self):
        response = MagicMock()
        response.json.return_value = [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "exchange": "NASDAQ",
                "tradable": True,
            }
        ]
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpaca.settings") as configured,
            patch("app.providers.alpaca._asset_cache", {}),
            patch("app.providers.alpaca.httpx.get", return_value=response) as get,
        ):
            configured.ALPACA_API_KEY = "key"
            configured.ALPACA_SECRET_KEY = "secret"
            configured.ALPACA_TRADING_BASE_URL = "https://paper-api.alpaca.markets/v2"
            page = AlpacaProvider().discover_universe_page("EQUITY", 0)
        assert page["quotes"][0]["symbol"] == "AAPL"
        assert get.call_args.args[0] == "https://paper-api.alpaca.markets/v2/assets"

    def test_invalid_assets_host_fails_closed(self):
        with patch("app.providers.alpaca.settings") as configured:
            configured.ALPACA_TRADING_BASE_URL = "https://attacker.invalid/v2"
            with pytest.raises(ProviderNotConfiguredError):
                _trading_base_url()

    def test_http_status_failures_are_not_converted_to_empty_history(self):
        provider = AlpacaProvider()
        response = httpx.Response(
            429,
            headers={"retry-after": "2"},
            request=httpx.Request("GET", "https://data.alpaca.markets/v2/stocks/bars"),
        )
        with (
            patch("app.providers.alpaca.settings") as configured,
            patch("app.providers.alpaca.httpx.get", return_value=response),
        ):
            configured.ALPACA_API_KEY = "key"
            configured.ALPACA_SECRET_KEY = "secret"
            configured.ALPACA_DATA_FEED = "iex"
            with pytest.raises(httpx.HTTPStatusError):
                provider.fetch_ohlcv(
                    "AAPL",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 2, 1, tzinfo=UTC),
                )

    def test_transport_failures_are_typed_instead_of_empty_history(self):
        provider = AlpacaProvider()
        failure = httpx.ConnectError(
            "connection failed",
            request=httpx.Request("GET", "https://data.alpaca.markets/v2/stocks/bars"),
        )
        with (
            patch("app.providers.alpaca.settings") as configured,
            patch("app.providers.alpaca.httpx.get", side_effect=failure),
        ):
            configured.ALPACA_API_KEY = "key"
            configured.ALPACA_SECRET_KEY = "secret"
            configured.ALPACA_DATA_FEED = "iex"
            with pytest.raises(ProviderResponseError) as exc_info:
                provider.fetch_ohlcv(
                    "AAPL",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 2, 1, tzinfo=UTC),
                )
        assert exc_info.value.provider_name == "alpaca"

    def test_invalid_json_is_typed_instead_of_empty_history(self):
        provider = AlpacaProvider()
        response = MagicMock()
        response.json.side_effect = ValueError("malformed payload")
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpaca.settings") as configured,
            patch("app.providers.alpaca.httpx.get", return_value=response),
        ):
            configured.ALPACA_API_KEY = "key"
            configured.ALPACA_SECRET_KEY = "secret"
            configured.ALPACA_DATA_FEED = "iex"
            with pytest.raises(ProviderResponseError) as exc_info:
                provider.fetch_ohlcv(
                    "AAPL",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 2, 1, tzinfo=UTC),
                )
        assert exc_info.value.provider_name == "alpaca"


# ── Alpaca OHLCV bar parsing ──────────────────────────────────────────────────


class TestAlpacaOHLCVParsing:
    def test_history_request_count_covers_all_bar_pages(self):
        start = datetime(2020, 1, 1, tzinfo=UTC)
        end = start + timedelta(days=2501)
        assert estimate_ohlcv_request_count(Timeframe.D1, start, end) == 3

    def test_latest_request_count_covers_provider_lookback(self):
        assert estimate_latest_ohlcv_request_count(Timeframe.M1, 1000) == 3

    def test_fetch_ohlcv_parses_stock_bars(self):
        provider = AlpacaProvider()
        fake_response = {
            "bars": {
                "AAPL": [
                    {
                        "t": "2024-01-02T05:00:00Z",
                        "o": 185.0,
                        "h": 187.0,
                        "l": 184.0,
                        "c": 186.0,
                        "v": 50000000,
                        "vw": 185.5,
                    },
                    {
                        "t": "2024-01-03T05:00:00Z",
                        "o": 186.0,
                        "h": 188.0,
                        "l": 185.0,
                        "c": 187.0,
                        "v": 45000000,
                        "vw": 186.5,
                    },
                ]
            },
            "next_page_token": None,
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status.return_value = None

        with (
            patch("app.providers.alpaca.settings") as mock_settings,
            patch("app.providers.alpaca.httpx.get", return_value=mock_resp),
        ):
            mock_settings.ALPACA_API_KEY = "key"
            mock_settings.ALPACA_SECRET_KEY = "secret"
            mock_settings.ALPACA_DATA_FEED = "iex"
            bars = provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 5, tzinfo=UTC),
            )

        assert len(bars) == 2
        assert float(bars[0].open) == 185.0
        assert float(bars[0].close) == 186.0
        assert float(bars[1].open) == 186.0
        assert bars[0].adjustment_basis == "provider_adjusted"
        assert bars[0].adjustment_version == "alpaca-all"
        assert bars[0].provenance["provider"] == "alpaca"

    @pytest.mark.parametrize(
        "rows",
        [
            [{"t": "2024-01-02T05:00:00Z", "o": 185.0}],
            [{"t": "2024-01-02T05:00:00Z", "o": 185.0, "h": 187.0, "l": 184.0, "c": "NaN"}],
            ["not-a-bar"],
        ],
    )
    def test_fetch_ohlcv_rejects_malformed_or_non_finite_rows(self, rows):
        provider = AlpacaProvider()
        response = MagicMock()
        response.json.return_value = {"bars": {"AAPL": rows}, "next_page_token": None}
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpaca.settings") as configured,
            patch("app.providers.alpaca.httpx.get", return_value=response),
        ):
            configured.ALPACA_API_KEY = "key"
            configured.ALPACA_SECRET_KEY = "secret"
            configured.ALPACA_DATA_FEED = "iex"
            with pytest.raises(ProviderResponseError, match="Alpaca returned"):
                provider.fetch_ohlcv(
                    "AAPL",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 1, 5, tzinfo=UTC),
                )

    def test_fetch_ohlcv_rejects_invalid_pagination_token(self):
        provider = AlpacaProvider()
        response = MagicMock()
        response.json.return_value = {
            "bars": {"AAPL": []},
            "next_page_token": {"unexpected": "object"},
        }
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpaca.settings") as configured,
            patch("app.providers.alpaca.httpx.get", return_value=response),
        ):
            configured.ALPACA_API_KEY = "key"
            configured.ALPACA_SECRET_KEY = "secret"
            configured.ALPACA_DATA_FEED = "iex"
            with pytest.raises(ProviderResponseError, match="pagination token"):
                provider.fetch_ohlcv(
                    "AAPL",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 1, 5, tzinfo=UTC),
                )

    @pytest.mark.parametrize(
        "actions,match",
        [
            ({"forward_splits": "not-an-array"}, "invalid forward_splits"),
            ({"reverse_splits": [{"ex_date": "not-a-date"}]}, "reverse split"),
            ({"cash_dividends": [{"ex_date": "2024-01-02", "rate": "NaN"}]}, "cash-dividend"),
            ({"cash_dividends": [{"rate": "1"}]}, "cash dividend without"),
        ],
    )
    def test_corporate_actions_reject_malformed_collections_and_rows(self, actions, match):
        response = MagicMock()
        response.json.return_value = {"corporate_actions": actions}
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpaca.settings") as configured,
            patch("app.providers.alpaca.httpx.get", return_value=response),
        ):
            configured.ALPACA_API_KEY = "key"
            configured.ALPACA_SECRET_KEY = "secret"
            with pytest.raises(ProviderResponseError, match=match):
                AlpacaProvider().fetch_instrument_events("AAPL")

    def test_corporate_actions_use_current_v1_endpoint_and_follow_page_tokens(self):
        responses = []
        for payload in (
            {
                "corporate_actions": {
                    "cash_dividends": [
                        {
                            "id": "div-1",
                            "ex_date": "2025-01-02",
                            "payable_date": "2025-01-10",
                            "rate": 0.25,
                        }
                    ]
                },
                "next_page_token": "next-page",
            },
            {
                "corporate_actions": {
                    "forward_splits": [
                        {
                            "id": "split-1",
                            "ex_date": "2025-02-03",
                            "new_rate": 2,
                            "old_rate": 1,
                        }
                    ]
                },
                "next_page_token": None,
            },
        ):
            response = MagicMock()
            response.json.return_value = payload
            response.raise_for_status.return_value = None
            responses.append(response)
        with (
            patch("app.providers.alpaca.settings") as configured,
            patch("app.providers.alpaca.httpx.get", side_effect=responses) as get,
        ):
            configured.ALPACA_API_KEY = "key"
            configured.ALPACA_SECRET_KEY = "secret"
            configured.ALPACA_CORPORATE_ACTIONS_MAX_PAGES = 0
            events = AlpacaProvider().fetch_instrument_events("AAPL")

        assert [event.event_type.value for event in events] == [
            "ex_dividend",
            "dividend",
            "split",
        ]
        assert events[1].event_time.date() == date(2025, 1, 10)
        assert get.call_count == 2
        assert get.call_args_list[0].args[0] == "https://data.alpaca.markets/v1/corporate-actions"
        assert get.call_args_list[0].kwargs["params"]["symbols"] == "AAPL"
        assert get.call_args_list[0].kwargs["params"]["types"] == (
            "forward_split,reverse_split,cash_dividend"
        )
        assert get.call_args_list[0].kwargs["params"]["limit"] == 1000
        assert get.call_args_list[1].kwargs["params"]["page_token"] == "next-page"

    def test_corporate_actions_positive_page_bound_fails_before_unreserved_page(self):
        response = MagicMock()
        response.json.return_value = {
            "corporate_actions": {"cash_dividends": []},
            "next_page_token": "next-page",
        }
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpaca.settings") as configured,
            patch("app.providers.alpaca.httpx.get", return_value=response) as get,
        ):
            configured.ALPACA_API_KEY = "key"
            configured.ALPACA_SECRET_KEY = "secret"
            configured.ALPACA_CORPORATE_ACTIONS_MAX_PAGES = 1
            with pytest.raises(ProviderResponseError, match="page bound"):
                AlpacaProvider().fetch_instrument_events("AAPL")

        assert get.call_count == 1


# ── Binance symbol helpers ────────────────────────────────────────────────────


class TestBinanceSymbolHelpers:
    @pytest.mark.parametrize(
        "symbol,expected",
        [
            ("BTC-USD", "BTCUSDT"),
            ("ETH-USD", "ETHUSDT"),
            ("SOL-USD", "SOLUSDT"),
        ],
    )
    def test_to_binance(self, symbol, expected):
        assert _to_binance(symbol) == expected

    @pytest.mark.parametrize("symbol", ["AAPL", "BTC-ETH", "BTCUSD"])
    def test_to_binance_returns_none_for_non_usd_pairs(self, symbol):
        assert _to_binance(symbol) is None

    @pytest.mark.parametrize(
        "binance_sym,expected",
        [
            ("BTCUSDT", "BTC-USD"),
            ("ETHUSDT", "ETH-USD"),
            ("SOLUSDT", "SOL-USD"),
        ],
    )
    def test_from_binance(self, binance_sym, expected):
        assert _from_binance(binance_sym) == expected

    def test_fetch_ohlcv_returns_empty_for_non_crypto(self):
        provider = BinanceProvider()
        bars = provider.fetch_ohlcv(
            "AAPL",
            Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 5, tzinfo=UTC),
            adjusted=False,
        )
        assert bars == []

    def test_discovery_returns_empty_for_non_crypto_type(self):
        provider = BinanceProvider()
        result = provider.discover_universe_page("EQUITY", 0)
        assert result == {"total": 0, "quotes": []}

    def test_supported_discovery_types(self):
        assert BinanceProvider().supported_discovery_types() == ["CRYPTOCURRENCY"]

    def test_adjusted_history_is_rejected_before_transport(self):
        provider = BinanceProvider()
        with patch("app.providers.binance.httpx.get") as get:
            with pytest.raises(ProviderResponseError, match="candles are raw"):
                provider.fetch_ohlcv(
                    "BTC-USD",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 1, 2, tzinfo=UTC),
                    adjusted=True,
                )
        get.assert_not_called()


# ── Binance OHLCV bar parsing ─────────────────────────────────────────────────


class TestBinanceOHLCVParsing:
    def test_fetch_ohlcv_parses_klines(self):
        provider = BinanceProvider()
        # klines format: [open_time_ms, open, high, low, close, volume, close_time_ms, ...]
        start_ms = int(datetime(2024, 1, 2, tzinfo=UTC).timestamp() * 1000)
        fake_klines = [
            [start_ms, "42000.0", "43000.0", "41000.0", "42500.0", "1000.5", start_ms + 86399999],
        ]
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_klines
        mock_resp.raise_for_status.return_value = None

        with patch("app.providers.binance.httpx.get", return_value=mock_resp):
            bars = provider.fetch_ohlcv(
                "BTC-USD",
                Timeframe.D1,
                datetime(2024, 1, 2, tzinfo=UTC),
                datetime(2024, 1, 3, tzinfo=UTC),
                adjusted=False,
            )

        assert len(bars) == 1
        assert float(bars[0].open) == 42000.0
        assert float(bars[0].close) == 42500.0
        assert bars[0].adjustment_basis == "raw"
        assert bars[0].adjustment_version == "provider-native"
        assert bars[0].provenance["provider"] == "binance"

    def test_transport_failure_is_typed(self):
        failure = httpx.ConnectError(
            "connection failed",
            request=httpx.Request("GET", "https://api.binance.com/api/v3/klines"),
        )
        with patch("app.providers.binance.httpx.get", side_effect=failure):
            with pytest.raises(ProviderResponseError) as exc_info:
                BinanceProvider().fetch_ohlcv(
                    "BTC-USD",
                    Timeframe.D1,
                    datetime(2024, 1, 2, tzinfo=UTC),
                    datetime(2024, 1, 3, tzinfo=UTC),
                    adjusted=False,
                )
        assert exc_info.value.provider_name == "binance"

    def test_malformed_klines_payload_is_typed(self):
        mock_resp = MagicMock()
        mock_resp.json.side_effect = ValueError("not json")
        mock_resp.raise_for_status.return_value = None
        with patch("app.providers.binance.httpx.get", return_value=mock_resp):
            with pytest.raises(ProviderResponseError) as exc_info:
                BinanceProvider().fetch_ohlcv(
                    "BTC-USD",
                    Timeframe.D1,
                    datetime(2024, 1, 2, tzinfo=UTC),
                    datetime(2024, 1, 3, tzinfo=UTC),
                    adjusted=False,
                )
        assert exc_info.value.provider_name == "binance"

    @pytest.mark.parametrize(
        "row",
        [
            {"open_time": 1704153600000},
            [1704153600000, "1", "2"],
            [1704153600000, "NaN", "2", "1", "1.5", "10"],
        ],
    )
    def test_malformed_klines_rows_are_typed(self, row):
        response = MagicMock()
        response.json.return_value = [row]
        response.raise_for_status.return_value = None
        with patch("app.providers.binance.httpx.get", return_value=response):
            with pytest.raises(ProviderResponseError) as exc_info:
                BinanceProvider().fetch_ohlcv(
                    "BTC-USD",
                    Timeframe.D1,
                    datetime(2024, 1, 2, tzinfo=UTC),
                    datetime(2024, 1, 3, tzinfo=UTC),
                    adjusted=False,
                )
        assert exc_info.value.provider_name == "binance"

    def test_non_progressing_klines_page_is_typed(self):
        start_ms = int(datetime(2024, 1, 2, tzinfo=UTC).timestamp() * 1000)
        response = MagicMock()
        response.json.return_value = [
            [start_ms, "1", "2", "1", "1.5", "10"],
            [start_ms, "1", "2", "1", "1.5", "10"],
        ]
        response.raise_for_status.return_value = None
        with patch("app.providers.binance.httpx.get", return_value=response):
            with pytest.raises(ProviderResponseError, match="not increasing"):
                BinanceProvider().fetch_ohlcv(
                    "BTC-USD",
                    Timeframe.D1,
                    datetime(2024, 1, 2, tzinfo=UTC),
                    datetime(2024, 1, 3, tzinfo=UTC),
                    adjusted=False,
                )

    def test_rate_limit_http_is_typed(self):
        response = httpx.Response(
            429,
            headers={"Retry-After": "2"},
            request=httpx.Request("GET", "https://api.binance.com/api/v3/klines"),
        )
        with patch("app.providers.binance.httpx.get", return_value=response):
            with pytest.raises(ProviderRateLimitError) as exc_info:
                BinanceProvider().fetch_ohlcv(
                    "BTC-USD",
                    Timeframe.D1,
                    datetime(2024, 1, 2, tzinfo=UTC),
                    datetime(2024, 1, 3, tzinfo=UTC),
                    adjusted=False,
                )
        assert exc_info.value.provider_name == "binance"
        assert exc_info.value.status_code == 429

    def test_malformed_exchange_info_payload_is_typed(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"symbols": {}}
        mock_resp.raise_for_status.return_value = None
        with patch("app.providers.binance.httpx.get", return_value=mock_resp):
            with pytest.raises(ProviderResponseError) as exc_info:
                BinanceProvider().discover_universe_page("CRYPTOCURRENCY", 0)
        assert exc_info.value.provider_name == "binance"

    def test_malformed_exchange_info_rows_are_typed(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"symbols": [{"symbol": "BTCUSDT", "quoteAsset": "USDT"}]}
        mock_resp.raise_for_status.return_value = None
        with patch("app.providers.binance.httpx.get", return_value=mock_resp):
            with pytest.raises(ProviderResponseError, match="invalid baseAsset"):
                BinanceProvider().discover_universe_page("CRYPTOCURRENCY", 0)

    def test_malformed_ticker_payload_is_typed(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"price": "Infinity"}
        mock_resp.raise_for_status.return_value = None
        with patch("app.providers.binance.httpx.get", return_value=mock_resp):
            with pytest.raises(ProviderResponseError, match="non-finite"):
                BinanceProvider().get_current_price("BTC-USD")

    def test_historical_weight_estimate_rounds_up_per_1000_candle_page(self):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = start + timedelta(days=1001)
        assert estimate_ohlcv_request_weight(Timeframe.D1, start, end) == 4
        assert estimate_latest_ohlcv_request_weight(Timeframe.D1, 1001) == 4
        assert estimate_latest_ohlcv_request_weight(Timeframe.M1, 1000) == 6


# ── Coinbase/Kraken paginated OHLCV ──────────────────────────────────────────


class TestCryptoOHLCVPagination:
    @pytest.mark.parametrize("provider", [CoinbaseProvider(), KrakenProvider()])
    def test_adjusted_history_is_rejected_before_transport(self, provider):
        with patch("app.providers.crypto_market_data.httpx.get") as get:
            with pytest.raises(ProviderResponseError, match="exchange candles are raw"):
                provider.fetch_ohlcv(
                    "BTC-USD",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 1, 2, tzinfo=UTC),
                    adjusted=True,
                )
        get.assert_not_called()

    @pytest.mark.parametrize("provider_name", ["coinbase", "kraken"])
    def test_http_capacity_failure_is_typed(self, provider_name):
        response = httpx.Response(
            429,
            json={"error": "too many requests"},
            headers={"Retry-After": "2", "X-RateLimit-Limit": "15"},
            request=httpx.Request("GET", "https://provider.example"),
        )
        provider = CoinbaseProvider() if provider_name == "coinbase" else KrakenProvider()
        with patch("app.providers.crypto_market_data.httpx.get", return_value=response):
            with pytest.raises(ProviderRateLimitError) as exc_info:
                provider.get_current_price("BTC-USD")
        assert exc_info.value.provider_name == provider_name
        assert exc_info.value.status_code == 429
        assert exc_info.value.headers == {
            "retry-after": "2",
            "x-ratelimit-limit": "15",
        }
        assert exc_info.value.retry_at is not None

    @pytest.mark.parametrize("provider", [CoinbaseProvider(), KrakenProvider()])
    def test_unsupported_crypto_timeframe_is_typed(self, provider):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        with pytest.raises(ProviderResponseError, match="unsupported crypto timeframe"):
            provider.fetch_ohlcv(
                "BTC-USD", Timeframe.MN, start, start + timedelta(days=1), adjusted=False
            )

    def test_coinbase_transport_failure_is_typed(self):
        failure = httpx.ConnectError(
            "connection failed",
            request=httpx.Request("GET", "https://api.exchange.coinbase.com/products/BTC-USD/ticker"),
        )
        with patch("app.providers.crypto_market_data.httpx.get", side_effect=failure):
            with pytest.raises(ProviderResponseError) as exc_info:
                CoinbaseProvider().get_current_price("BTC-USD")
        assert exc_info.value.provider_name == "coinbase"

    def test_kraken_invalid_json_is_typed(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.status_code = 200
        response.json.side_effect = ValueError("malformed payload")
        with patch("app.providers.crypto_market_data.httpx.get", return_value=response):
            with pytest.raises(ProviderResponseError) as exc_info:
                KrakenProvider().get_current_price("BTC-USD")
        assert exc_info.value.provider_name == "kraken"

    def test_coinbase_history_pages_300_candle_ranges(self):
        provider = CoinbaseProvider()
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = start + timedelta(minutes=301)
        first = [[start.timestamp(), "1", "2", "1.5", "1.75", "10"]]
        second_ts = start + timedelta(minutes=300)
        second = [[second_ts.timestamp(), "2", "3", "2.5", "2.75", "20"]]
        responses = [
            httpx.Response(
                200,
                json=first,
                request=httpx.Request("GET", "https://api.exchange.coinbase.com"),
            ),
            httpx.Response(
                200,
                json=second,
                request=httpx.Request("GET", "https://api.exchange.coinbase.com"),
            ),
        ]
        with patch("app.providers.crypto_market_data.httpx.get", side_effect=responses) as get:
            bars = provider.fetch_ohlcv("BTC-USD", Timeframe.M1, start, end, adjusted=False)

        assert get.call_count == 2
        assert [bar.ts for bar in bars] == [start, second_ts]
        assert all(bar.adjustment_basis == "raw" for bar in bars)
        assert all(bar.provenance["provider"] == "coinbase" for bar in bars)
        assert estimate_coinbase_ohlcv_request_count(Timeframe.M1, start, end) == 2
        assert estimate_coinbase_latest_ohlcv_request_count(Timeframe.M1, 301) == 2

    def test_kraken_history_follows_provider_last_cursor(self):
        provider = KrakenProvider()
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = start + timedelta(minutes=721)
        first_row = [start.timestamp(), "1", "2", "1.5", "1.75", "1.7", "10"]
        second_ts = start + timedelta(minutes=720)
        second_row = [second_ts.timestamp(), "2", "3", "2.5", "2.75", "2.7", "20"]
        responses = [
            httpx.Response(
                200,
                json={"result": {"XXBTZUSD": [first_row], "last": int((start + timedelta(minutes=719)).timestamp())}},
                request=httpx.Request("GET", "https://api.kraken.com/0/public/OHLC"),
            ),
            httpx.Response(
                200,
                json={"result": {"XXBTZUSD": [second_row], "last": int(second_ts.timestamp())}},
                request=httpx.Request("GET", "https://api.kraken.com/0/public/OHLC"),
            ),
        ]
        with patch("app.providers.crypto_market_data.httpx.get", side_effect=responses) as get:
            bars = provider.fetch_ohlcv("BTC-USD", Timeframe.M1, start, end, adjusted=False)

        assert get.call_count == 2
        assert [bar.ts for bar in bars] == [start, second_ts]
        assert all(bar.adjustment_basis == "raw" for bar in bars)
        assert all(bar.provenance["provider"] == "kraken" for bar in bars)
        assert estimate_kraken_ohlcv_request_count(Timeframe.M1, start, end) == 2
        assert estimate_kraken_latest_ohlcv_request_count(Timeframe.M1, 721) == 2

    def test_coinbase_malformed_candle_rows_are_typed(self):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        response = httpx.Response(
            200,
            json=[[start.timestamp(), "1"]],
            request=httpx.Request("GET", "https://api.exchange.coinbase.com"),
        )
        with patch("app.providers.crypto_market_data.httpx.get", return_value=response):
            with pytest.raises(ProviderResponseError) as exc_info:
                CoinbaseProvider().fetch_ohlcv(
                    "BTC-USD", Timeframe.M1, start, start + timedelta(minutes=1), adjusted=False
                )
        assert exc_info.value.provider_name == "coinbase"

    def test_kraken_malformed_candle_rows_are_typed(self):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        response = httpx.Response(
            200,
            json={"result": {"XXBTZUSD": [[start.timestamp(), "1"]], "last": 1}},
            request=httpx.Request("GET", "https://api.kraken.com/0/public/OHLC"),
        )
        with patch("app.providers.crypto_market_data.httpx.get", return_value=response):
            with pytest.raises(ProviderResponseError) as exc_info:
                KrakenProvider().fetch_ohlcv(
                    "BTC-USD", Timeframe.M1, start, start + timedelta(minutes=1), adjusted=False
                )
        assert exc_info.value.provider_name == "kraken"

    def test_crypto_invalid_ticker_shapes_are_typed(self):
        coinbase_response = httpx.Response(
            200,
            json={"price": "not-a-number"},
            request=httpx.Request("GET", "https://api.exchange.coinbase.com"),
        )
        with patch(
            "app.providers.crypto_market_data.httpx.get", return_value=coinbase_response
        ):
            with pytest.raises(ProviderResponseError):
                CoinbaseProvider().get_current_price("BTC-USD")

        kraken_response = httpx.Response(
            200,
            json={"result": {}},
            request=httpx.Request("GET", "https://api.kraken.com/0/public/Ticker"),
        )
        with patch(
            "app.providers.crypto_market_data.httpx.get", return_value=kraken_response
        ):
            with pytest.raises(ProviderResponseError):
                KrakenProvider().get_current_price("BTC-USD")

    @pytest.mark.parametrize("value", ["nan", "inf", "-inf"])
    def test_crypto_nonfinite_candle_values_are_typed(self, value):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        response = httpx.Response(
            200,
            json=[[start.timestamp(), value, "2", "1.5", "1.75", "10"]],
            request=httpx.Request("GET", "https://api.exchange.coinbase.com"),
        )
        with patch("app.providers.crypto_market_data.httpx.get", return_value=response):
            with pytest.raises(ProviderResponseError):
                CoinbaseProvider().fetch_ohlcv(
                    "BTC-USD", Timeframe.M1, start, start + timedelta(minutes=1), adjusted=False
                )

    def test_crypto_out_of_range_candle_timestamp_is_typed(self):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        response = httpx.Response(
            200,
            json=[["1e300", "1", "2", "1.5", "1.75", "10"]],
            request=httpx.Request("GET", "https://api.exchange.coinbase.com"),
        )
        with patch("app.providers.crypto_market_data.httpx.get", return_value=response):
            with pytest.raises(ProviderResponseError):
                CoinbaseProvider().fetch_ohlcv(
                    "BTC-USD", Timeframe.M1, start, start + timedelta(minutes=1), adjusted=False
                )

    def test_crypto_directory_rows_are_typed(self):
        coinbase_response = httpx.Response(
            200,
            json=[{"id": "BTC-USD"}, "invalid"],
            request=httpx.Request("GET", "https://api.exchange.coinbase.com/products"),
        )
        with patch(
            "app.providers.crypto_market_data.httpx.get", return_value=coinbase_response
        ):
            with pytest.raises(ProviderResponseError):
                CoinbaseProvider().discover_universe_page("CRYPTOCURRENCY", 0)

        kraken_response = httpx.Response(
            200,
            json={"result": {"XXBTZUSD": "invalid"}},
            request=httpx.Request("GET", "https://api.kraken.com/0/public/AssetPairs"),
        )
        with patch(
            "app.providers.crypto_market_data.httpx.get", return_value=kraken_response
        ):
            with pytest.raises(ProviderResponseError):
                KrakenProvider().discover_universe_page("CRYPTOCURRENCY", 0)

    def test_crypto_directory_missing_identity_is_typed(self):
        coinbase_response = httpx.Response(
            200,
            json=[{"quote_currency": "USD", "status": "online", "id": "BTC-USD"}],
            request=httpx.Request("GET", "https://api.exchange.coinbase.com/products"),
        )
        with patch(
            "app.providers.crypto_market_data.httpx.get", return_value=coinbase_response
        ):
            with pytest.raises(ProviderResponseError, match="incomplete product identity"):
                CoinbaseProvider().discover_universe_page("CRYPTOCURRENCY", 0)

        kraken_response = httpx.Response(
            200,
            json={"result": {"XXBTZUSD": {"quote": "ZUSD", "wsname": "XBT/USD"}}},
            request=httpx.Request("GET", "https://api.kraken.com/0/public/AssetPairs"),
        )
        with patch(
            "app.providers.crypto_market_data.httpx.get", return_value=kraken_response
        ):
            with pytest.raises(ProviderResponseError, match="incomplete asset-pair identity"):
                KrakenProvider().discover_universe_page("CRYPTOCURRENCY", 0)

    def test_twelve_data_history_pages_5000_point_ranges(self):
        provider = TwelveDataProvider()
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = start + timedelta(days=5001)
        first = {
            "values": [
                {
                    "datetime": start.isoformat(),
                    "open": "1",
                    "high": "2",
                    "low": "1",
                    "close": "1.5",
                    "volume": "10",
                }
            ]
        }
        second_ts = start + timedelta(days=5000)
        second = {
            "values": [
                {
                    "datetime": second_ts.isoformat(),
                    "open": "2",
                    "high": "3",
                    "low": "2",
                    "close": "2.5",
                    "volume": "20",
                }
            ]
        }
        with patch.object(provider, "_get", side_effect=[first, second]) as get:
            bars = provider.fetch_ohlcv("AAPL", Timeframe.D1, start, end, adjusted=False)

        assert get.call_count == 2
        assert [bar.ts for bar in bars] == [start, second_ts]
        assert estimate_twelve_data_ohlcv_request_count(Timeframe.D1, start, end) == 2
        assert estimate_twelve_data_latest_ohlcv_request_count(Timeframe.D1, 5001) == 2


# ── FRED series map ───────────────────────────────────────────────────────────


class TestFREDSeriesMap:
    @pytest.mark.parametrize(
        "symbol",
        [
            "^IRX",
            "^FVX",
            "^TNX",
            "^TYX",
            "EURUSD=X",
            "GBPUSD=X",
            "AUDUSD=X",
            "FEDFUNDS",
            "CPIAUCSL",
            "UNRATE",
            "VIXCLS",
            "DCOILWTICO",
        ],
    )
    def test_known_symbols_are_recognised(self, symbol):
        assert is_fred_symbol(symbol) is True

    def test_equity_symbol_is_not_fred(self):
        assert is_fred_symbol("AAPL") is False

    def test_fred_series_for_returns_correct_id(self):
        assert fred_series_for("^TNX") == "DGS10"
        assert fred_series_for("EURUSD=X") == "DEXUSEU"
        assert fred_series_for("DCOILWTICO") == "DCOILWTICO"

    def test_fred_series_for_unknown_returns_none(self):
        assert fred_series_for("AAPL") is None


class TestFREDCredentialWarning:
    def test_warns_when_api_key_missing(self, caplog):
        provider = FREDProvider()
        with patch("app.providers.fred.settings") as mock_settings:
            mock_settings.FRED_API_KEY = ""
            with caplog.at_level(logging.WARNING, logger="app.providers.fred"):
                with pytest.raises(ProviderNotConfiguredError):
                    provider.fetch_ohlcv(
                        "^TNX",
                        Timeframe.D1,
                        datetime(2024, 1, 1, tzinfo=UTC),
                        datetime(2024, 2, 1, tzinfo=UTC),
                    )
        assert "FRED_API_KEY" in caplog.text

    def test_unsupported_timeframe_returns_empty(self):
        provider = FREDProvider()
        with patch("app.providers.fred.settings") as mock_settings:
            mock_settings.FRED_API_KEY = "key"
            bars = provider.fetch_ohlcv(
                "^TNX",
                Timeframe.M1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 2, 1, tzinfo=UTC),
            )
        assert bars == []

    def test_unknown_symbol_returns_empty_without_warning(self, caplog):
        provider = FREDProvider()
        with caplog.at_level(logging.WARNING, logger="app.providers.fred"):
            bars = provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 2, 1, tzinfo=UTC),
            )
        assert bars == []
        assert "FRED_API_KEY" not in caplog.text


class TestMassiveReferenceProvider:
    def test_missing_key_is_honest_and_empty(self):
        with patch("app.providers.massive.settings") as mock_settings:
            mock_settings.MASSIVE_API_KEY = ""
            mock_settings.MARKETDATA_API_KEY = ""
            provider = MassiveProvider()
            with pytest.raises(ProviderNotConfiguredError):
                provider.search_instruments("AAPL")
            assert provider.discover_universe_page("CRYPTOCURRENCY", 0) == {
                "total": 0,
                "quotes": [],
            }
            with pytest.raises(ProviderNotConfiguredError):
                provider.fetch_market_events()

    def test_search_and_discovery_parse_reference_rows(self):
        response = MagicMock()
        response.json.side_effect = [
            {
                "results": [
                    {
                        "ticker": "AAPL",
                        "name": "Apple Inc.",
                        "primary_exchange": "XNAS",
                        "type": "CS",
                    }
                ]
            },
            {
                "results": [
                    {
                        "ticker": "AAPL",
                        "name": "Apple Inc.",
                        "primary_exchange": "XNAS",
                        "type": "CS",
                    }
                ],
                "next_url": "https://api.massive.com/v3/reference/tickers?cursor=abc",
            },
            {"results": []},
        ]
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.massive.settings") as mock_settings,
            patch("app.providers.massive.httpx.get", return_value=response) as get,
        ):
            mock_settings.MASSIVE_API_KEY = "key"
            mock_settings.MARKETDATA_API_KEY = ""
            provider = MassiveProvider()
            result = provider.search_instruments("AAPL")
            page = provider.discover_universe_page("EQUITY", 0)
            next_page = provider.discover_universe_page("EQUITY", 1000)
        assert result[0].symbol == "AAPL"
        assert result[0].exchange == "XNAS"
        assert page["quotes"][0]["instrument_type"] == "CS"
        assert page["next_url"] == "https://api.massive.com/v3/reference/tickers?cursor=abc"
        assert page["total"] is None and page["complete"] is False
        assert next_page["quotes"] == []
        assert next_page["total"] is None and next_page["complete"] is True
        assert get.call_count == 3
        assert get.call_args_list[1].kwargs["params"].get("cursor") is None
        assert get.call_args_list[2].kwargs["params"]["cursor"] == "abc"

    @pytest.mark.parametrize(
        "payload",
        [
            {"results": "not-an-array"},
            {"results": [{"name": "Missing ticker"}, 42]},
        ],
    )
    def test_search_rejects_malformed_reference_rows(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.massive.settings") as mock_settings,
            patch("app.providers.massive.httpx.get", return_value=response),
        ):
            mock_settings.MASSIVE_API_KEY = "key"
            mock_settings.MARKETDATA_API_KEY = ""
            with pytest.raises(ProviderResponseError, match="Massive"):
                MassiveProvider().search_instruments("AAPL")

    def test_ipo_calendar_normalizes_bounds_status_and_cursor_without_following_pages(self):
        response = MagicMock()
        response.json.return_value = {
            "results": [
                {
                    "ticker": "NEW",
                    "isin": "US0000000001",
                    "issuer_name": "New Corp",
                    "listing_date": "2024-01-02",
                    "last_updated": "2024-01-01T12:30:00Z",
                    "ipo_status": "upcoming",
                    "primary_exchange": "XNAS",
                },
                {
                    "ticker": "OLD",
                    "issuer_name": "Old Corp",
                    "listing_date": "2023-12-31",
                    "ipo_status": "history",
                },
            ],
            "next_url": "https://api.massive.com/vX/reference/ipos?cursor=next",
        }
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.massive.settings") as mock_settings,
            patch("app.providers.massive.httpx.get", return_value=response) as get,
        ):
            mock_settings.MASSIVE_API_KEY = "key"
            mock_settings.MARKETDATA_API_KEY = ""
            page = MassiveProvider().fetch_market_events_page(
                start=date(2024, 1, 1), end=date(2024, 1, 3), status="UPCOMING"
            )
        assert len(page["events"]) == 1
        event = page["events"][0]
        assert event.event_key == "massive:ipo:NEW:2024-01-02"
        assert event.event_time == datetime(2024, 1, 1, 12, 30, tzinfo=UTC)
        assert event.is_provisional is True
        assert event.raw_payload["primary_exchange"] == "XNAS"
        assert page["next_url"].endswith("cursor=next")
        assert page["complete"] is False
        assert get.call_count == 1
        assert get.call_args.args[0] == "https://api.massive.com/vX/reference/ipos"
        assert get.call_args.kwargs["params"]["ipo_status"] == "upcoming"

    @pytest.mark.parametrize(
        "payload",
        [
            {"results": ["not-a-row"]},
            {"results": [{"ticker": "NO_DATE"}]},
            {"results": [{"listing_date": "2024-01-02"}]},
        ],
    )
    def test_ipo_calendar_rejects_malformed_rows(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.massive.settings") as mock_settings,
            patch("app.providers.massive.httpx.get", return_value=response),
        ):
            mock_settings.MASSIVE_API_KEY = "key"
            mock_settings.MARKETDATA_API_KEY = ""
            with pytest.raises(ProviderResponseError, match="Massive"):
                MassiveProvider().fetch_market_events()

    def test_market_holidays_normalize_array_rows_and_early_close(self):
        response = MagicMock()
        response.json.return_value = [
            {
                "date": "2024-11-28",
                "exchange": "NYSE",
                "name": "Thanksgiving",
                "status": "closed",
            },
            {
                "date": "2024-11-29",
                "exchange": "NASDAQ",
                "name": "Thanksgiving",
                "open": "2024-11-29T14:30:00.000Z",
                "close": "2024-11-29T18:00:00.000Z",
                "status": "early-close",
            },
        ]
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.massive.settings") as mock_settings,
            patch("app.providers.massive.httpx.get", return_value=response) as get,
        ):
            mock_settings.MASSIVE_API_KEY = "key"
            mock_settings.MARKETDATA_API_KEY = ""
            events = MassiveProvider().fetch_market_holidays(
                start=date(2024, 11, 28), end=date(2024, 11, 29)
            )
        assert [event.event_type for event in events] == ["market_holiday", "market_holiday"]
        assert events[0].event_key == "massive:market_holiday:NYSE:2024-11-28:closed"
        assert events[1].event_time == datetime(2024, 11, 29, 14, 30, tzinfo=UTC)
        assert events[1].raw_payload["close"] == "2024-11-29T18:00:00.000Z"
        assert get.call_args.args[0] == "https://api.massive.com/v1/marketstatus/upcoming"

    @pytest.mark.parametrize(
        "payload",
        [
            {"results": [{"exchange": "NYSE"}]},
            {"results": [{"date": "not-a-date"}, "not-a-row"]},
        ],
    )
    def test_market_holidays_reject_malformed_rows(self, payload):
        response = MagicMock()
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.massive.settings") as mock_settings,
            patch("app.providers.massive.httpx.get", return_value=response),
        ):
            mock_settings.MASSIVE_API_KEY = "key"
            mock_settings.MARKETDATA_API_KEY = ""
            with pytest.raises(ProviderResponseError, match="Massive market-holiday"):
                MassiveProvider().fetch_market_holidays()

    def test_ipo_calendar_http_429_is_typed_and_redacted(self):
        response = MagicMock()
        response.status_code = 429
        response.headers = {"Retry-After": "60"}
        request = httpx.Request("GET", "https://api.massive.com/vX/reference/ipos?apiKey=secret")
        response.request = request
        response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429 for https://api.massive.com/vX/reference/ipos?apiKey=secret",
            request=request,
            response=response,
        )
        with (
            patch("app.providers.massive.settings") as mock_settings,
            patch("app.providers.massive.httpx.get", return_value=response),
        ):
            mock_settings.MASSIVE_API_KEY = "secret"
            mock_settings.MARKETDATA_API_KEY = ""
            with pytest.raises(ProviderRateLimitError) as exc_info:
                MassiveProvider().fetch_market_events()
        assert exc_info.value.status_code == 429
        assert "secret" not in str(exc_info.value)


class TestAlphaVantageProvider:
    def test_missing_key_is_empty(self):
        with patch("app.providers.alpha_vantage.settings") as mock_settings:
            mock_settings.ALPHA_VANTAGE_API_KEY = ""
            with pytest.raises(ProviderNotConfiguredError):
                AlphaVantageProvider().search_instruments("AAPL")

    def test_daily_history_is_parsed_and_bounded(self):
        response = MagicMock()
        response.json.return_value = {
            "Time Series (Daily)": {
                "2024-01-03": {
                    "1. open": "101",
                    "2. high": "103",
                    "3. low": "100",
                    "4. close": "102",
                    "5. volume": "1000",
                },
                "2024-01-02": {
                    "1. open": "99",
                    "2. high": "100",
                    "3. low": "98",
                    "4. close": "99",
                    "5. volume": "900",
                },
            }
        }
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as mock_settings,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response) as get,
        ):
            mock_settings.ALPHA_VANTAGE_API_KEY = "key"
            bars = AlphaVantageProvider().fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 2, tzinfo=UTC),
                datetime(2024, 1, 4, tzinfo=UTC),
                adjusted=False,
            )
        assert [bar.close for bar in bars] == [99.0, 102.0]
        assert get.call_args.kwargs["params"]["outputsize"] == "compact"
        assert bars[0].adjustment_basis == "raw"
        assert bars[0].adjustment_version == "provider-native"
        assert bars[0].provenance["provider"] == "alpha_vantage"

    def test_adjusted_history_is_rejected_on_free_raw_endpoint(self):
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get") as get,
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(
                ProviderResponseError,
                match="free daily history is raw; request adjusted=False",
            ):
                AlphaVantageProvider().fetch_ohlcv(
                    "AAPL",
                    Timeframe.D1,
                    datetime(2024, 1, 2, tzinfo=UTC),
                    datetime(2024, 1, 4, tzinfo=UTC),
                )
        get.assert_not_called()

    def test_listing_status_becomes_paginated_universe_evidence(self):
        response = MagicMock()
        response.text = (
            "symbol,name,exchange,assetType,ipoDate,delistingDate,status\n"
            "AAPL,Apple Inc.,NASDAQ,Common Stock,1980-12-12,,Active\n"
            "MSFT,Microsoft Corp.,NASDAQ,Common Stock,1986-03-13,,Active\n"
        )
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as mock_settings,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            mock_settings.ALPHA_VANTAGE_API_KEY = "key"
            page = AlphaVantageProvider().discover_universe_page("EQUITY", 1)
        assert page["total"] == 2
        assert page["quotes"][0]["symbol"] == "MSFT"
        assert page["quotes"][0]["status"] == "active"

    def test_ipo_calendar_becomes_bounded_market_events(self):
        response = MagicMock()
        response.text = (
            "symbol,name,ipoDate,status\n"
            "NEW,New Corp,2024-01-02,expected\n"
            "OLD,Old Corp,2023-12-31,completed\n"
        )
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as mock_settings,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response) as get,
        ):
            mock_settings.ALPHA_VANTAGE_API_KEY = "key"
            events = AlphaVantageProvider().fetch_market_events(
                start=date(2024, 1, 1), end=date(2024, 1, 3)
            )

        assert len(events) == 1
        assert events[0].event_type == "ipo"
        assert events[0].event_key == "alpha_vantage:ipo:NEW:2024-01-02"
        assert events[0].effective_date == date(2024, 1, 2)
        assert events[0].is_provisional is True
        assert get.call_args.kwargs["params"]["function"] == "IPO_CALENDAR"

    def test_earnings_calendar_becomes_bounded_market_events(self):
        response = MagicMock()
        response.text = (
            "symbol,name,reportDate,fiscalDateEnding,estimate,currency\n"
            "AAPL,Apple Inc.,2024-01-02,2023-12-30,2.10,USD\n"
            "MSFT,Microsoft Corp.,2024-01-05,2023-12-31,2.75,USD\n"
        )
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as mock_settings,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response) as get,
        ):
            mock_settings.ALPHA_VANTAGE_API_KEY = "key"
            events = AlphaVantageProvider().fetch_earnings_calendar(
                horizon="3month",
                start=date(2024, 1, 1),
                end=date(2024, 1, 3),
            )

        assert len(events) == 1
        assert events[0].event_type == "earnings"
        assert events[0].event_key == "alpha_vantage:earnings_calendar:AAPL:2024-01-02"
        assert events[0].effective_date == date(2024, 1, 2)
        assert events[0].source_version == "EARNINGS_CALENDAR:3month"
        assert get.call_args.kwargs["params"] == {
            "function": "EARNINGS_CALENDAR",
            "apikey": "key",
            "horizon": "3month",
        }

    def test_earnings_calendar_rejects_unknown_horizon(self):
        with pytest.raises(ProviderResponseError, match="horizon must be"):
            AlphaVantageProvider().fetch_earnings_calendar(horizon="1year")

    def test_earnings_calendar_rejects_invalid_report_date(self):
        response = MagicMock(status_code=200)
        response.text = "symbol,name,reportDate\nAAPL,Apple Inc.,not-a-date\n"
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderResponseError, match="earnings-calendar date"):
                AlphaVantageProvider().fetch_earnings_calendar()

    def test_earnings_history_normalizes_annual_and_quarterly_rows(self):
        response = MagicMock()
        response.json.return_value = {
            "symbol": "AAPL",
            "annualEarnings": [
                {"fiscalDateEnding": "2023-09-30", "reportedEPS": "6.13"},
            ],
            "quarterlyEarnings": [
                {
                    "fiscalDateEnding": "2024-03-30",
                    "reportedDate": "2024-05-02",
                    "reportedEPS": "1.53",
                    "estimatedEPS": "1.50",
                    "surprise": "0.03",
                    "surprisePercentage": "2.0",
                },
                {
                    "fiscalDateEnding": "2024-06-29",
                    "reportedDate": "",
                    "reportedEPS": "None",
                    "estimatedEPS": "1.35",
                },
            ],
        }
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response) as get,
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            events = AlphaVantageProvider().fetch_instrument_events("aapl")

        assert [event.event_type for event in events] == [
            InstrumentEventType.EARNINGS,
            InstrumentEventType.EARNINGS,
            InstrumentEventType.EARNINGS_ESTIMATE,
        ]
        assert [event.event_time.date() for event in events] == [
            date(2023, 9, 30),
            date(2024, 5, 2),
            date(2024, 6, 29),
        ]
        assert str(events[1].eps_actual) == "1.53"
        assert str(events[1].eps_estimate) == "1.50"
        assert str(events[1].eps_surprise_pct) == "2.0"
        assert events[2].time_hint is EventTimeHint.UNKNOWN
        assert events[0].source_event_key.startswith("alpha_vantage:earnings:annual:AAPL:")
        assert get.call_args.kwargs["params"] == {
            "function": "EARNINGS",
            "apikey": "key",
            "symbol": "AAPL",
        }

    @pytest.mark.parametrize(
        "payload,match",
        [
            ({"annualEarnings": [], "quarterlyEarnings": "not-an-array"}, "quarterlyEarnings"),
            (
                {"annualEarnings": [{"reportedEPS": "1.2"}], "quarterlyEarnings": []},
                "fiscalDateEnding",
            ),
            (
                {
                    "annualEarnings": [],
                    "quarterlyEarnings": [
                        {"fiscalDateEnding": "2024-03-30", "reportedDate": "not-a-date"}
                    ],
                },
                "reportedDate",
            ),
            (
                {
                    "annualEarnings": [],
                    "quarterlyEarnings": [
                        {"fiscalDateEnding": "2024-03-30", "reportedEPS": "NaN"}
                    ],
                },
                "reportedEPS",
            ),
        ],
    )
    def test_earnings_history_rejects_malformed_rows(self, payload, match):
        response = MagicMock(status_code=200)
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderResponseError, match=match):
                AlphaVantageProvider().fetch_instrument_events("AAPL")

    def test_http_success_error_message_is_typed(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"Error Message": "Invalid API call."}
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderResponseError) as exc_info:
                AlphaVantageProvider().fetch_ohlcv(
                    "AAPL",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 2, 1, tzinfo=UTC),
                    adjusted=False,
                )
        assert exc_info.value.provider_name == "alpha_vantage"

    def test_csv_endpoint_error_message_is_typed(self):
        response = MagicMock()
        response.status_code = 200
        response.text = '{"Error Message":"Invalid API call."}'
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderResponseError):
                AlphaVantageProvider().discover_universe_page("EQUITY", 0)

    def test_transport_failure_is_typed(self):
        failure = httpx.ConnectError(
            "connection failed",
            request=httpx.Request("GET", "https://www.alphavantage.co/query"),
        )
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", side_effect=failure),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderResponseError) as exc_info:
                AlphaVantageProvider().search_instruments("AAPL")
        assert exc_info.value.provider_name == "alpha_vantage"

    def test_invalid_json_is_typed(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.status_code = 200
        response.json.side_effect = ValueError("malformed payload")
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderResponseError) as exc_info:
                AlphaVantageProvider().search_instruments("AAPL")
        assert exc_info.value.provider_name == "alpha_vantage"

    @pytest.mark.parametrize(
        "payload",
        [
            {"bestMatches": "not-an-array"},
            {"bestMatches": [{"1. symbol": "AAPL"}, "not-a-row"]},
        ],
    )
    def test_symbol_search_rejects_malformed_rows(self, payload):
        response = MagicMock(status_code=200)
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderResponseError, match="Alpha Vantage"):
                AlphaVantageProvider().search_instruments("AAPL")

    @pytest.mark.parametrize(
        "payload",
        [
            {"Time Series (Daily)": "not-an-object"},
            {"Time Series (Daily)": {"2024-01-02": "not-a-row"}},
            {"Time Series (Daily)": {"2024-01-02": {"1. open": "1"}}},
        ],
    )
    def test_daily_history_rejects_malformed_rows(self, payload):
        response = MagicMock(status_code=200)
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderResponseError, match="Alpha Vantage"):
                AlphaVantageProvider().fetch_ohlcv(
                    "AAPL",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 1, 5, tzinfo=UTC),
                    adjusted=False,
                )

    def test_non_rate_limit_http_failure_is_typed(self):
        response = httpx.Response(
            500,
            request=httpx.Request("GET", "https://www.alphavantage.co/query"),
        )
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderResponseError) as exc_info:
                AlphaVantageProvider().search_instruments("AAPL")
        assert exc_info.value.provider_name == "alpha_vantage"

    def test_listing_csv_rejects_missing_columns(self):
        response = MagicMock(status_code=200)
        response.text = "symbol,name\nAAPL,Apple\n"
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderResponseError, match="listing CSV"):
                AlphaVantageProvider().discover_universe_page("EQUITY", 0)

    def test_ipo_csv_rejects_invalid_dates(self):
        response = MagicMock(status_code=200)
        response.text = "symbol,name,ipoDate\nNEW,New Corp,not-a-date\n"
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderResponseError, match="invalid IPO date"):
                AlphaVantageProvider().fetch_market_events()

    def test_ipo_csv_information_message_is_typed_as_rate_limit(self):
        response = MagicMock(status_code=200)
        response.text = "symbol,name,ipoDate,priceRangeLow,priceRangeHigh,currency,exchange\nI,n,f,o,r,m,a\n"
        response.raise_for_status.return_value = None
        before = datetime.now(UTC) + timedelta(days=1)
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderRateLimitError) as exc_info:
                AlphaVantageProvider().fetch_market_events()
        after = datetime.now(UTC) + timedelta(days=1)
        assert before <= exc_info.value.retry_at <= after
        assert str(exc_info.value) == (
            "Alpha Vantage CSV response indicates the documented daily request capacity"
        )
        assert "symbol,name" not in str(exc_info.value)

    def test_json_daily_capacity_message_gets_provider_window(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "Information": "The standard API call frequency is 25 requests per day."
        }
        response.headers = {"X-RateLimit-Remaining": "0"}
        response.raise_for_status.return_value = None
        before = datetime.now(UTC) + timedelta(days=1)
        with (
            patch("app.providers.alpha_vantage.settings") as configured,
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            configured.ALPHA_VANTAGE_API_KEY = "key"
            with pytest.raises(ProviderRateLimitError) as exc_info:
                AlphaVantageProvider().search_instruments("AAPL")
        after = datetime.now(UTC) + timedelta(days=1)
        assert before <= exc_info.value.retry_at <= after
        assert exc_info.value.headers == {"X-RateLimit-Remaining": "0"}


class TestCryptoProviderErrorEnvelopes:
    def test_kraken_http_success_error_array_is_typed(self):
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"error": ["EQuery:Unknown asset pair"]}
        response.raise_for_status.return_value = None
        with patch("app.providers.crypto_market_data.httpx.get", return_value=response):
            with pytest.raises(ProviderResponseError) as exc_info:
                KrakenProvider().get_current_price("BTC-USD")
        assert exc_info.value.provider_name == "kraken"


class TestFREDOHLCVParsing:
    def test_scalar_observation_becomes_ohlc_bar(self):
        provider = FREDProvider()
        fake_observations = {
            "observations": [
                {"date": "2024-01-02", "value": "4.52"},
                {"date": "2024-01-03", "value": "4.55"},
                {"date": "2024-01-04", "value": "."},  # FRED missing-data marker
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_observations
        mock_resp.raise_for_status.return_value = None

        with (
            patch("app.providers.fred.settings") as mock_settings,
            patch("app.providers.fred.httpx.get", return_value=mock_resp),
        ):
            mock_settings.FRED_API_KEY = "key"
            bars = provider.fetch_ohlcv(
                "^TNX",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 10, tzinfo=UTC),
            )

        assert len(bars) == 2  # the "." observation is skipped
        assert float(bars[0].open) == float(bars[0].close) == 4.52
        assert float(bars[0].high) == float(bars[0].low) == 4.52
        assert bars[0].volume is None

    def test_http_429_is_typed_instead_of_becoming_empty_success(self):
        provider = FREDProvider()
        response = httpx.Response(
            429,
            headers={"retry-after": "2", "x-rate-limit-remaining": "0"},
            request=httpx.Request("GET", "https://api.stlouisfed.org/fred/series/observations"),
        )
        with (
            patch("app.providers.fred.settings") as mock_settings,
            patch("app.providers.fred.httpx.get", return_value=response),
        ):
            mock_settings.FRED_API_KEY = "key"
            with pytest.raises(ProviderRateLimitError) as exc_info:
                provider.fetch_ohlcv(
                    "^TNX",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 1, 10, tzinfo=UTC),
                )

        assert exc_info.value.provider_name == "fred"
        assert exc_info.value.status_code == 429
        assert exc_info.value.headers["retry-after"] == "2"
        assert exc_info.value.retry_at is not None

    def test_latest_price_http_429_is_typed(self):
        provider = FREDProvider()
        response = httpx.Response(
            429,
            headers={"retry-after": "3"},
            request=httpx.Request("GET", "https://api.stlouisfed.org/fred/series/observations"),
        )
        with (
            patch("app.providers.fred.settings") as mock_settings,
            patch("app.providers.fred.httpx.get", return_value=response),
        ):
            mock_settings.FRED_API_KEY = "key"
            with pytest.raises(ProviderRateLimitError):
                provider.get_current_price("^TNX")

    def test_http_success_error_code_is_typed(self):
        provider = FREDProvider()
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "error_code": 400,
            "error_message": "Bad series request",
        }
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.fred.settings") as configured,
            patch("app.providers.fred.httpx.get", return_value=response),
        ):
            configured.FRED_API_KEY = "key"
            with pytest.raises(ProviderResponseError) as exc_info:
                provider.fetch_ohlcv(
                    "^TNX",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 2, 1, tzinfo=UTC),
                )
        assert exc_info.value.provider_name == "fred"

    def test_transport_failures_are_typed_instead_of_empty_history(self):
        provider = FREDProvider()
        failure = httpx.ConnectError(
            "connection failed",
            request=httpx.Request("GET", "https://api.stlouisfed.org/fred/series/observations"),
        )
        with (
            patch("app.providers.fred.settings") as configured,
            patch("app.providers.fred.httpx.get", side_effect=failure),
        ):
            configured.FRED_API_KEY = "key"
            with pytest.raises(ProviderResponseError) as exc_info:
                provider.fetch_ohlcv(
                    "^TNX",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 2, 1, tzinfo=UTC),
                )
        assert exc_info.value.provider_name == "fred"

    def test_invalid_json_is_typed_instead_of_empty_history(self):
        provider = FREDProvider()
        response = MagicMock()
        response.json.side_effect = ValueError("malformed payload")
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.fred.settings") as configured,
            patch("app.providers.fred.httpx.get", return_value=response),
        ):
            configured.FRED_API_KEY = "key"
            with pytest.raises(ProviderResponseError) as exc_info:
                provider.fetch_ohlcv(
                    "^TNX",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 2, 1, tzinfo=UTC),
                )
        assert exc_info.value.provider_name == "fred"

    @pytest.mark.parametrize(
        "payload",
        [
            {"observations": "not-an-array"},
            {"observations": [{"date": "2024-01-02", "value": "4.5"}, "not-a-row"]},
            {"observations": [{"date": "2024-01-02", "value": "NaN"}]},
            {"observations": [{"date": "not-a-date", "value": "4.5"}]},
        ],
    )
    def test_malformed_observations_are_typed(self, payload):
        provider = FREDProvider()
        response = MagicMock(status_code=200)
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.fred.settings") as configured,
            patch("app.providers.fred.httpx.get", return_value=response),
        ):
            configured.FRED_API_KEY = "key"
            with pytest.raises(ProviderResponseError, match="FRED"):
                provider.fetch_ohlcv(
                    "^TNX",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 1, 10, tzinfo=UTC),
                )

    def test_non_rate_limit_http_failure_is_typed_instead_of_empty_history(self):
        provider = FREDProvider()
        response = httpx.Response(
            500,
            request=httpx.Request("GET", "https://api.stlouisfed.org/fred/series/observations"),
        )
        with (
            patch("app.providers.fred.settings") as configured,
            patch("app.providers.fred.httpx.get", return_value=response),
        ):
            configured.FRED_API_KEY = "key"
            with pytest.raises(ProviderResponseError) as exc_info:
                provider.fetch_ohlcv(
                    "^TNX",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 1, 10, tzinfo=UTC),
                )
        assert exc_info.value.provider_name == "fred"


# ── CoinGecko ─────────────────────────────────────────────────────────────────


class TestCoinGeckoCredentialWarning:
    def test_missing_key_is_explicit(self, caplog):
        provider = CoinGeckoProvider()
        with patch("app.providers.coingecko.settings") as mock_settings:
            mock_settings.COINGECKO_API_KEY = ""
            with pytest.raises(ProviderNotConfiguredError):
                provider._headers()

    def test_missing_key_does_not_call_network(self, caplog):
        provider = CoinGeckoProvider()
        with patch("app.providers.coingecko.settings") as mock_settings:
            mock_settings.COINGECKO_API_KEY = ""
            with pytest.raises(ProviderNotConfiguredError):
                provider._headers()

    def test_includes_key_header_when_configured(self):
        provider = CoinGeckoProvider()
        with patch("app.providers.coingecko.settings") as mock_settings:
            mock_settings.COINGECKO_API_KEY = "demo-key-123"
            headers = provider._headers()
        assert headers == {"x-cg-demo-api-key": "demo-key-123"}

    def test_profile_uses_ranked_symbol_search_before_metadata_fetch(self):
        provider = CoinGeckoProvider()
        search_response = MagicMock()
        search_response.status_code = 200
        search_response.content = b"search"
        search_response.headers = {}
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {
            "coins": [
                {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin"},
                {"id": "unrelated-btc", "symbol": "BTC", "name": "Unrelated BTC"},
            ]
        }
        profile_response = MagicMock()
        profile_response.status_code = 200
        profile_response.content = b"profile"
        profile_response.headers = {}
        profile_response.raise_for_status.return_value = None
        profile_response.json.return_value = {
            "id": "bitcoin",
            "symbol": "btc",
            "name": "Bitcoin",
            "description": {"en": ""},
            "market_data": {},
            "platforms": {},
            "links": {"homepage": [""]},
        }
        with (
            patch("app.providers.coingecko.settings") as configured,
            patch(
                "app.providers.coingecko.httpx.get",
                side_effect=[search_response, profile_response],
            ) as get,
        ):
            configured.COINGECKO_API_KEY = "demo-key-123"
            profile = provider.get_instrument_profile("BTC-USD")

        assert profile is not None
        assert profile.extra["coingecko_id"] == "bitcoin"
        assert get.call_count == 2

    def test_discovery_returns_empty_for_non_crypto(self):
        provider = CoinGeckoProvider()
        result = provider.discover_universe_page("EQUITY", 0)
        assert result == {"total": 0, "quotes": []}

    def test_supported_discovery_types(self):
        assert CoinGeckoProvider().supported_discovery_types() == ["CRYPTOCURRENCY"]

    def test_transport_failure_is_typed(self):
        failure = httpx.ConnectError(
            "connection failed",
            request=httpx.Request("GET", "https://api.coingecko.com/api/v3/search"),
        )
        with (
            patch("app.providers.coingecko.settings") as configured,
            patch("app.providers.coingecko.httpx.get", side_effect=failure),
        ):
            configured.COINGECKO_API_KEY = "demo-key-123"
            with pytest.raises(ProviderResponseError) as exc_info:
                CoinGeckoProvider().search_instruments("BTC")
        assert exc_info.value.provider_name == "coingecko"

    @pytest.mark.parametrize(
        "payload",
        [
            {"coins": "not-an-array"},
            {"coins": [{"id": "bitcoin", "symbol": "BTC"}, "not-a-row"]},
            {"coins": [{"id": "bitcoin", "name": "Bitcoin"}]},
        ],
    )
    def test_search_rejects_malformed_coin_rows(self, payload):
        response = MagicMock(status_code=200)
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.coingecko.settings") as configured,
            patch("app.providers.coingecko.httpx.get", return_value=response),
        ):
            configured.COINGECKO_API_KEY = "demo-key-123"
            with pytest.raises(ProviderResponseError, match="CoinGecko"):
                CoinGeckoProvider().search_instruments("BTC")

    @pytest.mark.parametrize("payload", ["not-an-array", [{"symbol": "btc"}, "not-a-row"]])
    def test_discovery_rejects_malformed_market_rows(self, payload):
        response = MagicMock(status_code=200)
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.coingecko.settings") as configured,
            patch("app.providers.coingecko.httpx.get", return_value=response),
        ):
            configured.COINGECKO_API_KEY = "demo-key-123"
            with pytest.raises(ProviderResponseError, match="CoinGecko"):
                CoinGeckoProvider().discover_universe_page("CRYPTOCURRENCY", 0)

    def test_non_rate_limit_http_failure_is_typed(self):
        response = httpx.Response(
            500,
            request=httpx.Request("GET", "https://api.coingecko.com/api/v3/search"),
        )
        with (
            patch("app.providers.coingecko.settings") as configured,
            patch("app.providers.coingecko.httpx.get", return_value=response),
        ):
            configured.COINGECKO_API_KEY = "demo-key-123"
            with pytest.raises(ProviderResponseError) as exc_info:
                CoinGeckoProvider().search_instruments("BTC")
        assert exc_info.value.provider_name == "coingecko"

    def test_invalid_json_is_typed(self):
        response = MagicMock()
        response.raise_for_status.return_value = None
        response.status_code = 200
        response.json.side_effect = ValueError("malformed payload")
        with (
            patch("app.providers.coingecko.settings") as configured,
            patch("app.providers.coingecko.httpx.get", return_value=response),
        ):
            configured.COINGECKO_API_KEY = "demo-key-123"
            with pytest.raises(ProviderResponseError) as exc_info:
                CoinGeckoProvider().search_instruments("BTC")
        assert exc_info.value.provider_name == "coingecko"


# ── EDGAR ticker map parsing ──────────────────────────────────────────────────


class TestEdgarTickerMap:
    @pytest.fixture(autouse=True)
    def _configured_sec_user_agent(self, monkeypatch):
        monkeypatch.setattr(
            "app.providers.edgar.settings.EDGAR_USER_AGENT",
            "charting-platform unit-test test@example.invalid",
        )

    def test_missing_user_agent_is_explicit(self):
        with patch("app.providers.edgar.settings") as configured:
            configured.EDGAR_USER_AGENT = ""
            with pytest.raises(ProviderNotConfiguredError):
                EdgarProvider()._headers()

    def test_placeholder_user_agent_is_explicit(self):
        with patch("app.providers.edgar.settings") as configured:
            configured.EDGAR_USER_AGENT = "charting-platform your.email@example.com"
            with pytest.raises(ProviderNotConfiguredError):
                EdgarProvider()._headers()

            configured.EDGAR_USER_AGENT = "ChartingPlatform <real contact email>"
            with pytest.raises(ProviderNotConfiguredError):
                EdgarProvider()._headers()

    def test_sec_exchange_directory_pages_all_reported_us_venues(self):
        import app.providers.edgar as edgar_module

        edgar_module._exchange_directory = []
        edgar_module._exchange_directory_ts = 0.0
        fake_response = {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [
                [320193, "Apple Inc.", "AAPL", "Nasdaq"],
                [66740, "Berkshire Hathaway Inc.", "BRK-B", "NYSE"],
                [1018724, "AMC Networks Inc.", "AMCX", "NYSE American"],
            ],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status.return_value = None

        with patch("app.providers.edgar.httpx.get", return_value=mock_resp):
            page = EdgarProvider().discover_universe_page("EQUITY", 0)

        assert page["total"] == 3
        assert [(row["symbol"], row["exchange"], row["sec_cik"]) for row in page["quotes"]] == [
            ("AAPL", "Nasdaq", 320193),
            ("AMCX", "NYSE American", 1018724),
            ("BRK-B", "NYSE", 66740),
        ]
        assert EdgarProvider().discover_universe_page("ETF", 0) == {"total": 0, "quotes": []}

    def test_sec_exchange_directory_accepts_object_rows_and_pages(self):
        import app.providers.edgar as edgar_module

        edgar_module._exchange_directory = []
        edgar_module._exchange_directory_ts = 0.0
        fake_response = {
            "0": {"cik": "1", "name": "One Corp", "ticker": "ONE", "exchange": "OTC"},
            "1": {"cik": "2", "name": "Two Corp", "ticker": "TWO", "exchange": "Cboe BZX"},
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status.return_value = None

        with patch("app.providers.edgar.httpx.get", return_value=mock_resp):
            first = EdgarProvider().discover_universe_page("EQUITY", 0)

        assert first["total"] == 2
        assert first["quotes"][0]["symbol"] == "ONE"
        assert EdgarProvider().discover_universe_page("EQUITY", 250) == {"total": 2, "quotes": []}

    def test_sec_exchange_directory_marks_distinct_issuers_with_same_ticker_ambiguous(self):
        import app.providers.edgar as edgar_module

        edgar_module._exchange_directory = []
        edgar_module._exchange_directory_ts = 0.0
        fake_response = {
            "fields": ["cik", "name", "ticker", "exchange"],
            "data": [
                [1, "One Holdings", "DUP", "NYSE"],
                [2, "Two Holdings", "DUP", "OTC"],
                [3, "Three Holdings", "OK", "Nasdaq"],
            ],
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_response
        mock_resp.raise_for_status.return_value = None

        with patch("app.providers.edgar.httpx.get", return_value=mock_resp):
            page = EdgarProvider().discover_universe_page("EQUITY", 0)

        duplicate_rows = [row for row in page["quotes"] if row["symbol"] == "DUP"]
        assert len(duplicate_rows) == 2
        assert all(len(row["identity_ambiguity"]) == 2 for row in duplicate_rows)
        assert page["quotes"][-1]["symbol"] == "OK"

    @pytest.mark.parametrize(
        "payload",
        [
            {"fields": ["cik", "name", "ticker"], "data": [[1, "One", "ONE", "EXTRA"]]},
            {"fields": ["cik", "name", "ticker"], "data": [[1, "One"], "not-a-row"]},
            {"data": [{"cik": 1}, "not-a-row"]},
            {"0": {"cik": 1, "name": "One"}, "1": "not-a-row"},
        ],
    )
    def test_sec_exchange_directory_rejects_malformed_rows(self, payload):
        import app.providers.edgar as edgar_module

        edgar_module._exchange_directory = []
        edgar_module._exchange_directory_ts = 0.0
        mock_resp = MagicMock()
        mock_resp.json.return_value = payload
        mock_resp.raise_for_status.return_value = None

        with patch("app.providers.edgar.httpx.get", return_value=mock_resp):
            with pytest.raises(ProviderResponseError, match="SEC EDGAR exchange directory"):
                EdgarProvider().discover_universe_page("EQUITY", 0)

    def test_sec_ticker_directory_rejects_malformed_rows(self):
        import app.providers.edgar as edgar_module

        edgar_module._ticker_map = {}
        edgar_module._ticker_map_ts = 0.0
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "0": {"ticker": "AAPL", "cik_str": "not-a-cik", "title": "Apple"},
        }
        mock_resp.raise_for_status.return_value = None

        with patch("app.providers.edgar.httpx.get", return_value=mock_resp):
            with pytest.raises(ProviderResponseError, match="SEC EDGAR ticker directory"):
                edgar_module._ensure_ticker_map({"User-Agent": "test test@example.invalid"})

    def test_search_instruments_uses_cached_sec_directory(self):
        import app.providers.edgar as edgar_module

        edgar_module._ticker_map = {
            "AAPL": {"cik": 320193, "title": "Apple Inc."},
            "MSFT": {"cik": 789019, "title": "Microsoft Corporation"},
        }
        edgar_module._ticker_map_ts = edgar_module._ticker_map_ts + 9999999

        results = EdgarProvider().search_instruments("apple", limit=5)

        assert [(item.symbol, item.name) for item in results] == [("AAPL", "Apple Inc.")]

    def test_ensure_ticker_map_parses_sec_json(self):
        import app.providers.edgar as edgar_module

        # Reset module cache so our fake data is loaded
        edgar_module._ticker_map = {}
        edgar_module._ticker_map_ts = 0.0

        fake_sec_response = {
            "0": {"cik_str": "320193", "ticker": "AAPL", "title": "Apple Inc."},
            "1": {"cik_str": "789019", "ticker": "MSFT", "title": "Microsoft Corporation"},
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_sec_response
        mock_resp.raise_for_status.return_value = None

        with patch("app.providers.edgar.httpx.get", return_value=mock_resp):
            _ensure_ticker_map({"User-Agent": "test test@test.com"})

        assert edgar_module._ticker_map["AAPL"] == {"cik": 320193, "title": "Apple Inc."}
        assert edgar_module._ticker_map["MSFT"] == {"cik": 789019, "title": "Microsoft Corporation"}

    def test_sec_http_status_failure_is_not_converted_to_synthetic_profile(self):
        import app.providers.edgar as edgar_module

        edgar_module._ticker_map = {"AAPL": {"cik": 320193, "title": "Apple Inc."}}
        edgar_module._ticker_map_ts = edgar_module._ticker_map_ts + 9999999
        edgar_module._profile_cache = {}
        response = httpx.Response(
            429,
            headers={"retry-after": "3"},
            request=httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000320193.json"),
        )
        provider = EdgarProvider()
        with (
            patch("app.providers.edgar.settings") as configured,
            patch("app.providers.edgar.httpx.get", return_value=response),
        ):
            configured.EDGAR_USER_AGENT = "charting-platform test test@example.invalid"
            with pytest.raises(httpx.HTTPStatusError):
                provider.get_instrument_profile("AAPL")

    def test_sec_transport_failure_is_not_converted_to_synthetic_profile(self):
        import app.providers.edgar as edgar_module

        edgar_module._ticker_map = {"AAPL": {"cik": 320193, "title": "Apple Inc."}}
        edgar_module._ticker_map_ts = edgar_module._ticker_map_ts + 9999999
        edgar_module._profile_cache = {}
        failure = httpx.ConnectError(
            "connection failed",
            request=httpx.Request("GET", "https://data.sec.gov/submissions/CIK0000320193.json"),
        )
        provider = EdgarProvider()
        with (
            patch("app.providers.edgar.settings") as configured,
            patch("app.providers.edgar.httpx.get", side_effect=failure),
        ):
            configured.EDGAR_USER_AGENT = "charting-platform test test@example.invalid"
            with pytest.raises(ProviderResponseError) as exc_info:
                provider.get_instrument_profile("AAPL")
        assert exc_info.value.provider_name == "edgar"

    def test_sec_invalid_json_is_not_converted_to_synthetic_profile(self):
        import app.providers.edgar as edgar_module

        edgar_module._ticker_map = {"AAPL": {"cik": 320193, "title": "Apple Inc."}}
        edgar_module._ticker_map_ts = edgar_module._ticker_map_ts + 9999999
        edgar_module._profile_cache = {}
        response = MagicMock()
        response.json.side_effect = ValueError("malformed payload")
        response.raise_for_status.return_value = None
        provider = EdgarProvider()
        with (
            patch("app.providers.edgar.settings") as configured,
            patch("app.providers.edgar.httpx.get", return_value=response),
        ):
            configured.EDGAR_USER_AGENT = "charting-platform test test@example.invalid"
            with pytest.raises(ProviderResponseError) as exc_info:
                provider.get_instrument_profile("AAPL")
        assert exc_info.value.provider_name == "edgar"

    def test_get_instrument_profile_returns_none_for_unknown_ticker(self):
        import app.providers.edgar as edgar_module

        edgar_module._ticker_map = {}  # empty cache — no CIK resolution possible
        edgar_module._ticker_map_ts = 0.0

        mock_resp = MagicMock()
        mock_resp.json.return_value = {}  # empty ticker map
        mock_resp.raise_for_status.return_value = None

        provider = EdgarProvider()
        with patch("app.providers.edgar.httpx.get", return_value=mock_resp):
            result = provider.get_instrument_profile("UNKNOWN_XYZ")
        assert result is None

    def test_fetch_instrument_events_parses_10q_and_10k(self):
        import app.providers.edgar as edgar_module

        edgar_module._ticker_map = {"AAPL": {"cik": 320193, "title": "Apple Inc."}}
        edgar_module._ticker_map_ts = edgar_module._ticker_map_ts + 9999999  # mark as fresh

        fake_submissions = {
            "filings": {
                "recent": {
                    "form": ["10-Q", "8-K", "10-K"],
                    "filingDate": ["2024-02-01", "2024-01-15", "2023-11-03"],
                    "accessionNumber": [
                        "0000320193-24-000010",
                        "0000320193-24-000005",
                        "0000320193-23-000100",
                    ],
                }
            }
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = fake_submissions
        mock_resp.raise_for_status.return_value = None

        provider = EdgarProvider()
        with (
            patch("app.providers.edgar.httpx.get", return_value=mock_resp),
            patch("app.providers.edgar.settings") as mock_settings,
        ):
            mock_settings.EDGAR_USER_AGENT = "test test@test.com"
            events = provider.fetch_instrument_events("AAPL")

        # Only 10-Q and 10-K should be included, not 8-K
        assert len(events) == 2
        titles = [e.title for e in events]
        assert any("Quarterly" in t for t in titles)
        assert any("Annual" in t for t in titles)

    def test_fetch_ipo_pipeline_events_normalizes_candidate_filings(self):
        submissions = {
            "name": "Example Issuer, Inc.",
            "tickers": ["EXMP"],
            "filings": {
                "recent": {
                    "form": ["S-1", "8-K", "F-1/A", "424B4"],
                    "filingDate": ["2024-01-02", "2024-01-03", "2024-02-04", "2024-03-05"],
                    "accessionNumber": [
                        "0000123456-24-000001",
                        "0000123456-24-000002",
                        "0000123456-24-000003",
                        "0000123456-24-000004",
                    ],
                    "primaryDocument": ["s1.htm", "8k.htm", "f1a.htm", "424b4.htm"],
                }
            },
        }
        response = MagicMock()
        response.json.return_value = submissions
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.edgar.settings") as configured,
            patch("app.providers.edgar.httpx.get", return_value=response) as get,
        ):
            configured.EDGAR_USER_AGENT = "test test@example.invalid"
            events = EdgarProvider().fetch_ipo_pipeline_events(
                "123456",
                start=date(2024, 1, 1),
                end=date(2024, 2, 29),
            )

        assert [event.raw_payload["form"] for event in events] == ["S-1", "F-1/A"]
        assert events[0].event_type == "ipo_pipeline"
        assert events[0].event_key == "edgar:ipo_pipeline:0000123456:000012345624000001"
        assert events[0].is_provisional is True
        assert events[0].raw_payload["filing_url"].endswith("/s1.htm")
        get.assert_called_once_with(
            "https://data.sec.gov/submissions/CIK0000123456.json",
            headers={"User-Agent": "test test@example.invalid"},
            timeout=20,
        )

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"cik": "not-a-cik"},
            {"cik": "123", "max_events": 0},
            {"cik": "123", "start": date(2024, 2, 1), "end": date(2024, 1, 1)},
        ],
    )
    def test_fetch_ipo_pipeline_events_rejects_invalid_bounds(self, kwargs):
        provider = EdgarProvider()
        with pytest.raises((ProviderResponseError, ValueError)):
            provider.fetch_ipo_pipeline_events(**kwargs)

    def test_fetch_ipo_pipeline_events_rejects_misaligned_arrays(self):
        response = MagicMock()
        response.json.return_value = {
            "filings": {
                "recent": {
                    "form": ["S-1"],
                    "filingDate": ["2024-01-02"],
                    "accessionNumber": [],
                }
            }
        }
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.edgar.settings") as configured,
            patch("app.providers.edgar.httpx.get", return_value=response),
        ):
            configured.EDGAR_USER_AGENT = "test test@example.invalid"
            with pytest.raises(ProviderResponseError, match="misaligned filing arrays"):
                EdgarProvider().fetch_ipo_pipeline_events("123456")

    def test_fetch_instrument_events_rejects_misaligned_filing_arrays(self):
        import app.providers.edgar as edgar_module

        edgar_module._ticker_map = {"AAPL": {"cik": 320193, "title": "Apple Inc."}}
        edgar_module._ticker_map_ts = edgar_module._ticker_map_ts + 9999999
        response = MagicMock()
        response.json.return_value = {
            "filings": {
                "recent": {
                    "form": ["10-Q"],
                    "filingDate": [],
                    "accessionNumber": ["0000320193-24-000010"],
                }
            }
        }
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.edgar.settings") as configured,
            patch("app.providers.edgar.httpx.get", return_value=response),
        ):
            configured.EDGAR_USER_AGENT = "test test@example.invalid"
            with pytest.raises(ProviderResponseError, match="misaligned filing arrays"):
                EdgarProvider().fetch_instrument_events("AAPL")

    def test_fetch_fundamental_facts_rejects_malformed_nested_rows(self):
        response = MagicMock()
        response.json.return_value = {"facts": {"us-gaap": {"Revenue": {"units": {"USD": [42]}}}}}
        response.raise_for_status.return_value = None
        with (
            patch("app.providers.edgar.settings") as configured,
            patch("app.providers.edgar.httpx.get", return_value=response),
        ):
            configured.EDGAR_USER_AGENT = "test test@example.invalid"
            with pytest.raises(ProviderResponseError, match="malformed observation"):
                EdgarProvider().fetch_fundamental_facts("320193")
