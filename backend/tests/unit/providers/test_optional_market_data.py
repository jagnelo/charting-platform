from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.models.ohlcv import Timeframe
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from app.providers.optional_market_data import (
    EODHDProvider,
    FinnhubProvider,
    FMPProvider,
    MarketDataAppProvider,
    MarketstackProvider,
    TiingoProvider,
    TradierProvider,
    TwelveDataProvider,
    estimate_marketstack_latest_ohlcv_request_count,
    estimate_marketstack_ohlcv_request_count,
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
    assert "adjusted_price_history" not in list_provider_capabilities("twelve_data")
    assert "instrument_metadata" in list_provider_capabilities("finnhub")
    assert "instrument_search" in list_provider_capabilities("tiingo")
    assert "universe_discovery" in list_provider_capabilities("eodhd")
    assert "instrument_events" in list_provider_capabilities("finnhub")
    assert "market_events" in list_provider_capabilities("finnhub")
    assert "earnings" in list_provider_capabilities("finnhub")
    assert "option_chain" in list_provider_capabilities("tradier")
    assert "option_chain" in list_provider_capabilities("marketdata_app")
    assert "option_quote_history" in list_provider_capabilities("marketdata_app")


@pytest.mark.parametrize(
    "provider_cls",
    [
        TiingoProvider,
        TwelveDataProvider,
        TradierProvider,
        MarketDataAppProvider,
        FinnhubProvider,
        MarketstackProvider,
        EODHDProvider,
        FMPProvider,
    ],
)
def test_raw_only_rest_adapters_reject_adjusted_history_before_transport(provider_cls):
    provider = provider_cls()
    with patch.object(provider, "_get") as get:
        with pytest.raises(ProviderResponseError, match="historical bars are raw"):
            provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 2, tzinfo=UTC),
                adjusted=True,
            )
    get.assert_not_called()


def test_twelve_data_parses_intraday_values():
    provider = TwelveDataProvider()
    payload = {
        "meta": {"symbol": "AAPL", "exchange_timezone": "America/New_York"},
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
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.TWELVE_DATA_API_KEY = "demo"
        bars = provider.fetch_ohlcv(
            "AAPL",
            Timeframe.M5,
            datetime(2024, 1, 2, 14, tzinfo=UTC),
            datetime(2024, 1, 2, 15, tzinfo=UTC),
            adjusted=False,
        )
    assert len(bars) == 1
    assert bars[0].close == 185.5
    assert bars[0].is_adjusted is False
    assert bars[0].ts == datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    assert get.call_args.kwargs["params"]["timezone"] == "UTC"


def test_twelve_data_parses_daily_exchange_local_timestamp_as_utc():
    provider = TwelveDataProvider()
    payload = {
        "meta": {"symbol": "AAPL", "exchange_timezone": "America/New_York"},
        "values": [
            {
                "datetime": "2024-01-02 16:00:00",
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
            Timeframe.D1,
            datetime(2024, 1, 2, 20, tzinfo=UTC),
            datetime(2024, 1, 3, tzinfo=UTC),
            adjusted=False,
        )

    assert len(bars) == 1
    assert bars[0].ts == datetime(2024, 1, 2, 21, tzinfo=UTC)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("datetime", "not-a-date"),
        ("open", "Infinity"),
        ("high", "NaN"),
        ("close", "not-a-number"),
        ("volume", "Infinity"),
        ("vwap", "NaN"),
    ],
)
def test_optional_ohlcv_rejects_invalid_or_nonfinite_values(field, value):
    provider = TwelveDataProvider()
    row = {
        "datetime": "2024-01-02 14:30:00",
        "open": "185.0",
        "high": "186.0",
        "low": "184.5",
        "close": "185.5",
        "volume": "1000",
        "vwap": "185.2",
    }
    row[field] = value
    payload = {
        "meta": {"symbol": "AAPL", "exchange_timezone": "America/New_York"},
        "values": [row],
    }
    with patch.object(provider, "_get", return_value=payload):
        with pytest.raises(ProviderResponseError, match="OHLCV"):
            provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 3, tzinfo=UTC),
                adjusted=False,
            )


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
            adjusted=False,
        )
    assert [(bar.open, bar.close) for bar in bars] == [(100.0, 101.0)]


def test_finnhub_invalid_candle_status_is_typed():
    provider = FinnhubProvider()
    payload = {"s": "unexpected", "t": [], "o": [], "h": [], "l": [], "c": [], "v": []}
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ),
    ):
        configured.FINNHUB_API_KEY = "demo"
        with pytest.raises(ProviderResponseError) as exc_info:
            provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 3, tzinfo=UTC),
                adjusted=False,
            )
    assert exc_info.value.provider_name == "finnhub"


def test_marketdata_app_mismatched_candle_arrays_are_typed():
    provider = MarketDataAppProvider()
    payload = {"s": "ok", "t": [1], "o": [100], "h": [], "l": [99], "c": [101], "v": [10]}
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ),
    ):
        configured.MARKETDATA_APP_API_KEY = "demo"
        with pytest.raises(ProviderResponseError) as exc_info:
            provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 3, tzinfo=UTC),
                adjusted=False,
            )
    assert exc_info.value.provider_name == "marketdata_app"


def test_finnhub_parses_documented_earnings_actual_and_estimate_fields():
    provider = FinnhubProvider()
    payload = [
        {
            "symbol": "AAPL",
            "period": "2024-01-01",
            "actual": 2.18,
            "estimate": 2.10,
            "surprise": 0.08,
            "surprisePercent": 3.81,
        }
    ]
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ),
    ):
        configured.FINNHUB_API_KEY = "demo"
        events = provider.fetch_instrument_events("AAPL")

    assert len(events) == 1
    assert events[0].eps_actual == Decimal("2.18")
    assert events[0].eps_estimate == Decimal("2.10")
    assert events[0].eps_surprise == Decimal("0.08")


def test_finnhub_parses_documented_forward_earnings_calendar():
    provider = FinnhubProvider()
    payload = {
        "earningsCalendar": [
            {
                "date": "2024-01-02",
                "symbol": "AAPL",
                "hour": "amc",
                "epsEstimate": 2.10,
                "revenueEstimate": 117000000000,
            }
        ]
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.FINNHUB_API_KEY = "demo"
        events = provider.fetch_market_events(start=date(2024, 1, 1), end=date(2024, 1, 3))

    assert len(events) == 1
    assert events[0].event_type == "earnings"
    assert events[0].effective_date == date(2024, 1, 2)
    assert events[0].raw_payload["hour"] == "amc"
    assert get.call_args.kwargs["params"] == {
        "from": "2024-01-01",
        "to": "2024-01-03",
        "token": "demo",
    }


def test_fmp_parses_documented_stable_earnings_calendar():
    provider = FMPProvider()
    payload = [
        {
            "date": "2024-01-02",
            "symbol": "AAPL",
            "epsActual": 2.18,
            "epsEstimated": 2.10,
            "revenueActual": 119000000000,
            "revenueEstimated": 117000000000,
        }
    ]
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.FMP_API_KEY = "demo"
        events = provider.fetch_market_events(start=date(2024, 1, 1), end=date(2024, 1, 3))

    assert len(events) == 1
    assert events[0].event_type == "earnings"
    assert events[0].event_key == "fmp:earnings_calendar:AAPL:2024-01-02"
    assert events[0].effective_date == date(2024, 1, 2)
    assert events[0].raw_payload["epsEstimated"] == 2.10
    assert get.call_args.kwargs["params"] == {
        "from": "2024-01-01",
        "to": "2024-01-03",
        "apikey": "demo",
    }


@pytest.mark.parametrize(
    ("provider", "payload", "operation"),
    [
        (TiingoProvider(), [{}], "search"),
        (TwelveDataProvider(), {"data": [{}]}, "search"),
        (TradierProvider(), {"securities": {"security": [{}]}}, "search"),
        (FinnhubProvider(), {"result": [{}]}, "search"),
        (MarketstackProvider(), {"pagination": {"total": 1}, "data": [{}]}, "discovery"),
        (EODHDProvider(), [{}], "discovery"),
        (FMPProvider(), [{}], "discovery"),
    ],
)
def test_optional_identity_rows_are_not_silently_dropped(provider, payload, operation):
    with patch.object(provider, "_get", return_value=payload):
        with pytest.raises(ProviderResponseError, match="required") as exc_info:
            if operation == "search":
                provider.search_instruments("Apple")
            else:
                with patch(
                    "app.providers.optional_market_data.settings.MARKETSTACK_DISCOVERY_EXCHANGE",
                    "XNAS",
                ):
                    provider.discover_universe_page("EQUITY", 0)
    assert exc_info.value.provider_name == provider.name


@pytest.mark.parametrize(
    ("provider", "payload", "operation"),
    [
        (FinnhubProvider(), [{"period": "not-a-date"}], "instrument"),
        (
            FinnhubProvider(),
            {"earningsCalendar": [{"date": "not-a-date", "symbol": "AAPL"}]},
            "market",
        ),
        (FinnhubProvider(), {"earningsCalendar": [{"date": "2024-01-02"}]}, "market"),
        (FMPProvider(), [{"date": "not-a-date", "symbol": "AAPL"}], "market"),
        (FMPProvider(), [{"date": "2024-01-02"}], "market"),
    ],
)
def test_optional_earnings_rows_are_not_silently_dropped(provider, payload, operation):
    with patch.object(provider, "_get", return_value=payload):
        with pytest.raises(ProviderResponseError):
            if operation == "instrument":
                provider.fetch_instrument_events("AAPL")
            else:
                provider.fetch_market_events(start=date(2024, 1, 1), end=date(2024, 1, 3))


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
        (
            MarketstackProvider(),
            "MARKETSTACK_API_KEY",
            {
                "data": [row],
                "pagination": {"limit": 100, "offset": 0, "count": 1, "total": 1},
            },
        ),
        (EODHDProvider(), "EODHD_API_KEY", [row]),
        (FMPProvider(), "FMP_API_KEY", [row]),
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
                adjusted=False,
            )
        assert len(bars) == 1
        assert bars[0].close == 10.5


def test_tiingo_parses_single_object_metadata_response():
    provider = TiingoProvider()
    payload = {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "exchangeCode": "NASDAQ",
        "description": "Technology company",
        "currency": "USD",
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.TIINGO_API_KEY = "demo"
        profile = provider.get_instrument_profile("AAPL")

    assert profile is not None
    assert profile.symbol == "AAPL"
    assert profile.name == "Apple Inc."
    assert profile.exchange == "NASDAQ"
    assert get.call_args.args[0] == "https://api.tiingo.com/tiingo/daily/AAPL"


@pytest.mark.parametrize(
    ("timeframe", "period"),
    [(Timeframe.W1, "w"), (Timeframe.MN, "m")],
)
def test_eodhd_uses_documented_weekly_and_monthly_periods(timeframe, period):
    provider = EODHDProvider()
    payload = [
        {
            "date": "2024-01-02",
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10.5,
            "volume": 42,
        }
    ]
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.EODHD_API_KEY = "demo"
        bars = provider.fetch_ohlcv(
            "AAPL",
            timeframe,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 2, 1, tzinfo=UTC),
            adjusted=False,
        )

    assert bars and bars[0].close == 10.5
    assert get.call_args.kwargs["params"]["period"] == period


def test_eodhd_fundamentals_uses_documented_v11_endpoint():
    provider = EODHDProvider()
    payload = {
        "General": {
            "Code": "AAPL",
            "Name": "Apple Inc.",
            "CurrencyCode": "USD",
            "Exchange": "NASDAQ",
        }
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.EODHD_API_KEY = "demo"
        profile = provider.get_instrument_profile("AAPL")

    assert profile is not None
    assert profile.symbol == "AAPL"
    assert profile.exchange == "NASDAQ"
    assert get.call_args.args[0] == ("https://eodhd.com/api/v1.1/fundamentals/AAPL.US")


def test_marketstack_follows_response_pagination_and_reserves_each_page():
    provider = MarketstackProvider()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 6, 1, tzinfo=UTC)
    first_payload = {
        "pagination": {"limit": 100, "offset": 0, "count": 100, "total": 150},
        "data": [
            {
                "date": "2024-01-02T00:00:00+0000",
                "open": "10",
                "high": "11",
                "low": "9",
                "close": "10.5",
                "volume": "42",
            }
        ],
    }
    second_payload = {
        "pagination": {"limit": 100, "offset": 100, "count": 50, "total": 150},
        "data": [
            {
                "date": "2024-05-31T00:00:00+0000",
                "open": "20",
                "high": "21",
                "low": "19",
                "close": "20.5",
                "volume": "84",
            }
        ],
    }
    with patch.object(provider, "_get", side_effect=[first_payload, second_payload]) as get:
        bars = provider.fetch_ohlcv("AAPL", Timeframe.D1, start, end, adjusted=False)

    assert get.call_count == 2
    assert get.call_args_list[0].args[1]["offset"] == 0
    assert get.call_args_list[1].args[1]["offset"] == 100
    assert [bar.close for bar in bars] == [10.5, 20.5]
    assert estimate_marketstack_ohlcv_request_count(Timeframe.D1, start, end) == 2
    assert estimate_marketstack_latest_ohlcv_request_count(Timeframe.D1, 100) == 2


def test_marketstack_invalid_pagination_is_typed_instead_of_truncating_history():
    provider = MarketstackProvider()
    with patch.object(
        provider,
        "_get",
        return_value={"pagination": {"offset": 0, "count": "many", "total": 1}, "data": []},
    ):
        with pytest.raises(ProviderResponseError) as exc_info:
            provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 2, 1, tzinfo=UTC),
                adjusted=False,
            )
    assert exc_info.value.provider_name == "marketstack"


@pytest.mark.parametrize(
    "pagination",
    [
        {"offset": True, "count": 1, "total": 1},
        {"offset": 0, "count": 1.5, "total": 1},
        {"offset": 0, "count": 1, "total": "1"},
        {"offset": 0, "count": 1, "total": 0},
    ],
)
def test_marketstack_pagination_counters_require_strict_integer_metadata(pagination):
    provider = MarketstackProvider()
    payload = {
        "pagination": pagination,
        "data": [
            {
                "date": "2024-01-02T00:00:00+0000",
                "open": "10",
                "high": "11",
                "low": "9",
                "close": "10.5",
                "volume": "42",
            }
        ],
    }
    with patch.object(provider, "_get", return_value=payload):
        with pytest.raises(ProviderResponseError, match="pagination"):
            provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 2, 1, tzinfo=UTC),
                adjusted=False,
            )


def test_marketstack_discovery_requires_explicit_exchange_and_preserves_scope():
    provider = MarketstackProvider()
    with patch("app.providers.optional_market_data.settings") as configured:
        configured.MARKETSTACK_DISCOVERY_EXCHANGE = ""
        with pytest.raises(ProviderNotConfiguredError, match="MARKETSTACK_DISCOVERY_EXCHANGE"):
            provider.discover_universe_page("EQUITY", 0)

    payload = {
        "pagination": {"limit": 1000, "offset": 0, "count": 1, "total": 1},
        "data": [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "exchange": "XNAS",
                "currency": "USD",
            }
        ],
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch.object(provider, "_get", return_value=payload) as get,
    ):
        configured.MARKETSTACK_DISCOVERY_EXCHANGE = "xnas"
        page = provider.discover_universe_page("EQUITY", 0)

    assert page["quotes"][0]["exchange"] == "XNAS"
    assert get.call_args.args[1]["exchange"] == "XNAS"


def test_fmp_uses_current_stable_history_endpoint():
    provider = FMPProvider()
    payload = [
        {
            "date": "2024-01-02",
            "open": 10,
            "high": 11,
            "low": 9,
            "close": 10.5,
            "volume": 42,
        }
    ]
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.FMP_API_KEY = "demo"
        rows = provider.fetch_ohlcv(
            "AAPL",
            Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 3, tzinfo=UTC),
            adjusted=False,
        )

    assert rows and rows[0].close == 10.5
    assert get.call_args.args[0] == (
        "https://financialmodelingprep.com/stable/historical-price-eod/full"
    )
    assert get.call_args.kwargs["params"]["symbol"] == "AAPL"


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
            adjusted=False,
        )

    assert provider.base_url == "https://api.marketdata.app/v1"
    assert get.call_args.args[0] == "https://api.marketdata.app/v1/stocks/candles/D/AAPL/"
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

    assert get.call_args.args[0] == "https://api.marketdata.app/v1/stocks/candles/D/AAPL/"


def test_marketdata_app_fetches_account_usage_from_unversioned_user_endpoint():
    provider = MarketDataAppProvider()
    response = _response(
        {
            "x-ratelimit-requests-limit": 10000,
            "x-ratelimit-requests-remaining": 9876,
            "x-options-data-permissions": "OPRA data delayed 15 minutes",
        }
    )
    response.status_code = 200
    response.headers = {
        "X-Api-Ratelimit-Limit": "10000",
        "X-Api-Ratelimit-Remaining": "9876",
        "X-Api-Ratelimit-Consumed": "0",
        "X-Api-Ratelimit-Reset": "1789306200",
        "Authorization": "Bearer must-not-be-retained",
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=response,
        ) as get,
    ):
        configured.MARKETDATA_APP_API_KEY = "demo"
        usage = provider.fetch_account_usage()

    assert usage is not None
    assert usage.provider == "marketdata_app"
    assert usage.unit == "credits"
    assert usage.limit == 10000
    assert usage.remaining == 9876
    assert usage.consumed == 0
    assert usage.reset_at == datetime.fromtimestamp(1789306200, tz=UTC)
    assert usage.options_data_permissions == "OPRA data delayed 15 minutes"
    assert get.call_args.args[0] == "https://api.marketdata.app/user/"
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer demo"}


def test_marketdata_app_account_usage_honors_documented_not_found_response():
    provider = MarketDataAppProvider()
    response = MagicMock(status_code=404, headers={})
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=response,
        ),
    ):
        configured.MARKETDATA_APP_API_KEY = "demo"
        assert provider.fetch_account_usage() is None
    response.raise_for_status.assert_not_called()


def test_marketdata_app_account_usage_rejects_missing_documented_fields():
    provider = MarketDataAppProvider()
    response = _response({})
    response.status_code = 200
    response.headers = {}
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=response,
        ),
    ):
        configured.MARKETDATA_APP_API_KEY = "demo"
        with pytest.raises(ProviderResponseError, match="account-usage fields"):
            provider.fetch_account_usage()


@pytest.mark.parametrize(
    "field",
    ["x-ratelimit-requests-limit", "x-ratelimit-requests-remaining"],
)
def test_marketdata_app_account_usage_rejects_fractional_counters(field):
    provider = MarketDataAppProvider()
    response = _response({field: 10.5, "x-options-data-permissions": ""})
    response.status_code = 200
    response.headers = {}
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=response,
        ),
    ):
        configured.MARKETDATA_APP_API_KEY = "demo"
        with pytest.raises(ProviderResponseError, match="invalid account"):
            provider.fetch_account_usage()


def test_marketdata_app_parses_documented_option_expirations():
    provider = MarketDataAppProvider()
    payload = {
        "s": "ok",
        "expirations": ["2024-01-19", "2024-01-05", "2024-01-19"],
        "updated": 1700000000,
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.MARKETDATA_APP_API_KEY = "demo"
        expirations = provider.list_option_expirations("AAPL")

    assert expirations == [date(2024, 1, 5), date(2024, 1, 19)]
    assert get.call_args.args[0] == "https://api.marketdata.app/v1/options/expirations/AAPL/"
    assert get.call_args.kwargs["headers"] == {"Authorization": "Bearer demo"}


def test_marketdata_app_parses_parallel_option_chain_arrays_and_greeks():
    provider = MarketDataAppProvider()
    updated = int(datetime(2024, 1, 2, 21, tzinfo=UTC).timestamp())
    payload = {
        "s": "ok",
        "optionSymbol": ["AAPL240119C00100000"],
        "underlying": ["AAPL"],
        "expiration": [int(datetime(2024, 1, 19, 21, tzinfo=UTC).timestamp())],
        "side": ["call"],
        "strike": [100],
        "bid": [5.15],
        "ask": [5.25],
        "mid": [5.2],
        "last": [5.25],
        "volume": [977],
        "openInterest": [61289],
        "iv": [0.3468],
        "delta": [0.347],
        "gamma": [0.015],
        "theta": [-0.05],
        "vega": [0.264],
        "updated": [updated],
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.MARKETDATA_APP_API_KEY = "demo"
        contracts = provider.fetch_option_chain("AAPL", expiration=date(2024, 1, 19))

    assert len(contracts) == 1
    contract = contracts[0]
    assert contract.provider_symbol == "AAPL240119C00100000"
    assert contract.expiry_date == date(2024, 1, 19)
    assert contract.strike == Decimal("100")
    assert contract.right == "call"
    assert contract.mark == Decimal("5.2")
    assert contract.delta == Decimal("0.347")
    assert contract.observed_at == datetime(2024, 1, 2, 21, tzinfo=UTC)
    assert get.call_args.args[0] == "https://api.marketdata.app/v1/options/chain/AAPL/"
    assert get.call_args.kwargs["params"] == {"expiration": "2024-01-19"}


def test_marketdata_app_mismatched_option_arrays_are_typed():
    provider = MarketDataAppProvider()
    payload = {
        "s": "ok",
        "optionSymbol": ["AAPL240119C00100000"],
        "underlying": ["AAPL"],
        "expiration": [1705698000],
        "side": ["call"],
        "strike": [100],
        "bid": [],
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ),
    ):
        configured.MARKETDATA_APP_API_KEY = "demo"
        with pytest.raises(ProviderResponseError, match="mismatched option bid array"):
            provider.fetch_option_chain("AAPL", expiration=date(2024, 1, 19))


def test_marketdata_app_applies_reviewed_option_chain_symbol_bound():
    provider = MarketDataAppProvider()
    payload = {
        "s": "ok",
        "optionSymbol": ["AAPL240119C00100000", "AAPL240119P00100000"],
        "underlying": ["AAPL", "AAPL"],
        "expiration": [1705698000, 1705698000],
        "side": ["call", "put"],
        "strike": [100, 100],
        "updated": [1704229200, 1704229200],
    }
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ) as get,
    ):
        configured.MARKETDATA_APP_API_KEY = "demo"
        contracts = provider.fetch_option_chain("AAPL", expiration=date(2024, 1, 19), max_symbols=4)

    assert len(contracts) == 2
    assert get.call_args.kwargs["params"] == {
        "expiration": "2024-01-19",
        "strikeLimit": 2,
    }


def test_marketdata_app_rejects_option_chain_bound_below_two_symbols():
    provider = MarketDataAppProvider()
    with patch("app.providers.optional_market_data.settings") as configured:
        configured.MARKETDATA_APP_API_KEY = "demo"
        with pytest.raises(ProviderResponseError, match="symbol bound"):
            provider.fetch_option_chain("AAPL", max_symbols=1)


def test_marketdata_app_parses_historical_option_quote_arrays():
    provider = MarketDataAppProvider()
    updated = int(datetime(2024, 1, 2, 21, tzinfo=UTC).timestamp())
    payload = {
        "s": "ok",
        "optionSymbol": ["AAPL240119C00100000"],
        "updated": [updated],
        "bid": [5.15],
        "ask": [5.25],
        "mid": [5.2],
        "last": [5.25],
        "volume": [977],
        "openInterest": [61289],
        # MarketData.app documents historical Greeks as null.
        "iv": [None],
        "delta": [None],
        "gamma": [None],
        "theta": [None],
        "vega": [None],
    }
    with patch.object(provider, "_get", return_value=payload) as get:
        points = provider.fetch_option_quote_history(
            "AAPL240119C00100000",
            start=datetime(2024, 1, 1, tzinfo=UTC),
            end=datetime(2024, 1, 3, tzinfo=UTC),
        )

    assert len(points) == 1
    point = points[0]
    assert point.provider_symbol == "AAPL240119C00100000"
    assert point.observed_at == datetime(2024, 1, 2, 21, tzinfo=UTC)
    assert point.bid == Decimal("5.15")
    assert point.mark == Decimal("5.2")
    assert point.open_interest == Decimal("61289")
    assert point.delta is None
    assert get.call_args.args[0] == "options/quotes/AAPL240119C00100000/"
    assert get.call_args.args[1] == {
        "from": "2024-01-01",
        "to": "2024-01-03",
    }


def test_marketdata_app_mismatched_option_quote_arrays_are_typed():
    provider = MarketDataAppProvider()
    payload = {
        "s": "ok",
        "optionSymbol": ["AAPL240119C00100000"],
        "updated": [1704229200],
        "bid": [5.15, 5.2],
    }
    with patch.object(provider, "_get", return_value=payload):
        with pytest.raises(ProviderResponseError, match="mismatched option-quote bid array"):
            provider.fetch_option_quote_history(
                "AAPL240119C00100000",
                start=datetime(2024, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 3, tzinfo=UTC),
            )


def test_tradier_parses_documented_nested_history_and_singleton_quote_search_shapes():
    provider = TradierProvider()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 3, tzinfo=UTC)
    history = {
        "history": {
            "day": {
                "date": "2024-01-02",
                "open": "100",
                "high": "102",
                "low": "99",
                "close": "101",
                "volume": "1234",
            }
        }
    }
    with patch.object(provider, "_get", return_value=history):
        bars = provider.fetch_ohlcv("AAPL", Timeframe.D1, start, end, adjusted=False)
    assert len(bars) == 1
    assert bars[0].close == 101.0

    with patch.object(
        provider,
        "_get",
        return_value={"quotes": {"quote": {"symbol": "AAPL", "last": "101.5"}}},
    ):
        assert provider.get_current_price("AAPL") == 101.5

    with patch.object(
        provider,
        "_get",
        return_value={
            "securities": {
                "security": {
                    "symbol": "AAPL",
                    "description": "Apple Inc.",
                    "exchange": "Q",
                    "type": "stock",
                }
            }
        },
    ):
        rows = provider.search_instruments("Apple")
    assert rows and rows[0].symbol == "AAPL"
    assert rows[0].name == "Apple Inc."


def test_tradier_invalid_nested_wrapper_is_typed():
    provider = TradierProvider()
    with patch.object(provider, "_get", return_value={"history": {"day": "invalid"}}):
        with pytest.raises(ProviderResponseError) as exc_info:
            provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 3, tzinfo=UTC),
                adjusted=False,
            )
    assert exc_info.value.provider_name == "tradier"


def test_tradier_mixed_nested_rows_are_typed():
    provider = TradierProvider()
    payload = {"history": {"day": [{"date": "2024-01-02"}, "invalid"]}}
    with patch.object(provider, "_get", return_value=payload):
        with pytest.raises(ProviderResponseError) as exc_info:
            provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 3, tzinfo=UTC),
                adjusted=False,
            )
    assert exc_info.value.provider_name == "tradier"


def test_tradier_invalid_option_expiration_is_typed():
    provider = TradierProvider()
    with patch.object(
        provider,
        "_get",
        return_value={"expirations": {"date": ["2024-01-19", "not-a-date"]}},
    ):
        with pytest.raises(ProviderResponseError) as exc_info:
            provider.list_option_expirations("AAPL")
    assert exc_info.value.provider_name == "tradier"


@pytest.mark.parametrize(
    "row",
    [
        {"expiration_date": "2024-01-19", "option_type": "call", "strike": "100"},
        {
            "symbol": "AAPL240119C00100000",
            "expiration_date": "2024-01-19",
            "option_type": "call",
            "strike": "0",
        },
        {
            "symbol": "AAPL240119C00100000",
            "expiration_date": "2024-01-19",
            "option_type": "call",
            "strike": "100",
            "greeks": {"delta": "NaN"},
        },
        {
            "symbol": "AAPL240119C00100000",
            "expiration_date": "2024-01-19",
            "option_type": "call",
            "strike": "100",
            "greeks": "invalid",
        },
    ],
)
def test_tradier_option_chain_rejects_malformed_contracts(row):
    provider = TradierProvider()
    with patch.object(provider, "_get", return_value={"options": {"option": [row]}}):
        with pytest.raises(ProviderResponseError, match="option") as exc_info:
            provider.fetch_option_chain("AAPL", expiration=date(2024, 1, 19))
    assert exc_info.value.provider_name == "tradier"


def test_optional_documented_row_endpoints_reject_malformed_containers():
    calls = (
        ("tiingo", TiingoProvider(), {"data": "invalid"}, "history"),
        ("twelve_data", TwelveDataProvider(), {"values": "invalid"}, "history"),
        ("eodhd", EODHDProvider(), {"data": "invalid"}, "history"),
        ("fmp", FMPProvider(), {"historical": "invalid"}, "history"),
        (
            "finnhub",
            FinnhubProvider(),
            {"earningsCalendar": "invalid"},
            "calendar",
        ),
        (
            "marketstack",
            MarketstackProvider(),
            {
                "data": "invalid",
                "pagination": {"offset": 0, "count": 0, "total": 0},
            },
            "discovery",
        ),
    )
    for provider_name, provider, payload, operation in calls:
        with patch.object(provider, "_get", return_value=payload):
            with pytest.raises(ProviderResponseError) as exc_info:
                if operation == "history":
                    provider.fetch_ohlcv(
                        "AAPL",
                        Timeframe.D1,
                        datetime(2024, 1, 1, tzinfo=UTC),
                        datetime(2024, 1, 3, tzinfo=UTC),
                        adjusted=False,
                    )
                elif operation == "calendar":
                    provider.fetch_market_events(start=date(2024, 1, 1), end=date(2024, 1, 3))
                else:
                    with patch(
                        "app.providers.optional_market_data.settings.MARKETSTACK_DISCOVERY_EXCHANGE",
                        "XNAS",
                    ):
                        provider.discover_universe_page("EQUITY", 0)
        assert exc_info.value.provider_name == provider_name


def test_tradier_parses_option_expirations_and_chain_greeks():
    provider = TradierProvider()
    expiration = date(2024, 1, 19)
    with patch.object(
        provider,
        "_get",
        side_effect=[
            {"expirations": {"date": [expiration.isoformat()]}},
            {
                "options": {
                    "option": [
                        {
                            "symbol": "AAPL240119C00100000",
                            "underlying": "AAPL",
                            "expiration_date": expiration.isoformat(),
                            "option_type": "call",
                            "strike": "100",
                            "contract_size": "100",
                            "bid": "2.00",
                            "ask": "2.20",
                            "last": "2.10",
                            "volume": "42",
                            "open_interest": "1000",
                            "greeks": {
                                "mid_iv": "0.25",
                                "delta": "0.70",
                                "gamma": "0.03",
                                "theta": "-0.02",
                                "vega": "0.11",
                                "rho": "0.04",
                            },
                        }
                    ]
                }
            },
        ],
    ) as get:
        expirations = provider.list_option_expirations("AAPL")
        contracts = provider.fetch_option_chain("AAPL", expiration=expirations[0])

    assert expirations == [expiration]
    assert len(contracts) == 1
    contract = contracts[0]
    assert contract.provider_symbol == "AAPL240119C00100000"
    assert contract.right == "call"
    assert contract.mark == Decimal("2.10")
    assert contract.implied_vol == Decimal("0.25")
    assert contract.delta == Decimal("0.70")
    assert get.call_args_list[1].args[0].endswith("markets/options/chains")
    assert get.call_args_list[1].args[1]["greeks"] == "true"


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


@pytest.mark.parametrize(
    ("provider", "setting", "payload"),
    [
        (
            TwelveDataProvider(),
            "TWELVE_DATA_API_KEY",
            {"status": "error", "message": "invalid symbol"},
        ),
        (
            FMPProvider(),
            "FMP_API_KEY",
            {"Error Message": "legacy endpoint is unavailable"},
        ),
        (
            MarketDataAppProvider(),
            "MARKETDATA_APP_API_KEY",
            {"s": "error", "errmsg": "invalid token"},
        ),
    ],
)
def test_http_success_error_envelopes_do_not_become_empty_data(provider, setting, payload):
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response(payload),
        ),
    ):
        setattr(configured, setting, "demo")
        with pytest.raises(ProviderResponseError):
            provider.get_current_price("AAPL")


def test_malformed_json_is_a_typed_provider_failure():
    provider = TwelveDataProvider()
    response = _response({})
    response.json.side_effect = ValueError("not json")
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch("app.providers.optional_market_data.httpx.get", return_value=response),
    ):
        configured.TWELVE_DATA_API_KEY = "demo"
        with pytest.raises(ProviderResponseError) as exc_info:
            provider.get_current_price("AAPL")
    assert exc_info.value.provider_name == "twelve_data"


def test_scalar_json_success_payload_is_a_typed_provider_failure():
    provider = TwelveDataProvider()
    response = _response("not an object or array")
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch("app.providers.optional_market_data.httpx.get", return_value=response),
    ):
        configured.TWELVE_DATA_API_KEY = "demo"
        with pytest.raises(ProviderResponseError) as exc_info:
            provider.get_current_price("AAPL")
    assert exc_info.value.provider_name == "twelve_data"


def test_http_success_rate_limit_envelope_is_typed_capacity_failure():
    provider = FinnhubProvider()
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch(
            "app.providers.optional_market_data.httpx.get",
            return_value=_response({"error": "API rate limit exceeded"}),
        ),
    ):
        configured.FINNHUB_API_KEY = "demo"
        with pytest.raises(ProviderRateLimitError) as exc_info:
            provider.get_instrument_profile("AAPL")
    assert exc_info.value.provider_name == "finnhub"


def test_http_status_failure_redacts_query_credentials_and_preserves_status():
    provider = EODHDProvider()
    response = MagicMock(status_code=403, headers={})
    request = httpx.Request(
        "GET", "https://eodhd.com/api/fundamentals/AAPL.US?api_token=demo-secret"
    )
    failure = httpx.HTTPStatusError(
        "Client error '403 Forbidden' for url 'https://eodhd.com/api/fundamentals/AAPL.US?api_token=demo-secret'",
        request=request,
        response=response,
    )
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch("app.providers.optional_market_data.httpx.get", side_effect=failure),
    ):
        configured.EODHD_API_KEY = "demo-secret"
        with pytest.raises(ProviderResponseError) as exc_info:
            provider.get_instrument_profile("AAPL")
    assert exc_info.value.status_code == 403
    assert "demo-secret" not in str(exc_info.value)
    assert "<redacted>" in str(exc_info.value)


def test_http_status_rate_limit_preserves_reset_header():
    provider = FinnhubProvider()
    response = MagicMock(
        status_code=429,
        headers={"Retry-After": "7", "Authorization": "must-not-be-retained"},
    )
    request = httpx.Request("GET", "https://finnhub.io/api/v1/profile2?token=demo-secret")
    failure = httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch("app.providers.optional_market_data.httpx.get", side_effect=failure),
    ):
        configured.FINNHUB_API_KEY = "demo-secret"
        with pytest.raises(ProviderRateLimitError) as exc_info:
            provider.get_instrument_profile("AAPL")
    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_at is not None
    assert "demo-secret" not in str(exc_info.value)
    assert exc_info.value.headers == {"Retry-After": "7"}


def test_marketdata_app_rate_limit_parses_native_reset_header():
    provider = MarketDataAppProvider()
    response = MagicMock(
        status_code=429,
        headers={
            "X-Api-Ratelimit-Reset": "1700000000",
            "X-Api-Ratelimit-Remaining": "0",
            "Authorization": "Bearer must-not-be-retained",
        },
    )
    request = httpx.Request("GET", "https://api.marketdata.app/v1/stocks/candles/AAPL/")
    failure = httpx.HTTPStatusError("429 Too Many Requests", request=request, response=response)
    with (
        patch("app.providers.optional_market_data.settings") as configured,
        patch("app.providers.optional_market_data.httpx.get", side_effect=failure),
    ):
        configured.MARKETDATA_APP_API_KEY = "marketdata-secret"
        with pytest.raises(ProviderRateLimitError) as exc_info:
            provider.fetch_ohlcv(
                "AAPL",
                Timeframe.D1,
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 2, tzinfo=UTC),
                adjusted=False,
            )
    assert exc_info.value.status_code == 429
    assert exc_info.value.retry_at == datetime.fromtimestamp(1700000000, tz=UTC)
    assert exc_info.value.headers == {
        "X-Api-Ratelimit-Reset": "1700000000",
        "X-Api-Ratelimit-Remaining": "0",
    }
