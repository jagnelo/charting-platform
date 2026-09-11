import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.config import settings
from app.models.provider_runtime import ProviderCapability
from app.services.provider_availability import (
    classify_exception,
    classify_response,
    latest_availability,
    notification_due,
    recent_availability_runs,
    representative_request,
    response_shape,
)


def test_representative_contract_covers_each_capability():
    for capability in ProviderCapability:
        request = representative_request(capability)
        assert request
        assert "symbol" in request or "query" in request or "quote_type" in request


def test_classification_is_deterministic_for_empty_and_transport_failures():
    assert classify_response([]) == "empty_partial_response"
    assert response_shape([]) == {"type": "array", "items": 0, "item_type": "NoneType"}
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


def test_availability_read_models_emit_canonical_wire_timestamps():
    observation = SimpleNamespace(
        capability=ProviderCapability.PRICE_HISTORY,
        classification="success",
        success=True,
        latency_ms=12,
        consecutive_failures=0,
        recovered=False,
        error_message=None,
        created_at=datetime(2026, 9, 11, 14, 30),
        response_shape={"type": "array"},
    )
    source = SimpleNamespace(id=1, name="yfinance")
    health = SimpleNamespace(
        last_success_at=datetime(2026, 9, 11, 12, 30),
        last_failure_at=None,
    )

    class AvailabilityResult:
        def all(self):
            return [(observation, source, health)]

    class RunResult:
        def scalars(self):
            return [
                SimpleNamespace(
                    id=1,
                    mode="daily_core",
                    status="completed",
                    application_version="test",
                    probe_contract_version="v1",
                    started_at=datetime(2026, 9, 11, 12, 0),
                    finished_at=datetime(2026, 9, 11, 12, 1, tzinfo=UTC),
                    error=None,
                )
            ]

    class FakeDb:
        def __init__(self):
            self.calls = 0

        async def execute(self, _statement):
            self.calls += 1
            return AvailabilityResult() if self.calls == 1 else RunResult()

    # ``datetime.timezone`` is used through ``tzinfo`` so the helper receives
    # an offset-aware value without involving database setup.
    observation.created_at = datetime.fromisoformat("2026-09-11T14:30:00+02:00")
    db = FakeDb()
    availability = asyncio.run(latest_availability(db))
    assert availability[0]["observed_at"] == "2026-09-11T12:30:00Z"
    assert availability[0]["last_success_at"] == "2026-09-11T12:30:00Z"

    runs = asyncio.run(recent_availability_runs(db))
    assert runs[0]["started_at"] == "2026-09-11T12:00:00Z"
    assert runs[0]["finished_at"] == "2026-09-11T12:01:00Z"
