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
    assert "instrument_metadata" in list_provider_capabilities("finnhub")
    assert "instrument_search" in list_provider_capabilities("tiingo")
    assert "universe_discovery" in list_provider_capabilities("eodhd")
    assert "instrument_events" in list_provider_capabilities("finnhub")
    assert "market_events" in list_provider_capabilities("finnhub")


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
        )

    assert len(bars) == 1
    assert bars[0].ts == datetime(2024, 1, 2, 21, tzinfo=UTC)


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
    assert get.call_args.args[0] == (
        "https://eodhd.com/api/v1.1/fundamentals/AAPL.US"
    )


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
        bars = provider.fetch_ohlcv("AAPL", Timeframe.D1, start, end)

    assert get.call_count == 2
    assert get.call_args_list[0].args[1]["offset"] == 0
    assert get.call_args_list[1].args[1]["offset"] == 100
    assert [bar.close for bar in bars] == [10.5, 20.5]
    assert estimate_marketstack_ohlcv_request_count(Timeframe.D1, start, end) == 2
    assert estimate_marketstack_latest_ohlcv_request_count(Timeframe.D1, 100) == 2


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
        bars = provider.fetch_ohlcv("AAPL", Timeframe.D1, start, end)
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
    response = MagicMock(status_code=429, headers={"Retry-After": "7"})
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
