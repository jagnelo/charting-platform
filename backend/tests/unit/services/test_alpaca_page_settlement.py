"""Alpaca history is debited for the pages it really requested, not the estimate.

The reviewed Alpaca ``fetch_ohlcv`` cost is a calendar-time page estimate. A
long range that Alpaca answers with nothing (a pre-listing probe) is one HTTP
request but used to be debited as every reserved page, so the durable ledger
reported the 200/minute window full while the account was about half used.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.models.provider_runtime import ProviderCapability, ProviderPolicy
from app.services import market_data
from app.services.provider_runtime import _consumed_dimension_costs, _coordinator_settlement

DIMENSION = "market_data_requests_per_minute"


def _policy() -> ProviderPolicy:
    return ProviderPolicy(
        data_source_id=1,
        capability=ProviderCapability.PRICE_HISTORY,
        quota_scope="account",
        quota_contract={
            "reset": "rolling",
            "dimensions": [
                {
                    "name": DIMENSION,
                    "limit": 200,
                    "window_seconds": 60,
                    "unit": "requests",
                    "scope": "account",
                    "source": "unit-test",
                }
            ],
        },
    )


def _measurement(requests: int):
    return SimpleNamespace(http_requests=requests, response_bytes=10, response_headers={})


def test_alpaca_history_settles_measured_requests_not_the_page_estimate():
    consumed = _consumed_dimension_costs(
        _policy(),
        _measurement(1),
        {DIMENSION: 3},
        provider_name="alpaca",
        operation="fetch_ohlcv:D1",
    )
    observed, unknown = _coordinator_settlement(
        _policy(),
        _measurement(1),
        {DIMENSION: 3},
        provider_name="alpaca",
        operation="fetch_ohlcv:D1",
    )

    assert consumed == {DIMENSION: 1}
    assert observed == {DIMENSION: 1}
    assert not unknown


def test_settlement_never_exceeds_the_reservation():
    consumed = _consumed_dimension_costs(
        _policy(),
        _measurement(5),
        {DIMENSION: 2},
        provider_name="alpaca",
        operation="fetch_ohlcv:D1",
    )

    assert consumed == {DIMENSION: 2}


def test_no_measured_request_keeps_the_conservative_reservation():
    consumed = _consumed_dimension_costs(
        _policy(),
        _measurement(0),
        {DIMENSION: 3},
        provider_name="alpaca",
        operation="fetch_ohlcv:D1",
    )
    observed, unknown = _coordinator_settlement(
        _policy(),
        _measurement(0),
        {DIMENSION: 3},
        provider_name="alpaca",
        operation="fetch_ohlcv:D1",
    )

    assert consumed == {DIMENSION: 3}
    assert observed == {} and unknown == {DIMENSION}


def test_other_providers_and_operations_keep_the_reviewed_cost():
    for provider, operation in (
        ("binance", "fetch_ohlcv:D1"),
        ("alpaca", "get_instrument_profile"),
    ):
        consumed = _consumed_dimension_costs(
            _policy(), _measurement(1), {DIMENSION: 3}, provider_name=provider, operation=operation
        )
        observed, _ = _coordinator_settlement(
            _policy(), _measurement(1), {DIMENSION: 3}, provider_name=provider, operation=operation
        )
        assert consumed == observed == {DIMENSION: 3}


def test_long_dead_no_data_slice_is_remembered_for_a_week_recent_one_for_hours():
    market_data._no_data_slices.clear()
    now = datetime.now(UTC)
    old_key, recent_key = ("old",), ("recent",)

    market_data._remember_no_data_slice(old_key, end=now - timedelta(days=400), now=now)
    market_data._remember_no_data_slice(recent_key, end=now - timedelta(days=5), now=now)

    assert market_data._no_data_slices[old_key] - now == timedelta(days=7)
    assert market_data._no_data_slices[recent_key] - now == timedelta(hours=12)
    market_data._no_data_slices.clear()
