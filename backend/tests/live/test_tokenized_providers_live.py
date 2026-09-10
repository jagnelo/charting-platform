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
    GateTradfiProvider,
    KrakenXStocksProvider,
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
    _assert_asset(priced, require_quote=True)


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
