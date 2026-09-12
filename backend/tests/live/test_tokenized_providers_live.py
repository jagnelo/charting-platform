"""Bounded live validation for public tokenized-security APIs."""

from __future__ import annotations

import os
import time

import pytest

from app.providers.errors import ProviderRateLimitError
from app.providers.telemetry import activate as activate_provider_telemetry
from app.providers.telemetry import deactivate as deactivate_provider_telemetry
from app.providers.tokenized import (
    BybitXStocksProvider,
    DinariTokenProvider,
    GateTradfiProvider,
    KrakenXStocksProvider,
    OndoGlobalMarketsProvider,
    RobinhoodTokenProvider,
    XStocksProvider,
)
from tests.live.live_usage import record_observation

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1",
        reason="Set RUN_LIVE_PROVIDER_TESTS=1 to run external provider probes.",
    ),
]


def _assert_asset(record, *, require_quote: bool = False):
    assert record is not None
    assert record.provider and record.asset_id and record.symbol
    assert record.raw_payload
    if require_quote:
        assert record.price is not None or record.bid is not None or record.ask is not None


def _require(*names: str) -> None:
    missing = [name for name in names if not os.getenv(name, "").strip()]
    if missing:
        pytest.fail(f"missing live provider credentials: {', '.join(missing)}")


def _observed_read(call, provider_name: str):
    """Require live tokenized reads to contribute transport evidence."""

    measurement, token = activate_provider_telemetry()
    try:
        result = call()
    except BaseException:
        # A rejected request is still useful live evidence: the provider
        # response must have crossed the adapter and been observed before the
        # caller decides whether a bounded retry is allowed.
        record_observation(
            provider_name,
            http_requests=measurement.http_requests,
            response_bytes=measurement.response_bytes,
            response_headers=measurement.response_headers,
            success=False,
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
        response_headers=measurement.response_headers,
        success=True,
    )
    assert measurement.http_requests > 0
    assert measurement.response_bytes > 0
    return result, measurement


def test_xstocks_public_asset_and_price():
    provider = XStocksProvider()
    rows, measurement = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=1), "xstocks"
    )
    assert rows
    _assert_asset(rows[0])
    priced, quote_measurement = _observed_read(
        lambda: provider.get_tokenized_price(rows[0].symbol), "xstocks"
    )
    assert quote_measurement.http_requests >= 2
    _assert_asset(priced)
    if priced.price is None and priced.bid is None and priced.ask is None:
        # xStocks returns an explicit null quote while the selected token's
        # trading session is closed. Treat that as a valid, observed market
        # state rather than fabricating a price or failing a transport probe.
        price_payload = priced.raw_payload.get("price", {})
        asset_payload = priced.raw_payload.get("asset", {})
        assert isinstance(price_payload, dict)
        assert price_payload.get("quote") is None
        trading = asset_payload.get("trading", {})
        assert isinstance(trading, dict)
        assert trading.get("currentPeriod") == "closed"
    else:
        _assert_asset(priced, require_quote=True)


def test_xstocks_public_corporate_actions():
    provider = XStocksProvider()
    events, measurement = _observed_read(
        lambda: provider.fetch_tokenized_corporate_actions(page=1, page_size=1),
        "xstocks",
    )
    assert isinstance(events, list)
    assert all(isinstance(event, dict) for event in events)
    assert measurement.http_requests == 1


def test_robinhood_public_asset_and_price():
    provider = RobinhoodTokenProvider()
    rows, _ = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=1), "robinhood_tokens"
    )
    assert rows
    _assert_asset(rows[0])
    try:
        priced, quote_measurement = _observed_read(
            lambda: provider.get_tokenized_price(rows[0].symbol), "robinhood_tokens"
        )
    except ProviderRateLimitError as exc:
        # Robinhood's public edge occasionally returns its documented local
        # throttle even below the published 60 req/s limit.  Record the first
        # bounded observation, then retry once after a provider-safe second.
        if exc.status_code != 429:
            raise
        time.sleep(1.1)
        priced, quote_measurement = _observed_read(
            lambda: provider.get_tokenized_price(rows[0].symbol), "robinhood_tokens"
        )
    assert quote_measurement.http_requests >= 2
    _assert_asset(priced, require_quote=True)


def test_robinhood_public_corporate_actions():
    provider = RobinhoodTokenProvider()
    events, measurement = _observed_read(
        lambda: provider.fetch_tokenized_corporate_actions(), "robinhood_tokens"
    )
    assert isinstance(events, list)
    assert all(isinstance(event, dict) for event in events)
    assert measurement.http_requests == 1


def test_bybit_public_xstocks_asset_and_price():
    provider = BybitXStocksProvider()
    rows, measurement = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=1), "bybit_xstocks"
    )
    assert rows
    assert measurement.response_bytes > 0
    # Bybit documents endpoint/UID-specific state in these response headers.
    # When the public edge emits them, telemetry must retain only the
    # allow-listed names; the current unauthenticated public edge may omit
    # them, which is itself evidence for keeping routing fail-closed.
    assert set(measurement.response_headers) <= {
        "content-length",
        "x-bapi-limit",
        "x-bapi-limit-status",
        "x-bapi-limit-reset-timestamp",
    }
    _assert_asset(rows[0])
    priced, quote_measurement = _observed_read(
        lambda: provider.get_tokenized_price(rows[0].symbol), "bybit_xstocks"
    )
    assert quote_measurement.http_requests >= 2
    assert set(quote_measurement.response_headers) <= {
        "content-length",
        "x-bapi-limit",
        "x-bapi-limit-status",
        "x-bapi-limit-reset-timestamp",
    }
    _assert_asset(priced, require_quote=True)


def test_gate_public_tradfi_asset_and_orderbook():
    provider = GateTradfiProvider()
    # The first Gate symbol may be listed but have no active order book. Probe
    # a small bounded page and require one quote-bearing symbol so this test
    # proves the market-data surface rather than merely catalogue metadata.
    rows, measurement = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=5), "gate_tradfi"
    )
    assert rows
    assert measurement.response_bytes > 0
    quote_record = None
    for row in rows:
        _assert_asset(row)
        priced, quote_measurement = _observed_read(
            lambda row=row: provider.get_tokenized_price(row.symbol), "gate_tradfi"
        )
        assert quote_measurement.http_requests >= 2
        _assert_asset(priced)
        if priced and (
            priced.price is not None or priced.bid is not None or priced.ask is not None
        ):
            quote_record = priced
            break
    _assert_asset(quote_record, require_quote=True)


def test_kraken_public_xstocks_asset_and_ticker():
    provider = KrakenXStocksProvider()
    rows, measurement = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=1), "kraken_xstocks"
    )
    assert measurement.response_bytes > 0
    # Kraken currently publishes no pair whose provider-native metadata marks
    # it as xStocks.  A successful empty catalogue is valid live evidence and
    # must not be turned into a fabricated stock-token mapping.
    if not rows:
        return
    _assert_asset(rows[0])
    priced, quote_measurement = _observed_read(
        lambda: provider.get_tokenized_price(rows[0].symbol), "kraken_xstocks"
    )
    assert quote_measurement.http_requests >= 2
    _assert_asset(priced, require_quote=True)


def test_dinari_credentialed_stock_metadata_price_quote_history_and_news():
    _require("DINARI_API_KEY_ID", "DINARI_API_SECRET_KEY")
    provider = DinariTokenProvider()
    rows, measurement = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=1), "dinari"
    )
    assert rows
    _assert_asset(rows[0])
    identifier = rows[0].asset_id
    resolved_by_symbol, symbol_measurement = _observed_read(
        lambda: provider.get_tokenized_asset(rows[0].symbol), "dinari"
    )
    assert symbol_measurement.http_requests == 1
    _assert_asset(resolved_by_symbol)
    assert resolved_by_symbol.asset_id == identifier
    priced, price_measurement = _observed_read(
        lambda: provider.get_tokenized_price(identifier), "dinari"
    )
    assert price_measurement.http_requests >= 2
    _assert_asset(priced, require_quote=True)
    quoted, quote_measurement = _observed_read(
        lambda: provider.get_tokenized_quote(identifier), "dinari"
    )
    assert quote_measurement.http_requests >= 2
    _assert_asset(quoted, require_quote=True)
    # Dinari documents four distinct aggregate windows. Exercise each one so
    # a transport/schema change cannot leave the adapter green while silently
    # supporting only the default DAY surface.
    for timespan in ("DAY", "WEEK", "MONTH", "YEAR"):
        history, history_measurement = _observed_read(
            lambda timespan=timespan: provider.fetch_tokenized_historical_prices(
                identifier, timespan=timespan
            ),
            "dinari",
        )
        assert history_measurement.http_requests >= 2
        assert isinstance(history, list)
    news, news_measurement = _observed_read(
        lambda: provider.fetch_tokenized_news(identifier, limit=1), "dinari"
    )
    assert news_measurement.http_requests >= 2
    assert isinstance(news, list)
    dividends, dividend_measurement = _observed_read(
        lambda: provider.fetch_tokenized_dividends(identifier), "dinari"
    )
    assert dividend_measurement.http_requests >= 2
    assert isinstance(dividends, list)
    splits, split_measurement = _observed_read(
        lambda: provider.fetch_tokenized_splits(identifier), "dinari"
    )
    assert split_measurement.http_requests >= 2
    assert isinstance(splits, list)
    # If the provider advertises another split page, exercise the explicit
    # same-instance cursor continuation. A terminal first page consumes no
    # additional request and is still a valid live observation.
    if provider._split_cursors:
        continued, continuation_measurement = _observed_read(
            lambda: provider.fetch_tokenized_splits(identifier, page=2), "dinari"
        )
        assert continuation_measurement.http_requests >= 2
        assert isinstance(continued, list)
    actions, action_measurement = _observed_read(
        lambda: provider.fetch_tokenized_corporate_actions(symbol=rows[0].symbol), "dinari"
    )
    assert action_measurement.http_requests >= 3
    assert isinstance(actions, list)
    assert all(row.get("action_type") in {"dividend", "split"} for row in actions)
    assert measurement.http_requests == 1


def test_ondo_credentialed_metadata_price_market_summary_and_ohlc():
    _require("ONDO_GLOBAL_MARKETS_API_KEY")
    provider = OndoGlobalMarketsProvider()
    rows, measurement = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=1), "ondo_global_markets"
    )
    assert rows
    _assert_asset(rows[0])
    priced, price_measurement = _observed_read(
        lambda: provider.get_tokenized_price(rows[0].symbol), "ondo_global_markets"
    )
    assert price_measurement.http_requests >= 2
    _assert_asset(priced, require_quote=True)
    market, market_measurement = _observed_read(
        lambda: provider.fetch_tokenized_market_data(rows[0].symbol),
        "ondo_global_markets",
    )
    assert market_measurement.http_requests >= 2
    assert market is not None
    assert market["primary_market"]["symbol"] == rows[0].symbol
    assert market["underlying_market"]["ticker"] == rows[0].underlying_symbol
    candles, ohlc_measurement = _observed_read(
        lambda: provider.fetch_tokenized_ohlc(
            rows[0].symbol, interval="1day", range_="1day", market="primary"
        ),
        "ondo_global_markets",
    )
    assert ohlc_measurement.http_requests >= 2
    assert isinstance(candles, list)
    assert measurement.http_requests == 1
