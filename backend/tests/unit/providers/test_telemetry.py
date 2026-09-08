from unittest.mock import MagicMock

from app.providers.telemetry import activate, deactivate, observe_response


def test_transport_measurement_records_bytes_and_selected_headers():
    response = MagicMock()
    response.content = b"{}\n"
    response.headers = {
        "content-length": "3",
        "x-ratelimit-remaining": "17",
        "authorization": "must-not-be-recorded",
    }

    measurement, token = activate()
    try:
        observe_response(response)
        observe_response(response)
    finally:
        deactivate(token)

    assert measurement.http_requests == 2
    assert measurement.response_bytes == 6
    assert measurement.response_headers == {
        "content-length": "3",
        "x-ratelimit-remaining": "17",
    }


def test_observation_without_active_call_is_ignored():
    response = MagicMock(content=b"payload")
    observe_response(response)


def test_transport_measurement_records_provider_specific_usage_headers():
    response = MagicMock()
    response.content = b"credits"
    response.headers = {
        "api-credits-used": "3",
        "api-credits-left": "5",
        "X-Ratelimit-Available": "117",
        "X-Ratelimit-Expiry": "1700000000",
    }

    measurement, token = activate()
    try:
        observe_response(response)
    finally:
        deactivate(token)

    assert measurement.response_headers == {
        "api-credits-used": "3",
        "api-credits-left": "5",
        "x-ratelimit-available": "117",
        "x-ratelimit-expiry": "1700000000",
    }
