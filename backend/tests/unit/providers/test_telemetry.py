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


def test_streaming_observation_accepts_explicit_measured_bytes_without_materializing_content():
    response = MagicMock()
    response.headers = {"record-total": "2"}
    measurement, token = activate()
    try:
        observe_response(response, response_bytes=0)
        observe_response(response, response_bytes=7, count_request=False)
    finally:
        deactivate(token)

    assert measurement.http_requests == 1
    assert measurement.response_bytes == 7
    assert measurement.response_headers == {"record-total": "2"}


def test_transport_measurement_records_provider_specific_usage_headers():
    response = MagicMock()
    response.content = b"credits"
    response.headers = {
        "api-credits-used": "3",
        "api-credits-left": "5",
        "Api-Credits-Request": "1",
        "X-Ratelimit-Available": "117",
        "X-Ratelimit-Expiry": "1700000000",
        "X-Bapi-Limit": "50",
        "X-Bapi-Limit-Status": "49",
        "X-Bapi-Limit-Reset-Timestamp": "1700000000000",
        "Record-Total": "250",
        "Record-Limit": "5000",
        "Response-Payload-Max-Size": "3",
    }

    measurement, token = activate()
    try:
        observe_response(response)
    finally:
        deactivate(token)

    assert measurement.response_headers == {
        "api-credits-used": "3",
        "api-credits-left": "5",
        "api-credits-request": "1",
        "x-ratelimit-available": "117",
        "x-ratelimit-expiry": "1700000000",
        "x-bapi-limit": "50",
        "x-bapi-limit-status": "49",
        "x-bapi-limit-reset-timestamp": "1700000000000",
        "record-total": "250",
        "record-limit": "5000",
        "response-payload-max-size": "3",
    }
