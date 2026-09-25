from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.provider_runtime import ProviderCapability
from app.providers.registry import provider_is_configured
from app.services.provider_availability import (
    availability_error_message,
    classify_exception,
    classify_response,
    default_probe,
    notification_due,
    provider_configured,
    representative_operation,
    representative_request,
    response_payload,
    response_shape,
    run_availability_probes,
)


@pytest.mark.asyncio
async def test_raw_only_history_availability_probe_requests_unadjusted_bars(monkeypatch):
    calls = []

    class RawOnlyProvider:
        name = "ibkr"

        def fetch_latest_ohlcv(self, **kwargs):
            calls.append(kwargs)
            return []

    monkeypatch.setattr(
        "app.services.provider_availability.get_provider",
        lambda _name: RawOnlyProvider(),
    )

    result = await default_probe(
        "ibkr",
        ProviderCapability.FUTURES_HISTORY,
        representative_request(ProviderCapability.FUTURES_HISTORY),
    )

    assert result == []
    assert calls and calls[0]["adjusted"] is False


@pytest.mark.asyncio
async def test_tokenized_history_availability_probe_uses_distinct_operation(monkeypatch):
    calls = []

    class DinariProvider:
        name = "dinari"

        def fetch_tokenized_historical_prices(self, **kwargs):
            calls.append(kwargs)
            return []

    monkeypatch.setattr(
        "app.services.provider_availability.get_provider",
        lambda _name: DinariProvider(),
    )

    capability = ProviderCapability.TOKENIZED_HISTORICAL_PRICES
    result = await default_probe("dinari", capability, representative_request(capability))

    assert result == []
    assert calls == [{"identifier": "AAPL", "timespan": "DAY"}]


@pytest.mark.asyncio
async def test_edgar_market_event_availability_probe_uses_ipo_pipeline_contract(monkeypatch):
    calls = []

    class EdgarProvider:
        name = "edgar"

        def fetch_ipo_pipeline_events(self, **kwargs):
            calls.append(kwargs)
            return []

    monkeypatch.setattr(
        "app.services.provider_availability.get_provider",
        lambda _name: EdgarProvider(),
    )

    capability = ProviderCapability.MARKET_EVENTS
    request = representative_request(capability)
    assert representative_operation(capability, "edgar") == "fetch_ipo_pipeline_events"
    result = await default_probe("edgar", capability, request)

    assert result == []
    assert calls == [
        {
            "cik": "0000320193",
            "start": date.fromisoformat(request["start"]),
            "end": date.fromisoformat(request["end"]),
            "max_events": 1,
        }
    ]


def test_representative_contract_covers_each_capability():
    for capability in ProviderCapability:
        request = representative_request(capability)
        assert request
        assert (
            "symbol" in request
            or "identifier" in request
            or "query" in request
            or "quote_type" in request
        )


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


def test_response_payload_retains_typed_fields_and_redacts_only_auth_material():
    from app.providers.base import ProviderSearchResult

    value = {
        "rows": [ProviderSearchResult(symbol="AAPL", name="Apple")],
        "observed_at": datetime(2026, 9, 25, tzinfo=UTC),
        "price": 123.45,
        "api_key": "do-not-persist",
        "next_page_token": "continuation-is-data",
    }

    assert response_payload(value) == {
        "rows": [{"symbol": "AAPL", "name": "Apple", "exchange": "", "instrument_type": ""}],
        "observed_at": "2026-09-25T00:00:00+00:00",
        "price": 123.45,
        "api_key": "<redacted>",
        "next_page_token": "continuation-is-data",
    }


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


@pytest.mark.asyncio
async def test_availability_skips_finra_otc_until_source_controls_are_reviewed(db, monkeypatch):
    from app.models.data_source import DataSource
    from app.models.provider_runtime import ProviderPolicy

    source = DataSource(
        name="finra_otc_directory",
        base_url="https://api.finra.org",
        is_active=True,
    )
    db.add(source)
    db.flush()
    db.add(
        ProviderPolicy(
            data_source_id=source.id,
            capability=ProviderCapability.UNIVERSE_DISCOVERY,
            is_enabled=True,
            is_pinned=True,
            base_priority=1,
        )
    )
    db.flush()
    monkeypatch.setattr(
        settings,
        "FINRA_OTC_SYMBOL_DIRECTORY_URL",
        "https://api.finra.org/data/group/otcMarket/name/otcSecurityMaster",
    )
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_REVIEWED", False)
    monkeypatch.setattr(settings, "FINRA_OTC_SOURCE_EVIDENCE", "")
    calls = []

    class AsyncSessionFacade:
        def add(self, value):
            db.add(value)

        async def execute(self, statement):
            return db.execute(statement)

        async def flush(self):
            db.flush()

        async def commit(self):
            db.commit()

    async def probe(provider_name, capability, request):
        calls.append((provider_name, capability, request))
        return {"rows": []}

    await run_availability_probes(
        AsyncSessionFacade(), "daily_core", probe=probe
    )

    from app.models.provider_runtime import ProviderAvailabilityObservation

    observation = db.query(ProviderAvailabilityObservation).one()
    assert calls == []
    assert observation.classification == "routing_control_exclusion"
    assert observation.success is False
    assert "FINRA_OTC_SOURCE_REVIEWED" in observation.error_message
    assert observation.consecutive_failures == 0
