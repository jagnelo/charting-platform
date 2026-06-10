from __future__ import annotations

from app.providers.base import InstrumentProfile
from app.providers.openfigi import OpenFigiProvider


class FakeResponse:
    def __init__(self, payload, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

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
