from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.config import settings
from app.models.provider_runtime import ProviderCapability
from app.providers.registry import provider_is_configured
from app.services.provider_availability import (
    availability_error_message,
    classify_exception,
    classify_response,
    notification_due,
    provider_configured,
    representative_operation,
    representative_request,
    response_shape,
)


def test_representative_contract_covers_each_capability():
    for capability in ProviderCapability:
        request = representative_request(capability)
        assert request
        assert "symbol" in request or "query" in request or "quote_type" in request


def test_representative_operations_cover_probeable_capabilities():
    for capability in ProviderCapability:
        request = representative_request(capability)
        operation = representative_operation(capability)
        if request and capability != ProviderCapability.MARKET_CALENDAR:
            assert operation


def test_availability_configuration_uses_operation_aware_registry(monkeypatch):
    source = SimpleNamespace(name="marketstack")
    entitlement = SimpleNamespace()
    monkeypatch.setattr(settings, "MARKETSTACK_API_KEY", "marketstack-key")
    monkeypatch.setattr(settings, "MARKETSTACK_DISCOVERY_EXCHANGE", "")

    assert provider_configured(source, entitlement, operation="fetch_latest_ohlcv")
    assert not provider_configured(source, entitlement, operation="discover_universe_page")

    dinari = SimpleNamespace(name="dinari")
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "dinari-id")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "dinari-secret")
    assert provider_configured(dinari, entitlement, operation="discover_tokenized_assets")


def test_provider_configuration_rejects_whitespace_credentials(monkeypatch):
    monkeypatch.setattr(settings, "DINARI_API_KEY_ID", "   ")
    monkeypatch.setattr(settings, "DINARI_API_SECRET_KEY", "dinari-secret")
    assert not provider_is_configured("dinari")

    monkeypatch.setattr(settings, "MASSIVE_API_KEY", "   ")
    monkeypatch.setattr(settings, "MARKETDATA_API_KEY", "\t")
    assert not provider_is_configured("massive")


def test_classification_is_deterministic_for_empty_and_transport_failures():
    assert classify_response([]) == "empty_partial_response"
    assert response_shape([]) == {"type": "array", "items": 0, "item_type": "NoneType"}
    assert classify_response({"rows": [1]}) == "success"
    assert classify_exception(TimeoutError()) == "timeout"
    assert classify_exception(ConnectionError("DNS lookup failed")) == "dns_transport"
    assert classify_exception(KeyError("new_field")) == "schema_content_incompatibility"


def test_availability_error_message_redacts_credentials_and_is_bounded():
    message = availability_error_message(
        RuntimeError("GET https://provider.test/data?api_key=availability-secret " + "x" * 2000)
    )

    assert "availability-secret" not in message
    assert "<redacted>" in message
    assert len(message) <= 1000


def test_classification_covers_http_auth_quota_schema_and_parser_boundaries():
    def error(status: int, message: str = "upstream") -> Exception:
        exc = RuntimeError(message)
        exc.response = SimpleNamespace(status_code=status)
        return exc

    assert classify_exception(error(401)) == "authentication"
    assert classify_exception(error(403, "forbidden")) == "authentication"
    assert classify_exception(error(408)) == "quota_rate_limit"
    assert classify_exception(error(429, "too many requests")) == "quota_rate_limit"
    assert classify_exception(error(500)) == "upstream_http"
    assert classify_exception(ValueError("malformed number")) == "internal_parser_failure"
    assert (
        classify_exception(RuntimeError("response schema changed"))
        == "schema_content_incompatibility"
    )


def test_weekly_notification_only_escalates_confirmed_schema_regressions():
    now = datetime.now(UTC)
    assert (
        notification_due(
            mode="weekly_supported_sweep",
            classification="upstream_http",
            success=False,
            consecutive_failures=1,
            last_notification_kind=None,
            last_notification_at=None,
            now=now,
        )
        is None
    )


def test_notification_policy_covers_first_failure_cooldown_and_recovery(monkeypatch):
    now = datetime.now(UTC)
    assert (
        notification_due(
            mode="daily_core",
            classification="timeout",
            success=False,
            consecutive_failures=1,
            last_notification_kind=None,
            last_notification_at=None,
            now=now,
        )
        is None
    )
    assert (
        notification_due(
            mode="daily_core",
            classification="timeout",
            success=False,
            consecutive_failures=2,
            last_notification_kind=None,
            last_notification_at=None,
            now=now,
        )
        == "failure"
    )
    recent = now - timedelta(
        seconds=settings.PROVIDER_AVAILABILITY_NOTIFICATION_COOLDOWN_SECONDS - 1
    )
    assert (
        notification_due(
            mode="daily_core",
            classification="timeout",
            success=False,
            consecutive_failures=3,
            last_notification_kind="failure",
            last_notification_at=recent,
            now=now,
        )
        is None
    )
    assert (
        notification_due(
            mode="weekly_supported_sweep",
            classification="schema_content_incompatibility",
            success=False,
            consecutive_failures=1,
            last_notification_kind=None,
            last_notification_at=None,
            now=now,
        )
        == "failure"
    )
    assert (
        notification_due(
            mode="daily_core",
            classification="not_configured",
            success=False,
            consecutive_failures=0,
            last_notification_kind=None,
            last_notification_at=None,
            now=now,
        )
        is None
    )
    assert (
        notification_due(
            mode="daily_core",
            classification="success",
            success=True,
            consecutive_failures=0,
            last_notification_kind="failure",
            last_notification_at=now,
            now=now,
        )
        == "recovery"
    )
