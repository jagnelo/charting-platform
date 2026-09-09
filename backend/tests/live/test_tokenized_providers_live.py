"""Bounded live validation for public tokenized-security APIs."""

from __future__ import annotations

import os
import time

import httpx
import pytest

from app.providers.telemetry import activate as activate_provider_telemetry
from app.providers.telemetry import deactivate as deactivate_provider_telemetry
from app.providers.tokenized import (
    BybitXStocksProvider,
    GateTradfiProvider,
    KrakenXStocksProvider,
    RobinhoodTokenProvider,
    XStocksProvider,
)

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


def _observed_read(call):
    """Require live tokenized reads to contribute transport evidence."""

    measurement, token = activate_provider_telemetry()
    try:
        result = call()
    finally:
        deactivate_provider_telemetry(token)
    assert measurement.http_requests > 0
    assert measurement.response_bytes > 0
    return result, measurement


def test_xstocks_public_asset_and_price():
    provider = XStocksProvider()
    rows, measurement = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=1)
    )
    assert rows
    _assert_asset(rows[0])
    priced = provider.get_tokenized_price(rows[0].symbol)
    _assert_asset(priced, require_quote=True)


def test_robinhood_public_asset_and_price():
    provider = RobinhoodTokenProvider()
    rows, _ = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=1)
    )
    assert rows
    _assert_asset(rows[0])
    try:
        priced = provider.get_tokenized_price(rows[0].symbol)
    except httpx.HTTPStatusError as exc:
        # Robinhood's public edge occasionally returns its documented local
        # throttle even below the published 60 req/s limit.  Record the first
        # bounded observation, then retry once after a provider-safe second.
        if exc.response.status_code != 429:
            raise
        time.sleep(1.1)
        priced = provider.get_tokenized_price(rows[0].symbol)
    _assert_asset(priced, require_quote=True)


def test_bybit_public_xstocks_asset_and_price():
    provider = BybitXStocksProvider()
    rows, measurement = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=1)
    )
    assert rows
    assert measurement.response_bytes > 0
    _assert_asset(rows[0])
    priced = provider.get_tokenized_price(rows[0].symbol)
    _assert_asset(priced, require_quote=True)


def test_gate_public_tradfi_asset_and_orderbook():
    provider = GateTradfiProvider()
    # The first Gate symbol may be listed but have no active order book. Probe
    # a small bounded page and require one quote-bearing symbol so this test
    # proves the market-data surface rather than merely catalogue metadata.
    rows, measurement = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=5)
    )
    assert rows
    assert measurement.response_bytes > 0
    quote_record = None
    for row in rows:
        _assert_asset(row)
        priced = provider.get_tokenized_price(row.symbol)
        _assert_asset(priced)
        if priced and (priced.price is not None or priced.bid is not None or priced.ask is not None):
            quote_record = priced
            break
    _assert_asset(quote_record, require_quote=True)


def test_kraken_public_xstocks_asset_and_ticker():
    provider = KrakenXStocksProvider()
    rows, measurement = _observed_read(
        lambda: provider.discover_tokenized_assets(page=0, page_size=1)
    )
    assert measurement.response_bytes > 0
    # Kraken currently publishes no pair whose provider-native metadata marks
    # it as xStocks.  A successful empty catalogue is valid live evidence and
    # must not be turned into a fabricated stock-token mapping.
    if not rows:
        return
    _assert_asset(rows[0])
    priced = provider.get_tokenized_price(rows[0].symbol)
    _assert_asset(priced, require_quote=True)
