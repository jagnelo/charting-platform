from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.models.ohlcv import Timeframe
from app.providers.nasdaq import NasdaqProvider


def _response(rows, *, total=None):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "data": {
            "totalRecords": total if total is not None else len(rows),
            "tradesTable": {"rows": rows},
        }
    }
    return response


def test_nasdaq_parses_currency_and_volume_fields_and_bounds_dates():
    rows = [
        {
            "date": "01/04/2024",
            "open": "$102.10",
            "high": "$104.00",
            "low": "$101.50",
            "close": "$103.25",
            "volume": "1,234,567",
        },
        {
            "date": "01/03/2024",
            "open": "$100.00",
            "high": "$102.00",
            "low": "$99.50",
            "close": "$101.00",
            "volume": "987,654",
        },
        {
            "date": "01/02/2024",
            "open": "--",
            "high": "$99.00",
            "low": "$98.00",
            "close": "$98.50",
            "volume": "100",
        },
    ]
    with patch("app.providers.nasdaq.httpx.get", return_value=_response(rows)) as get:
        bars = NasdaqProvider().fetch_ohlcv(
            "RSP",
            Timeframe.D1,
            datetime(2024, 1, 3, tzinfo=UTC),
            datetime(2024, 1, 5, tzinfo=UTC),
        )

    assert [bar.ts.date().isoformat() for bar in bars] == ["2024-01-03", "2024-01-04"]
    assert float(bars[0].close) == 101.0
    assert float(bars[0].volume) == 987654.0
    assert all(bar.is_adjusted for bar in bars)
    assert get.call_args.kwargs["params"]["assetclass"] == "stocks"


def test_nasdaq_retries_etf_asset_class_when_stock_route_is_empty():
    empty = _response([])
    etf = _response(
        [
            {
                "date": "01/04/2024",
                "open": "$100",
                "high": "$101",
                "low": "$99",
                "close": "$100.5",
                "volume": "10,000",
            }
        ]
    )
    with patch("app.providers.nasdaq.httpx.get", side_effect=[empty, etf]) as get:
        bars = NasdaqProvider().fetch_ohlcv(
            "SPY",
            Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 5, tzinfo=UTC),
            adjusted=True,
        )

    assert len(bars) == 1
    assert get.call_count == 2
    assert get.call_args_list[1].kwargs["params"]["assetclass"] == "etf"


def test_nasdaq_declines_raw_and_intraday_requests_without_mislabeling_them():
    provider = NasdaqProvider()
    start = datetime(2024, 1, 1, tzinfo=UTC)
    end = datetime(2024, 1, 5, tzinfo=UTC)
    with patch("app.providers.nasdaq.httpx.get") as get:
        assert provider.fetch_ohlcv("UNIQUE-SPY", Timeframe.D1, start, end, adjusted=False) == []
        assert provider.fetch_ohlcv("UNIQUE-SPY", Timeframe.H1, start, end) == []
    get.assert_not_called()


def test_nasdaq_widens_historical_end_to_today_for_one_day_repairs():
    response = _response(
        [
            {
                "date": "12/30/2025",
                "open": "$100",
                "high": "$101",
                "low": "$99",
                "close": "$100.5",
                "volume": "10,000",
            },
            {
                "date": "01/02/2026",
                "open": "$101",
                "high": "$102",
                "low": "$100",
                "close": "$101.5",
                "volume": "11,000",
            },
        ]
    )
    with patch("app.providers.nasdaq.httpx.get", return_value=response) as get:
        bars = NasdaqProvider().fetch_ohlcv(
            "QQQ",
            Timeframe.D1,
            datetime(2025, 12, 30, tzinfo=UTC),
            datetime(2025, 12, 31, tzinfo=UTC),
        )

    assert [bar.ts.date().isoformat() for bar in bars] == ["2025-12-30"]
    assert get.call_args.kwargs["params"]["todate"] >= datetime.now(UTC).strftime("%Y-%m-%d")


def test_nasdaq_widens_fromdate_for_single_session_repair_boundary():
    response = _response(
        [
            {
                "date": "08/12/2026",
                "open": "$770",
                "high": "$775",
                "low": "$769",
                "close": "$772.49",
                "volume": "33,179,130",
            }
        ]
    )
    with patch("app.providers.nasdaq.httpx.get", return_value=response) as get:
        bars = NasdaqProvider().fetch_ohlcv(
            "SPY-CACHE",
            Timeframe.D1,
            datetime(2026, 8, 12, tzinfo=UTC),
            datetime(2026, 8, 13, tzinfo=UTC),
            adjusted=True,
        )

    assert [bar.ts.date().isoformat() for bar in bars] == ["2026-08-12"]
    assert get.call_args.kwargs["params"]["fromdate"] == "2026-08-09"


def test_nasdaq_history_cache_keeps_distinct_start_boundaries():
    response = _response(
        [
            {
                "date": "08/12/2026",
                "open": "$770",
                "high": "$775",
                "low": "$769",
                "close": "$772.49",
                "volume": "33,179,130",
            }
        ]
    )
    with patch("app.providers.nasdaq.httpx.get", return_value=response) as get:
        provider = NasdaqProvider()
        provider.fetch_ohlcv(
            "SPY",
            Timeframe.D1,
            datetime(2026, 8, 12, tzinfo=UTC),
            datetime(2026, 8, 13, tzinfo=UTC),
        )
        provider.fetch_ohlcv(
            "SPY",
            Timeframe.D1,
            datetime(2026, 8, 1, tzinfo=UTC),
            datetime(2026, 8, 13, tzinfo=UTC),
        )

    assert get.call_count == 2


def test_nasdaq_is_registered_as_price_and_quote_provider():
    from app.providers.registry import get_price_history_provider, get_quote_provider

    assert get_price_history_provider("nasdaq").name == "nasdaq"
    assert get_quote_provider("nasdaq").name == "nasdaq"
