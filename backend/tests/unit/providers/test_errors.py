from app.config import settings
from app.providers.errors import (
    ProviderRateLimitError,
    ProviderResponseError,
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
