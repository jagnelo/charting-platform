"""Bounded live validation for public tokenized-security APIs."""

from __future__ import annotations

import os
import time

import httpx
import pytest

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


def _assert_asset(record):
    assert record is not None
    assert record.provider and record.asset_id and record.symbol
    assert record.raw_payload


def test_xstocks_public_asset_and_price():
    provider = XStocksProvider()
    rows = provider.discover_tokenized_assets(page=0, page_size=1)
    assert rows
    _assert_asset(rows[0])
    priced = provider.get_tokenized_price(rows[0].symbol)
    _assert_asset(priced)


def test_robinhood_public_asset_and_price():
    provider = RobinhoodTokenProvider()
    rows = provider.discover_tokenized_assets(page=0, page_size=1)
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
    _assert_asset(priced)


def test_bybit_public_xstocks_asset_and_price():
    provider = BybitXStocksProvider()
    rows = provider.discover_tokenized_assets(page=0, page_size=1)
    assert rows
    _assert_asset(rows[0])
    priced = provider.get_tokenized_price(rows[0].symbol)
    _assert_asset(priced)


def test_gate_public_tradfi_asset_and_orderbook():
    provider = GateTradfiProvider()
    rows = provider.discover_tokenized_assets(page=0, page_size=1)
    assert rows
    _assert_asset(rows[0])
    priced = provider.get_tokenized_price(rows[0].symbol)
    _assert_asset(priced)


def test_kraken_public_xstocks_asset_and_ticker():
    provider = KrakenXStocksProvider()
    rows = provider.discover_tokenized_assets(page=0, page_size=1)
    # Kraken currently publishes no pair whose provider-native metadata marks
    # it as xStocks.  A successful empty catalogue is valid live evidence and
    # must not be turned into a fabricated stock-token mapping.
    if not rows:
        return
    _assert_asset(rows[0])
    priced = provider.get_tokenized_price(rows[0].symbol)
    _assert_asset(priced)
