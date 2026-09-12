from datetime import UTC, datetime

import pytest

from app.config import settings
from app.providers.errors import (
    ProviderRateLimitError,
    ProviderResponseError,
    bounded_redact_provider_message,
    provider_retry_at_from_headers,
    raise_for_provider_error_envelope,
    redact_provider_message,
)


def test_provider_errors_redact_configured_secret_values(monkeypatch):
    monkeypatch.setattr(settings, "ALPHA_VANTAGE_API_KEY", "alpha-live-secret")

    message = "API key alpha-live-secret exceeded quota"
    assert "alpha-live-secret" not in str(ProviderRateLimitError("alpha", message))
    assert "alpha-live-secret" not in str(ProviderResponseError("alpha", message))


def test_provider_message_redacts_unknown_credential_bearing_url_and_header_values():
    message = (
        "https://example.test/query?apikey=unknown-secret&symbol=AAPL "
        "Authorization: Bearer unknown-token"
    )
    redacted = redact_provider_message(message)
    assert "unknown-secret" not in redacted
    assert "unknown-token" not in redacted
    assert "apikey=<redacted>" in redacted
    assert "Authorization: Bearer <redacted>" in redacted


def test_bounded_provider_message_redacts_before_truncating():
    message = bounded_redact_provider_message(
        "GET https://provider.test/data?api_key=unknown-secret " + "x" * 2000,
        max_length=1000,
    )
    assert "unknown-secret" not in message
    assert "<redacted>" in message
    assert len(message) == 1000


def test_bounded_provider_message_rejects_negative_limits():
    with pytest.raises(ValueError, match="non-negative"):
        bounded_redact_provider_message("error", max_length=-1)


def test_error_envelope_redacts_provider_echo_before_typed_rate_failure(monkeypatch):
    monkeypatch.setattr(settings, "ALPHA_VANTAGE_API_KEY", "alpha-live-secret")

    try:
        raise_for_provider_error_envelope(
            "alpha_vantage",
            {"Error Message": "API key alpha-live-secret exceeded the daily quota"},
            200,
        )
    except ProviderRateLimitError as exc:
        assert "alpha-live-secret" not in str(exc)
        assert "<redacted>" in str(exc)
    else:
        raise AssertionError("expected a typed provider rate-limit error")


def test_error_envelope_retains_provider_reset_headers_and_retry_time():
    with pytest.raises(ProviderRateLimitError) as exc_info:
        raise_for_provider_error_envelope(
            "provider",
            {"error": "daily quota exceeded"},
            200,
            headers={
                "Retry-After": "7",
                "X-RateLimit-Remaining": "0",
                "Authorization": "Bearer should-not-be-retained",
            },
        )

    failure = exc_info.value
    assert failure.headers == {"Retry-After": "7", "X-RateLimit-Remaining": "0"}
    assert failure.retry_at is not None
    assert 6 <= (failure.retry_at - datetime.now(UTC)).total_seconds() <= 8


def test_typed_rate_limit_error_filters_sensitive_transport_headers():
    failure = ProviderRateLimitError(
        "provider",
        "quota exceeded",
        headers={
            "Authorization": "Bearer should-not-be-retained",
            "Cookie": "session=secret",
            "Retry-After": "7",
            "X-RateLimit-Remaining": "0",
        },
    )

    assert failure.headers == {"Retry-After": "7", "X-RateLimit-Remaining": "0"}


def test_provider_retry_at_header_parser_rejects_unknown_values_without_guessing():
    now = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)
    assert provider_retry_at_from_headers({"Retry-After": "not-a-reset"}, now=now) is None
    assert provider_retry_at_from_headers({"X-RateLimit-Reset": "12"}, now=now) == datetime(
        2026, 9, 10, 10, 0, 12, tzinfo=UTC
    )
    assert provider_retry_at_from_headers(
        {"X-Api-Ratelimit-Reset": "12"}, now=now
    ) == datetime(2026, 9, 10, 10, 0, 12, tzinfo=UTC)
