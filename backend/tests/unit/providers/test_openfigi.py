from __future__ import annotations

import httpx
import pytest

from app.providers.base import InstrumentProfile
from app.providers.errors import ProviderResponseError
from app.providers.openfigi import OpenFigiProvider
from app.providers.telemetry import activate, deactivate


class FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.content = b"openfigi-payload"
        self.headers = {"x-ratelimit-remaining": "24"}

    def json(self):
        return self._payload


class FakeClient:
    next_payload = []
    captured_json = None
    captured_headers = None

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def post(self, url, json, headers):
        type(self).captured_json = json
        type(self).captured_headers = headers
        return FakeResponse(type(self).next_payload)


def test_fetch_stable_identifiers_maps_ticker_results(monkeypatch):
    monkeypatch.setattr("app.providers.openfigi.httpx.Client", FakeClient)
    FakeClient.next_payload = [
        {
            "data": [
                {
                    "ticker": "MSFT",
                    "name": "Microsoft Corporation",
                    "figi": "BBG000BPH45",
                    "compositeFIGI": "BBG000BPH459",
                    "shareClassFIGI": "BBG001S5TD05",
                    "exchCode": "US",
                    "securityType": "Common Stock",
                    "marketSector": "Equity",
                }
            ]
        }
    ]

    provider = OpenFigiProvider()
    identifiers = provider.fetch_stable_identifiers("MSFT")

    assert FakeClient.captured_json == [{"idType": "TICKER", "idValue": "MSFT"}]
    assert identifiers
    assert identifiers[0].identifier_type == "COMPOSITE_FIGI"
    assert identifiers[0].identifier_value == "BBG000BPH459"


def test_resolve_instrument_profile_uses_cusip_mapping(monkeypatch):
    monkeypatch.setattr("app.providers.openfigi.httpx.Client", FakeClient)
    FakeClient.next_payload = [
        {
            "data": [
                {
                    "ticker": "TXN",
                    "name": "Texas Instruments Incorporated",
                    "figi": "BBG000BLNQ16",
                    "compositeFIGI": "BBG000BLNQ10",
                    "shareClassFIGI": "BBG001S5VVB0",
                    "exchCode": "US",
                    "securityType": "Common Stock",
                    "marketSector": "Equity",
                }
            ]
        }
    ]

    provider = OpenFigiProvider()
    profile = provider.resolve_instrument_profile(cusip="882508104")

    assert isinstance(profile, InstrumentProfile)
    assert FakeClient.captured_json == [{"idType": "ID_CUSIP", "idValue": "882508104"}]
    assert profile.symbol == "TXN"
    assert profile.canonical_symbol == "TXN"
    assert profile.name == "Texas Instruments Incorporated"
    assert any(
        record.identifier_type == "CUSIP" and record.identifier_value == "882508104"
        for record in profile.identifiers
    )


def test_openfigi_mapping_reports_transport_usage(monkeypatch):
    monkeypatch.setattr("app.providers.openfigi.httpx.Client", FakeClient)
    FakeClient.next_payload = [{"data": []}]

    measurement, token = activate()
    try:
        OpenFigiProvider().fetch_stable_identifiers("AAPL")
    finally:
        deactivate(token)

    assert measurement.http_requests == 1
    assert measurement.response_bytes == len(b"openfigi-payload")
    assert measurement.response_headers == {"x-ratelimit-remaining": "24"}


def test_openfigi_transport_failure_is_typed(monkeypatch):
    failure = httpx.ConnectError(
        "connection failed",
        request=httpx.Request("POST", "https://api.openfigi.com/v3/mapping"),
    )

    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def post(self, *args, **kwargs):
            raise failure

    monkeypatch.setattr("app.providers.openfigi.httpx.Client", FailingClient)
    with pytest.raises(ProviderResponseError) as exc_info:
        OpenFigiProvider().fetch_stable_identifiers("AAPL")
    assert exc_info.value.provider_name == "openfigi"


def test_openfigi_invalid_json_is_typed(monkeypatch):
    class InvalidJsonClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def post(self, *args, **kwargs):
            response = FakeResponse(None)
            response.json = lambda: (_ for _ in ()).throw(ValueError("malformed payload"))
            return response

    monkeypatch.setattr("app.providers.openfigi.httpx.Client", InvalidJsonClient)
    with pytest.raises(ProviderResponseError) as exc_info:
        OpenFigiProvider().fetch_stable_identifiers("AAPL")
    assert exc_info.value.provider_name == "openfigi"
