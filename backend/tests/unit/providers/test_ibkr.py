from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.config import settings
from app.models.ohlcv import Timeframe
from app.providers.errors import (
    ProviderNotConfiguredError,
    ProviderRateLimitError,
    ProviderResponseError,
)
from app.providers.ibkr import IBKRProvider
from app.providers.registry import list_provider_capabilities


class FakeResponse:
    def __init__(self, payload, *, status_code: int = 200, headers: dict[str, str] | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        self.content = json.dumps(payload).encode()

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://gateway.test")
            raise httpx.HTTPStatusError("gateway error", request=request, response=self)


def _configure(monkeypatch, *, conid_map: dict[str, int] | None = None):
    monkeypatch.setattr(settings, "IBKR_READ_ONLY_URL", "https://gateway.test")
    monkeypatch.setattr(settings, "IBKR_READ_ONLY_SESSION_COOKIE", "session-secret")
    monkeypatch.setattr(settings, "IBKR_READ_ONLY_VERIFY_TLS", True)
    monkeypatch.setattr(settings, "IBKR_READ_ONLY_TIMEOUT_SECONDS", 3.0)
    monkeypatch.setattr(settings, "IBKR_CONID_MAP", conid_map or {})


def test_ibkr_requires_gateway_url_and_session_cookie(monkeypatch):
    monkeypatch.setattr(settings, "IBKR_READ_ONLY_URL", "")
    monkeypatch.setattr(settings, "IBKR_READ_ONLY_SESSION_COOKIE", "")
    with pytest.raises(ProviderNotConfiguredError, match="IBKR_READ_ONLY_URL"):
        IBKRProvider().search_instruments("AAPL")


def test_ibkr_search_uses_gateway_cookie_and_normalizes_rows(monkeypatch):
    _configure(monkeypatch)
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(
            [
                {
                    "conid": 265598,
                    "symbol": "AAPL",
                    "companyName": "Apple Inc.",
                    "listingExchange": "NASDAQ",
                    "assetClass": "STK",
                    "currency": "USD",
                }
            ]
        )

    monkeypatch.setattr("app.providers.ibkr.httpx.request", fake_request)
    rows = IBKRProvider().search_instruments("AAPL")
    assert rows[0].symbol == "AAPL"
    assert rows[0].exchange == "NASDAQ"
    assert calls[0][0:2] == ("GET", "https://gateway.test/v1/api/iserver/secdef/search")
    assert calls[0][2]["headers"]["Cookie"] == "api=session-secret"
    assert "session-secret" not in repr(calls[0][2].get("params"))


def test_ibkr_profile_retains_provider_conid_without_making_it_canonical(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(
        "app.providers.ibkr.httpx.request",
        lambda method, url, **kwargs: FakeResponse(
            [{"conid": 265598, "symbol": "AAPL", "companyName": "Apple Inc.", "listingExchange": "NASDAQ"}]
        ),
    )
    profile = IBKRProvider().get_instrument_profile("AAPL")
    assert profile is not None
    assert profile.extra["conid"] == 265598
    assert profile.listings[0].extra_data == {"conid": 265598}
    assert not profile.identifiers


def test_ibkr_history_normalizes_millisecond_timestamps_and_raw_provenance(monkeypatch):
    _configure(monkeypatch, conid_map={"AAPL": 265598})
    start = datetime(2026, 1, 2, tzinfo=UTC)
    end = start + timedelta(days=2)
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return FakeResponse(
            {
                "data": [
                    {"t": int(start.timestamp() * 1000), "o": "100", "h": "105", "l": "99", "c": "104", "v": "1000"},
                    {"t": int((start + timedelta(days=1)).timestamp() * 1000), "o": 104, "h": 106, "l": 103, "c": 105, "v": 1200},
                ]
            }
        )

    monkeypatch.setattr("app.providers.ibkr.httpx.request", fake_request)
    bars = IBKRProvider().fetch_ohlcv("AAPL", Timeframe.D1, start, end, adjusted=False)
    assert len(bars) == 2
    assert bars[0].ts == start
    assert bars[0].close == 104
    assert bars[0].is_adjusted is False
    assert bars[0].provenance["conid"] == 265598
    assert calls[0][2]["params"]["bar"] == "1d"
    assert calls[0][2]["params"]["outsideRth"] == "false"


def test_ibkr_rejects_adjusted_history_instead_of_mislabeling_raw_bars(monkeypatch):
    _configure(monkeypatch, conid_map={"AAPL": 265598})
    with pytest.raises(ProviderResponseError, match="raw"):
        IBKRProvider().fetch_latest_ohlcv("AAPL", Timeframe.D1, 1)


def test_ibkr_rejects_malformed_history_rows(monkeypatch):
    _configure(monkeypatch, conid_map={"AAPL": 265598})
    monkeypatch.setattr(
        "app.providers.ibkr.httpx.request",
        lambda method, url, **kwargs: FakeResponse(
            {"data": [{"t": "not-a-time", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}]}
        ),
    )
    with pytest.raises(ProviderResponseError, match="malformed historical bar"):
        IBKRProvider().fetch_ohlcv(
            "AAPL",
            Timeframe.D1,
            datetime(2026, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 2, tzinfo=UTC),
            adjusted=False,
        )


def test_ibkr_rate_limit_preserves_allowlisted_headers(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(
        "app.providers.ibkr.httpx.request",
        lambda method, url, **kwargs: FakeResponse(
            {"error": "pacing violation"},
            status_code=429,
            headers={"Retry-After": "12", "X-RateLimit-Remaining": "0", "Set-Cookie": "api=secret"},
        ),
    )
    with pytest.raises(ProviderRateLimitError) as raised:
        IBKRProvider().search_instruments("AAPL")
    assert raised.value.headers == {"Retry-After": "12", "X-RateLimit-Remaining": "0"}
    assert raised.value.retry_at is not None
    assert "secret" not in str(raised.value)


def test_ibkr_body_pacing_envelope_is_typed_capacity_failure(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(
        "app.providers.ibkr.httpx.request",
        lambda method, url, **kwargs: FakeResponse({"error": "historical pacing violation"}),
    )
    with pytest.raises(ProviderRateLimitError, match="pacing"):
        IBKRProvider().search_instruments("AAPL")


def test_ibkr_current_price_initializes_accounts_then_reads_field_31(monkeypatch):
    _configure(monkeypatch, conid_map={"AAPL": 265598})
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/iserver/accounts"):
            return FakeResponse({"accounts": ["DU123"]})
        return FakeResponse([{"31": "205.42", "55": "AAPL"}])

    monkeypatch.setattr("app.providers.ibkr.httpx.request", fake_request)
    price = IBKRProvider().get_current_price("AAPL")
    assert price == 205.42
    assert [call[0:2] for call in calls] == [
        ("GET", "https://gateway.test/v1/api/iserver/accounts"),
        ("GET", "https://gateway.test/v1/api/iserver/marketdata/snapshot"),
    ]
    assert calls[1][2]["params"] == {"conids": "265598", "fields": "31"}


def test_ibkr_snapshot_null_is_valid_no_observation(monkeypatch):
    _configure(monkeypatch, conid_map={"AAPL": 265598})
    monkeypatch.setattr(
        "app.providers.ibkr.httpx.request",
        lambda method, url, **kwargs: FakeResponse(
            {"accounts": ["DU123"]} if url.endswith("/iserver/accounts") else [None]
        ),
    )
    assert IBKRProvider().get_current_price("AAPL") is None


def test_ibkr_snapshot_accepts_documented_previous_close_prefix(monkeypatch):
    _configure(monkeypatch, conid_map={"AAPL": 265598})
    monkeypatch.setattr(
        "app.providers.ibkr.httpx.request",
        lambda method, url, **kwargs: FakeResponse(
            {"accounts": ["DU123"]} if url.endswith("/iserver/accounts") else [{"31": "C205.42"}]
        ),
    )
    assert IBKRProvider().get_current_price("AAPL") == 205.42


def test_ibkr_registry_exposes_only_implemented_capabilities():
    capabilities = set(list_provider_capabilities("ibkr"))
    assert {"instrument_search", "instrument_metadata", "price_history", "latest_price"} <= capabilities
    assert "futures_history" not in capabilities
    assert "option_chain" not in capabilities
