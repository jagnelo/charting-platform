"""Opt-in live coverage for the free, unauthenticated OpenFIGI identifier path."""

import os

import pytest

from app.providers.openfigi import OpenFigiProvider

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.getenv("RUN_LIVE_PROVIDER_TESTS") != "1",
        reason="Set RUN_LIVE_PROVIDER_TESTS=1 to run live provider checks.",
    ),
]


def test_public_openfigi_resolves_spy_without_credentials():
    records = OpenFigiProvider().fetch_stable_identifiers("SPY")

    assert records
    assert any(record.identifier_type == "COMPOSITE_FIGI" for record in records)
    assert all(record.source == "openfigi" for record in records)
    assert all(record.identifier_value for record in records)
