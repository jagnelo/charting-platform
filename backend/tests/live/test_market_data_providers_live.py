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
from app.providers.errors import ProviderResponseError
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
from app.providers.telemetry import activate as activate_provider_telemetry
from app.providers.telemetry import deactivate as deactivate_provider_telemetry
from tests.live.live_usage import record_observation

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


def _observed_read(call, provider_name: str):
    """Require every live adapter operation to report a real HTTP response."""

    measurement, token = activate_provider_telemetry()
    try:
        result = call()
    except BaseException:
        record_observation(
            provider_name,
            http_requests=measurement.http_requests,
            response_bytes=measurement.response_bytes,
        )
        assert measurement.http_requests > 0
        assert measurement.response_bytes > 0
        raise
    finally:
        deactivate_provider_telemetry(token)
    record_observation(
        provider_name,
        http_requests=measurement.http_requests,
        response_bytes=measurement.response_bytes,
    )
    assert measurement.http_requests > 0
    assert measurement.response_bytes > 0
    return result, measurement


def test_openfigi_keyless_mapping():
    rows, _ = _observed_read(
        lambda: OpenFigiProvider().fetch_stable_identifiers("SPY", exchange_code="US"), "openfigi"
    )
    assert rows and any(row.identifier_type == "COMPOSITE_FIGI" for row in rows)


def test_sec_edgar_keyless_profile():
    _require("EDGAR_USER_AGENT")
    import app.providers.edgar as edgar_module

    edgar_module._ticker_map = {}
    edgar_module._ticker_map_ts = 0.0
    edgar_module._profile_cache = {}
    profile, measurement = _observed_read(
        lambda: EdgarProvider().get_instrument_profile("AAPL"), "edgar"
    )
    assert profile is not None and profile.name and profile.extra.get("cik")
    assert measurement.http_requests >= 2


def test_sec_edgar_full_ticker_exchange_directory_pagination_is_complete():
    """Fetch the official SEC directory once and prove local page completion."""

    _require("EDGAR_USER_AGENT")
    provider = EdgarProvider()
    rows: list[dict] = []
    offset = 0
    declared_total: int | None = None
    first_page = True
    while True:
        if first_page:
            page, _ = _observed_read(
                lambda: provider.discover_universe_page("EQUITY", offset), "edgar"
            )
            first_page = False
        else:
            # Subsequent pages are served from the provider's documented
            # in-process directory cache; validate pagination locally without
            # pretending that a second HTTP response occurred.
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
    equities, _ = _observed_read(lambda: provider.discover_universe_page("EQUITY", 0), "nasdaq")
    # The first EQUITY read above populates the shared directory cache. The
    # ETF read is therefore a local projection of that same observed source.
    etfs = provider.discover_universe_page("ETF", 0)
    assert equities["quotes"] and etfs["quotes"]
    assert equities["source_files"] == ["nasdaqlisted", "otherlisted"]
    assert all(row["status"] == "active" for row in equities["quotes"][:10])
    assert all(not row["symbol"].startswith("FILE CREATION") for row in equities["quotes"])
    if equities["total"] > 1000:
        next_page = provider.discover_universe_page("EQUITY", 1000)
        assert (
            next_page["quotes"]
            and next_page["quotes"][0]["symbol"] != equities["quotes"][0]["symbol"]
        )


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
        assert len({(row["symbol"], row["exchange_mic"], row["quoteType"]) for row in rows}) == len(
            rows
        )


def test_binance_keyless_crypto_history():
    start, end = _bounds()
    rows, _ = _observed_read(
        lambda: BinanceProvider().fetch_latest_ohlcv("BTC-USD", Timeframe.D1, 1), "binance"
    )
    assert rows and rows[-1].close > 0


def test_coinbase_keyless_crypto_history():
    rows, _ = _observed_read(
        lambda: CoinbaseProvider().fetch_latest_ohlcv("BTC-USD", Timeframe.D1, 1), "coinbase"
    )
    assert rows and rows[-1].close > 0


def test_kraken_keyless_crypto_history():
    rows, _ = _observed_read(
        lambda: KrakenProvider().fetch_latest_ohlcv("BTC-USD", Timeframe.D1, 1), "kraken"
    )
    assert rows and rows[-1].close > 0


def test_alpaca_credentialed_history():
    _require("ALPACA_API_KEY", "ALPACA_SECRET_KEY")
    start, end = _bounds()
    rows, _ = _observed_read(
        lambda: AlpacaProvider().fetch_ohlcv("AAPL", Timeframe.D1, start, end), "alpaca"
    )
    assert rows and rows[-1].close > 0


def test_massive_credentialed_reference():
    _require("MASSIVE_API_KEY")
    rows, _ = _observed_read(
        lambda: MassiveProvider().search_instruments("AAPL", limit=1), "massive"
    )
    assert rows
    assert all("AAPL" in f"{row.symbol} {row.name}".upper() for row in rows)


def test_alpha_vantage_credentialed_daily():
    _require("ALPHA_VANTAGE_API_KEY")
    start, end = _bounds()
    rows, _ = _observed_read(
        lambda: AlphaVantageProvider().fetch_ohlcv("AAPL", Timeframe.D1, start, end),
        "alpha_vantage",
    )
    assert rows and rows[-1].close > 0


def test_coingecko_credentialed_search():
    _require("COINGECKO_API_KEY")
    rows, _ = _observed_read(
        lambda: CoinGeckoProvider().search_instruments("bitcoin", limit=1), "coingecko"
    )
    assert rows and rows[0].symbol == "BTC-USD"


def test_coingecko_credentialed_profile_observes_id_resolution_request():
    _require("COINGECKO_API_KEY")
    profile, measurement = _observed_read(
        lambda: CoinGeckoProvider().get_instrument_profile("BTC-USD"), "coingecko"
    )
    assert profile is not None
    assert profile.extra["coingecko_id"] == "bitcoin"
    assert measurement.http_requests >= 2


def test_fred_credentialed_series():
    _require("FRED_API_KEY")
    start, end = _bounds()
    rows, _ = _observed_read(
        lambda: FREDProvider().fetch_ohlcv("^IRX", Timeframe.D1, start, end), "fred"
    )
    assert rows and all(row.close > 0 for row in rows)


def test_finra_credentialed_short_interest():
    _require("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET")
    rows, _ = _observed_read(lambda: FINRAProvider().fetch_short_interest("AAPL"), "finra")
    assert rows
    assert all(row.settlement_date and row.short_position is not None for row in rows)
    assert any((row.source_identifier or "").upper() == "AAPL" for row in rows)


def test_finra_credentialed_otc_daily_list():
    _require("FINRA_CLIENT_ID", "FINRA_CLIENT_SECRET")
    end = date.today()
    rows, _ = _observed_read(
        lambda: FINRAProvider().fetch_market_events(start=end - timedelta(days=45), end=end),
        "finra",
    )
    assert rows
    for row in rows:
        assert row.event_key.startswith("finra:otc_daily_list:")


def test_finra_otc_directory_credentialed_source():
    """Prove the operator-approved complete OTC source returns a bounded page."""

    _require("FINRA_OTC_SYMBOL_DIRECTORY_URL")
    page, _ = _observed_read(
        lambda: FINRAOTCDirectoryProvider().discover_universe_page("OTC", 0), "finra_otc_directory"
    )
    assert page["quotes"]
    assert page["total"] >= len(page["quotes"])
    assert page["source_files"] == [os.environ["FINRA_OTC_SYMBOL_DIRECTORY_URL"].strip()]
    assert all(row["exchange"] == "OTC" for row in page["quotes"])


@pytest.mark.parametrize(
    ("provider", "credentials", "symbol"),
    [
        (TiingoProvider(), ("TIINGO_API_KEY",), "AAPL"),
        (TwelveDataProvider(), ("TWELVE_DATA_API_KEY",), "AAPL"),
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
    rows, _ = _observed_read(
        lambda: provider.fetch_ohlcv(symbol, Timeframe.D1, start, end), provider.name
    )
    assert rows
    assert all(row.ts.tzinfo is not None for row in rows)
    assert all(row.close > 0 for row in rows)
    if provider.name == "tiingo":
        profile, _ = _observed_read(
            lambda: provider.get_instrument_profile(symbol), provider.name
        )
        assert profile is not None
        assert profile.symbol == symbol
        assert profile.name and profile.exchange
    if provider.name == "twelve_data":
        intraday_start = datetime.now(UTC) - timedelta(days=5)
        intraday_rows, _ = _observed_read(
            lambda: provider.fetch_ohlcv(
                symbol, Timeframe.M5, intraday_start, datetime.now(UTC)
            ),
            provider.name,
        )
        assert intraday_rows
        assert all(row.ts.tzinfo is not None and row.close > 0 for row in intraday_rows)
    if provider.name == "eodhd":
        # EODHD documents the same EOD endpoint with d/w/m period selectors;
        # exercise the two non-daily adapter paths in the bounded live case.
        period_start = datetime.now(UTC) - timedelta(days=90)
        for timeframe in (Timeframe.W1, Timeframe.MN):
            period_rows, _ = _observed_read(
                lambda timeframe=timeframe: provider.fetch_ohlcv(
                    symbol, timeframe, period_start, end
                ),
                provider.name,
            )
            assert period_rows
            assert all(row.ts.tzinfo is not None and row.close > 0 for row in period_rows)
    if provider.name == "fmp":
        profile, _ = _observed_read(
            lambda: provider.get_instrument_profile(symbol), provider.name
        )
        assert profile is not None
        assert profile.symbol == symbol
        assert profile.name and profile.exchange


def test_eodhd_free_plan_profile_entitlement_is_explicit():
    """The configured free EODHD key is EOD-only; do not treat 403 as no data."""

    _require("EODHD_API_KEY")
    with pytest.raises(ProviderResponseError) as exc_info:
        _observed_read(lambda: EODHDProvider().get_instrument_profile("AAPL"), "eodhd")
    assert exc_info.value.status_code == 403


def test_finnhub_credentialed_company_profile():
    """The observed free key does not entitle the stock-candle endpoint."""

    _require("FINNHUB_API_KEY")
    profile, _ = _observed_read(lambda: FinnhubProvider().get_instrument_profile("AAPL"), "finnhub")
    assert profile is not None
    assert profile.symbol == "AAPL"
    assert profile.name and profile.exchange
    events, _ = _observed_read(
        lambda: FinnhubProvider().fetch_instrument_events("AAPL"), "finnhub"
    )
    assert events
    assert all(event.event_time.tzinfo is not None for event in events)
    assert any(event.eps_actual is not None or event.eps_estimate is not None for event in events)
    calendar_events, _ = _observed_read(
        lambda: FinnhubProvider().fetch_market_events(
            start=date.today() - timedelta(days=7),
            end=date.today() + timedelta(days=45),
        ),
        "finnhub",
    )
    assert all(event.effective_date is not None for event in calendar_events)
