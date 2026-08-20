from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.config import settings
from app.models.provider_runtime import ProviderCapability
from app.services.provider_availability import (
    classify_exception,
    classify_response,
    notification_due,
    representative_request,
)


def test_representative_contract_covers_each_capability():
    for capability in ProviderCapability:
        request = representative_request(capability)
        assert request
        assert "symbol" in request or "query" in request or "quote_type" in request


def test_classification_is_deterministic_for_empty_and_transport_failures():
    assert classify_response([]) == "empty_partial_response"
    assert classify_response({"rows": [1]}) == "success"
    assert classify_exception(TimeoutError()) == "timeout"
    assert classify_exception(ConnectionError("DNS lookup failed")) == "dns_transport"
    assert classify_exception(KeyError("new_field")) == "schema_content_incompatibility"


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
