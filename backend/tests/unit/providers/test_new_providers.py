"""
Unit tests for the five new data providers added in the provider-abstraction feature.
All tests are pure-Python / no-network: HTTP calls are mocked where needed.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.models.ohlcv import Timeframe
from app.providers.alpaca import (
    AlpacaProvider,
    _is_crypto,
    _to_alpaca_crypto,
)
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.binance import BinanceProvider, _from_binance, _to_binance
from app.providers.coingecko import CoinGeckoProvider
from app.providers.edgar import EdgarProvider, _ensure_ticker_map
from app.providers.fred import FREDProvider, fred_series_for, is_fred_symbol
from app.providers.massive import MassiveProvider
from app.providers.registry import (
    get_discovery_provider,
    get_event_provider,
    get_metadata_provider,
    get_price_history_provider,
    get_search_provider,
    list_provider_capabilities,
)

# ── Registry capability detection ────────────────────────────────────────────


class TestRegistryCapabilities:
    def test_alpaca_capabilities(self):
        caps = set(list_provider_capabilities("alpaca"))
        assert "price_history" in caps
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
        assert caps == {"instrument_search", "universe_discovery"}
        assert get_search_provider("massive").name == "massive"
        assert get_discovery_provider("massive").name == "massive"

    def test_alpha_vantage_capabilities(self):
        caps = set(list_provider_capabilities("alpha_vantage"))
        assert {"instrument_search", "price_history", "latest_price", "universe_discovery"} <= caps


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

    def test_fetch_ohlcv_returns_empty_list_when_no_credentials(self):
        provider = AlpacaProvider()
        with patch("app.providers.alpaca.settings") as mock_settings:
            mock_settings.ALPACA_API_KEY = ""
            mock_settings.ALPACA_SECRET_KEY = ""
            result = provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 2, 1, tzinfo=UTC),
            )
        assert result == []

    def test_discover_universe_page_returns_empty_dict_shape_when_no_credentials(self):
        provider = AlpacaProvider()
        with patch("app.providers.alpaca.settings") as mock_settings:
            mock_settings.ALPACA_API_KEY = ""
            mock_settings.ALPACA_SECRET_KEY = ""
            result = provider.discover_universe_page("EQUITY", 0)
        assert result == {"total": 0, "quotes": []}


# ── Alpaca OHLCV bar parsing ──────────────────────────────────────────────────


class TestAlpacaOHLCVParsing:
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
        )
        assert bars == []

    def test_discovery_returns_empty_for_non_crypto_type(self):
        provider = BinanceProvider()
        result = provider.discover_universe_page("EQUITY", 0)
        assert result == {"total": 0, "quotes": []}

    def test_supported_discovery_types(self):
        assert BinanceProvider().supported_discovery_types() == ["CRYPTOCURRENCY"]


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
            )

        assert len(bars) == 1
        assert float(bars[0].open) == 42000.0
        assert float(bars[0].close) == 42500.0


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
                bars = provider.fetch_ohlcv(
                    "^TNX",
                    Timeframe.D1,
                    datetime(2024, 1, 1, tzinfo=UTC),
                    datetime(2024, 2, 1, tzinfo=UTC),
                )
        assert bars == []
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
            assert provider.search_instruments("AAPL") == []
            assert provider.discover_universe_page("CRYPTOCURRENCY", 0) == {
                "total": 0,
                "quotes": [],
            }

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
        assert next_page["quotes"] == []
        assert get.call_count == 3
        assert get.call_args_list[1].kwargs["params"].get("cursor") is None
        assert get.call_args_list[2].kwargs["params"]["cursor"] == "abc"


class TestAlphaVantageProvider:
    def test_missing_key_is_empty(self):
        with patch("app.providers.alpha_vantage.settings") as mock_settings:
            mock_settings.ALPHA_VANTAGE_API_KEY = ""
            assert AlphaVantageProvider().search_instruments("AAPL") == []

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
            patch("app.providers.alpha_vantage.httpx.get", return_value=response),
        ):
            mock_settings.ALPHA_VANTAGE_API_KEY = "key"
            bars = AlphaVantageProvider().fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 2, tzinfo=UTC),
                datetime(2024, 1, 4, tzinfo=UTC),
            )
        assert [bar.close for bar in bars] == [99.0, 102.0]

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


# ── CoinGecko ─────────────────────────────────────────────────────────────────


class TestCoinGeckoCredentialWarning:
    def test_warns_when_api_key_missing(self, caplog):
        provider = CoinGeckoProvider()
        with patch("app.providers.coingecko.settings") as mock_settings:
            mock_settings.COINGECKO_API_KEY = ""
            with caplog.at_level(logging.WARNING, logger="app.providers.coingecko"):
                headers = provider._headers()
        assert headers == {}
        assert "COINGECKO_API_KEY" in caplog.text

    def test_warns_once_per_provider_instance(self, caplog):
        provider = CoinGeckoProvider()
        with patch("app.providers.coingecko.settings") as mock_settings:
            mock_settings.COINGECKO_API_KEY = ""
            with caplog.at_level(logging.WARNING, logger="app.providers.coingecko"):
                provider._headers()
                provider._headers()
        warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert len(warnings) == 1

    def test_includes_key_header_when_configured(self):
        provider = CoinGeckoProvider()
        with patch("app.providers.coingecko.settings") as mock_settings:
            mock_settings.COINGECKO_API_KEY = "demo-key-123"
            headers = provider._headers()
        assert headers == {"x-cg-demo-api-key": "demo-key-123"}

    def test_discovery_returns_empty_for_non_crypto(self):
        provider = CoinGeckoProvider()
        result = provider.discover_universe_page("EQUITY", 0)
        assert result == {"total": 0, "quotes": []}

    def test_supported_discovery_types(self):
        assert CoinGeckoProvider().supported_discovery_types() == ["CRYPTOCURRENCY"]


# ── EDGAR ticker map parsing ──────────────────────────────────────────────────


class TestEdgarTickerMap:
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
