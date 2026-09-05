from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.models.ohlcv import Timeframe
from app.providers.errors import ProviderNotConfiguredError
from app.providers.optional_market_data import (
    EODHDProvider,
    FinnhubProvider,
    FMPProvider,
    MarketDataAppProvider,
    MarketstackProvider,
    TiingoProvider,
    TwelveDataProvider,
)
from app.providers.registry import list_provider_capabilities


def _response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_optional_adapters_are_concrete_and_capability_visible():
    assert {
        "tiingo",
        "twelve_data",
        "finnhub",
        "marketstack",
        "eodhd",
        "fmp",
    } <= {
        "tiingo",
        "twelve_data",
        "finnhub",
        "marketstack",
        "eodhd",
        "fmp",
    }
    assert "price_history" in list_provider_capabilities("twelve_data")
    assert "instrument_metadata" in list_provider_capabilities("finnhub")
    assert "instrument_search" in list_provider_capabilities("tiingo")
    assert "universe_discovery" in list_provider_capabilities("eodhd")
    assert "instrument_events" in list_provider_capabilities("finnhub")


def test_twelve_data_parses_intraday_values():
    provider = TwelveDataProvider()
    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [
            {
                "datetime": "2024-01-02 14:30:00",
                "open": "185.0",
                "high": "186.0",
                "low": "184.5",
                "close": "185.5",
                "volume": "1000",
            }
        ],
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch("app.providers.optional_market_data.httpx.get", return_value=_response(payload)),
    ):
        configured.TWELVE_DATA_API_KEY = "demo"
        bars = provider.fetch_ohlcv(
            "AAPL",
            Timeframe.M5,
            datetime(2024, 1, 2, 14, tzinfo=UTC),
            datetime(2024, 1, 2, 15, tzinfo=UTC),
        )
    assert len(bars) == 1
    assert bars[0].close == 185.5
    assert bars[0].is_adjusted is False


def test_finnhub_parses_parallel_candle_arrays():
    provider = FinnhubProvider()
    start = int(datetime(2024, 1, 2, tzinfo=UTC).timestamp())
    payload = {
        "s": "ok",
        "t": [start],
        "o": [100],
        "h": [102],
        "l": [99],
        "c": [101],
        "v": [1234],
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch("app.providers.optional_market_data.httpx.get", return_value=_response(payload)),
    ):
        configured.FINNHUB_API_KEY = "demo"
        bars = provider.fetch_ohlcv(
            "AAPL",
            Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 3, tzinfo=UTC),
        )
    assert [(bar.open, bar.close) for bar in bars] == [(100.0, 101.0)]


def test_daily_adapters_parse_common_rows():
    row = {
        "date": "2024-01-02",
        "open": "10",
        "high": "11",
        "low": "9",
        "close": "10.5",
        "volume": "42",
    }
    for provider, setting, payload in (
        (TiingoProvider(), "TIINGO_API_KEY", [row]),
        (MarketstackProvider(), "MARKETSTACK_API_KEY", {"data": [row]}),
        (EODHDProvider(), "EODHD_API_KEY", [row]),
        (FMPProvider(), "FMP_API_KEY", {"historical": [row]}),
    ):
        with (
            patch("app.providers.optional_market_data.settings") as configured,
            patch("app.providers.optional_market_data.httpx.get", return_value=_response(payload)),
        ):
            setattr(configured, setting, "demo")
            bars = provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 3, tzinfo=UTC),
            )
        assert len(bars) == 1
        assert bars[0].close == 10.5


def test_marketdata_app_uses_documented_v1_root_and_parses_candles():
    provider = MarketDataAppProvider()
    payload = {
        "s": "ok",
        "t": [int(datetime(2024, 1, 2, tzinfo=UTC).timestamp())],
        "o": [100],
        "h": [102],
        "l": [99],
        "c": [101],
        "v": [1234],
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.MARKETDATA_APP_API_KEY = "demo"
        bars = provider.fetch_ohlcv(
            "AAPL",
            Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 3, tzinfo=UTC),
        )

    assert provider.base_url == "https://api.marketdata.app/v1"
    assert get.call_args.args[0] == "https://api.marketdata.app/v1/stocks/candles/D/AAPL"
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer demo"}
    assert [(bar.open, bar.close) for bar in bars] == [(100.0, 101.0)]


def test_marketdata_app_inherited_current_price_uses_one_documented_credit():
    provider = MarketDataAppProvider()
    payload = {
        "s": "ok",
        "t": [int(datetime(2024, 1, 2, tzinfo=UTC).timestamp())],
        "o": [100],
        "h": [102],
        "l": [99],
        "c": [101],
        "v": [1234],
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.MARKETDATA_APP_API_KEY = "demo"
        with patch.object(
            provider,
            "latest_window_start",
            return_value=datetime(2024, 1, 1, tzinfo=UTC),
        ):
            assert provider.get_current_price("AAPL") == 101.0

    assert get.call_args.args[0] == "https://api.marketdata.app/v1/stocks/candles/D/AAPL"


def test_missing_credentials_never_make_optional_call():
    provider = TwelveDataProvider()
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch("app.providers.optional_market_data.httpx.get") as get,
    ):
        configured.TWELVE_DATA_API_KEY = ""
        with pytest.raises(ProviderNotConfiguredError):
            provider.get_current_price("AAPL")
    get.assert_not_called()
