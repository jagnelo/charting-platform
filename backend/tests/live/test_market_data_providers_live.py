"""Bounded, opt-in provider probes.

These tests perform one deliberately small read per provider and assert a
provider-native response shape. They are never part of ordinary unit runs.
Missing credentials are failures when live mode is explicitly enabled, not
silently skipped evidence.
"""

from __future__ import annotations

import os
from datetime import UTC, date, datetime, timedelta

import pytest

from app.models.ohlcv import Timeframe
from app.providers.alpaca import AlpacaProvider
from app.providers.alpha_vantage import AlphaVantageProvider
from app.providers.binance import BinanceProvider
from app.providers.coingecko import CoinGeckoProvider
from app.providers.crypto_market_data import CoinbaseProvider, KrakenProvider
from app.providers.edgar import EdgarProvider
from app.providers.finra import FINRAProvider
from app.providers.finra_otc_directory import FINRAOTCDirectoryProvider
from app.providers.fred import FREDProvider
from app.providers.massive import MassiveProvider
from app.providers.nasdaq import NasdaqProvider
from app.providers.openfigi import OpenFigiProvider
from app.providers.optional_market_data import (
    EODHDProvider,
    FinnhubProvider,
    FMPProvider,
    MarketDataAppProvider,
    MarketstackProvider,
    TiingoProvider,
    TradierProvider,
    TwelveDataProvider,
)

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1",
        reason="Set RUN_LIVE_PROVIDER_TESTS=1 to run the external provider matrix.",
    ),
]


def _bounds() -> tuple[datetime, datetime]:
    end = datetime.now(UTC)
    return end - timedelta(days=5), end


def _require(*names: str) -> None:
    missing = [name for name in names if not os.getenv(name)]
    if missing:
        pytest.fail(f"missing live provider credentials: {', '.join(missing)}")


def test_openfigi_keyless_mapping():
    rows = OpenFigiProvider().fetch_stable_identifiers("SPY", exchange_code="US")
    assert rows and any(row.identifier_type == "COMPOSITE_FIGI" for row in rows)


def test_sec_edgar_keyless_profile():
    _require("EDGAR_USER_AGENT")
    profile = EdgarProvider().get_instrument_profile("AAPL")
    assert profile is not None and profile.name and profile.extra.get("cik")


def test_sec_edgar_full_ticker_exchange_directory_pagination_is_complete():
    """Fetch the official SEC directory once and prove local page completion."""

    _require("EDGAR_USER_AGENT")
    provider = EdgarProvider()
    rows: list[dict] = []
    offset = 0
    declared_total: int | None = None
    while True:
        page = provider.discover_universe_page("EQUITY", offset)
        page_rows = page["quotes"]
        assert page_rows
        if declared_total is None:
            declared_total = page["total"]
        assert page["total"] == declared_total
        rows.extend(page_rows)
        offset += len(page_rows)
        if offset >= declared_total:
            break
        assert len(page_rows) > 0

    assert declared_total == len(rows)
    assert len({(row["symbol"], row["exchange"], row.get("sec_cik")) for row in rows}) == len(rows)


def test_nasdaq_trader_keyless_directory():
    provider = NasdaqProvider()
    equities = provider.discover_universe_page("EQUITY", 0)
    etfs = provider.discover_universe_page("ETF", 0)
    assert equities["quotes"] and etfs["quotes"]
    assert equities["source_files"] == ["nasdaqlisted", "otherlisted"]
    assert all(row["status"] == "active" for row in equities["quotes"][:10])
    assert all(not row["symbol"].startswith("FILE CREATION") for row in equities["quotes"])
    if equities["total"] > 1000:
        next_page = provider.discover_universe_page("EQUITY", 1000)
        assert next_page["quotes"] and next_page["quotes"][0]["symbol"] != equities["quotes"][0]["symbol"]


def test_nasdaq_trader_full_directory_pagination_is_complete():
    """Fetch both official directory files once and prove page completion locally."""

    provider = NasdaqProvider()
    for quote_type in ("EQUITY", "ETF"):
        rows: list[dict] = []
        offset = 0
        declared_total: int | None = None
        while True:
            page = provider.discover_universe_page(quote_type, offset)
            assert page["source_files"] == ["nasdaqlisted", "otherlisted"]
            if declared_total is None:
                declared_total = page["total"]
            assert page["total"] == declared_total
            page_rows = page["quotes"]
            assert page_rows
            rows.extend(page_rows)
            next_offset = page.get("next_offset")
            if next_offset is None:
                break
            assert next_offset > offset
            assert len(rows) <= declared_total
            offset = next_offset

        assert declared_total == len(rows)
        assert len({(row["symbol"], row["exchange_mic"], row["quoteType"]) for row in rows}) == len(rows)


def test_binance_keyless_crypto_history():
    start, end = _bounds()
    rows = BinanceProvider().fetch_latest_ohlcv("BTC-USD", Timeframe.D1, 1)
    assert rows and rows[-1].close > 0


def test_coinbase_keyless_crypto_history():
    rows = CoinbaseProvider().fetch_latest_ohlcv("BTC-USD", Timeframe.D1, 1)
    assert rows and rows[-1].close > 0


def test_kraken_keyless_crypto_history():
    rows = KrakenProvider().fetch_latest_ohlcv("BTC-USD", Timeframe.D1, 1)
    assert rows and rows[-1].close > 0


def test_alpaca_credentialed_history():
    _require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    start, end = _bounds()
    rows = AlpacaProvider().fetch_ohlcv("AAPL", Timeframe.D1, start, end)
    assert rows and rows[-1].close > 0


def test_massive_credentialed_reference():
    _require("MASSIVE_API_KEY")
    rows = MassiveProvider().search_instruments("AAPL", limit=1)
    assert rows and rows[0].symbol == "AAPL"


def test_alpha_vantage_credentialed_daily():
    _require("ALPHA_VANTAGE_API_KEY")
    start, end = _bounds()
    rows = AlphaVantageProvider().fetch_ohlcv("AAPL", Timeframe.D1, start, end)
    assert rows and rows[-1].close > 0


def test_coingecko_credentialed_search():
    _require("COINGECKO_API_KEY")
    rows = CoinGeckoProvider().search_instruments("bitcoin", limit=1)
    assert rows and rows[0].symbol == "BTC-USD"


def test_fred_credentialed_series():
    _require("FRED_API_KEY")
    start, end = _bounds()
    rows = FREDProvider().fetch_ohlcv("^IRX", Timeframe.D1, start, end)
    assert rows


def test_finra_credentialed_short_interest():
    _require("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET")
    rows = FINRAProvider().fetch_short_interest("AAPL")
    assert isinstance(rows, list)


def test_finra_credentialed_otc_daily_list():
    _require("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET")
    end = date.today()
    rows = FINRAProvider().fetch_market_events(start=end - timedelta(days=7), end=end)
    assert isinstance(rows, list)
    for row in rows:
        assert row.event_key.startswith("finra:otc_daily_list:")


def test_finra_otc_directory_credentialed_source():
    """Prove the operator-approved complete OTC source returns a bounded page."""

    _require("FINRA_OTC_SYMBOL_DIRECTORY_URL")
    page = FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0)
    assert page["quotes"]
    assert page["total"] >= len(page["quotes"])
    assert page["source_files"] == [os.environ["FINRA_OTC_SYMBOL_DIRECTORY_URL"].strip()]
    assert all(row["exchange"] == "OTC" for row in page["quotes"])


@pytest.mark.parametrize(
    ("provider", "credentials", "symbol"),
    [
        (TiingoProvider(), ("TIINGO_API_KEY",), "AAPL"),
        (TwelveDataProvider(), ("TWELVE_DATA_API_KEY",), "AAPL"),
        (FinnhubProvider(), ("FINNHUB_API_KEY",), "AAPL"),
        (MarketstackProvider(), ("MARKETSTACK_API_KEY",), "AAPL"),
        (EODHDProvider(), ("EODHD_API_KEY",), "AAPL"),
        (FMPProvider(), ("FMP_API_KEY",), "AAPL"),
        (TradierProvider(), ("TRADIER_API_KEY",), "AAPL"),
        (MarketDataAppProvider(), ("MARKETDATA_APP_API_KEY",), "AAPL"),
    ],
    ids=lambda item: getattr(item, "name", str(item)),
)
def test_optional_credentialed_provider_small_read(provider, credentials, symbol):
    _require(*credentials)
    start, end = _bounds()
    rows = provider.fetch_ohlcv(symbol, Timeframe.D1, start, end)
    assert isinstance(rows, list)
