import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.config import settings
from app.lib.time_utils import wire_datetime
from app.models.asset_class import InstrumentType
from app.models.data_source import DataSource
from app.models.exchange import Exchange
from app.models.instrument import Instrument
from app.models.instrument_identity import (
    InstrumentIdentifier,
    InstrumentIdentifierType,
    InstrumentProviderSymbol,
)
from app.models.instrument_stats import InstrumentStats
from app.models.listing import InstrumentListing
from app.models.market_data_foundation import InstrumentIdentityQuarantine
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_runtime import ProviderEntitlement, ProviderHealthState, ProviderPolicy
from app.providers.base import IdentifierRecord, InstrumentProfile, ListingRecord
from app.routers.instruments import (
    _create_from_provider,
    _ensure_52w_stats,
    _instrument_search_exchange,
    _needs_52w_stats_refresh,
    acquire_instrument,
    discover_instruments,
)
from app.schemas.instrument import (
    FieldProvenanceOut,
    InstrumentIdentifierOut,
    InstrumentListingOut,
    InstrumentStatsOut,
)
from app.schemas.instrument_acquisition import (
    InstrumentAcquireRequest,
    InstrumentDiscoveryRequest,
    ProviderCandidateBinding,
)
from app.services import market_data
from app.services.instrument_mastering import (
    apply_profile_to_instrument,
    instrument_type_for_quote_type,
    store_profile_snapshot,
)
from app.services.provider_quota_coordinator import (
    ProviderQuotaAdmissionError,
    ProviderQuotaCoordinatorError,
)
from app.services.provider_runtime import (
    _EXPLICIT_ACQUISITION_CONTEXT,
    ProviderCapability,
    ProviderNoDataError,
    ProviderQuotaUnknownError,
    ProviderRateLimitError,
    ProviderRequestScopeDeniedError,
    seed_provider_runtime,
)
from tests.unit.conftest import AsyncSessionAdapter


def test_shared_wire_datetime_normalizes_aware_and_naive_provenance_values():
    assert wire_datetime(datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)) == ("2026-01-02T03:04:05Z")
    assert wire_datetime(datetime.fromisoformat("2026-01-02T05:04:05+02:00")) == (
        "2026-01-02T03:04:05Z"
    )
    assert wire_datetime(datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02T03:04:05Z"
    assert wire_datetime(None) is None


def test_shared_wire_datetime_normalizes_offsets_to_utc_z():
    aware = datetime.fromisoformat("2026-01-02T05:04:05+02:00")
    naive = datetime(2026, 1, 2, 3, 4, 5)
    assert wire_datetime(aware) == "2026-01-02T03:04:05Z"
    assert wire_datetime(naive) == "2026-01-02T03:04:05Z"


def test_history_availability_exposes_deepest_eligible_reviewed_bound(
    client, auth_headers, instrument, monkeypatch
):
    providers = [
        SimpleNamespace(
            provider_name="massive",
            entitlement=SimpleNamespace(
                quota_policy={"history_constraints": {"max_lookback_years": 2}}
            ),
        ),
        SimpleNamespace(
            provider_name="long_history",
            entitlement=SimpleNamespace(
                quota_policy={"history_constraints": {"max_lookback_years": 6}}
            ),
        ),
    ]
    calls = []

    async def _qualified(_db, selected):
        assert selected.id == instrument.id
        return object()

    async def _resolve(_db, capability, **kwargs):
        calls.append((capability, kwargs))
        return providers

    monkeypatch.setattr("app.routers.instruments._qualified_identity", _qualified)
    monkeypatch.setattr("app.routers.instruments.resolve_provider_chain", _resolve)
    before = datetime.now(UTC)
    response = client.get(
        f"/api/v1/instruments/{instrument.id}/history-availability?timeframe=D1&adjusted=true",
        headers=auth_headers,
    )
    after = datetime.now(UTC)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["instrument_id"] == instrument.id
    assert body["symbol"] == instrument.symbol
    assert body["timeframe"] == "D1"
    assert body["adjusted"] is True
    assert body["status"] == "eligible"
    assert body["reason_code"] is None
    assert body["max_requested_bars"] == max(1, int(settings.PROVIDER_ON_DEMAND_MAX_REQUESTED_BARS))
    bound = datetime.fromisoformat(body["earliest_start"].replace("Z", "+00:00"))
    assert before.replace(year=before.year - 6) - timedelta(seconds=1) <= bound
    assert bound <= after.replace(year=after.year - 6) + timedelta(seconds=1)
    assert calls[0][0] == ProviderCapability.PRICE_HISTORY
    resolver_args = calls[0][1]
    assert {
        key: resolver_args[key]
        for key in (
            "instrument_id",
            "provider_symbol",
            "operation",
            "adjusted",
            "read_only",
        )
    } == {
        "instrument_id": instrument.id,
        "provider_symbol": instrument.symbol,
        "operation": "fetch_ohlcv:D1",
        "adjusted": True,
        "read_only": True,
    }
    assert resolver_args["operation_cost_overrides"]["massive"] >= 1


def test_history_availability_uses_exact_scope_with_request_driven_routing(
    client, auth_headers, db, instrument, monkeypatch, tmp_path
):
    async_db = AsyncSessionAdapter(db)
    asyncio.run(seed_provider_runtime(async_db))
    source = db.query(DataSource).filter_by(name="massive").one()
    policy = (
        db.query(ProviderPolicy)
        .filter_by(data_source_id=source.id, capability=ProviderCapability.PRICE_HISTORY)
        .one()
    )
    entitlement = (
        db.query(ProviderEntitlement)
        .filter_by(data_source_id=source.id, capability=ProviderCapability.PRICE_HISTORY)
        .one()
    )
    health = (
        db.query(ProviderHealthState)
        .filter_by(data_source_id=source.id, capability=ProviderCapability.PRICE_HISTORY)
        .one()
    )
    now = datetime.now(UTC)
    policy.is_enabled = True
    policy.quota_scope = "massive-history-availability-test"
    policy.quota_source = "offline reviewed fixture"
    policy.quota_verified_at = now
    policy.quota_contract = {
        "reset": "rolling",
        "operation_costs": {"fetch_ohlcv": 1},
        "dimensions": [
            {
                "name": "requests_per_minute",
                "limit": 5,
                "window_seconds": 60,
                "unit": "requests",
                "scope": "massive-history-availability-test",
                "source": "offline reviewed fixture",
                "reset": "rolling",
            }
        ],
    }
    entitlement.configured_plan = "reviewed-free-history-test"
    entitlement.is_free = True
    entitlement.authentication_required = True
    entitlement.live_probe_status = "passed"
    entitlement.enabled_environments = [settings.APP_ENV]
    entitlement.review_due_at = now + timedelta(days=1)
    entitlement.quota_policy = {"history_constraints": {"max_lookback_years": 2}}
    instrument.identity_status = "resolved"
    instrument.domain_key = "figi:BBG00HISTORYTEST1"
    instrument.primary_identifier_type = InstrumentIdentifierType.FIGI.value
    instrument.primary_identifier_value = "BBG00HISTORYTEST1"
    exchange = Exchange(
        mic="XNAS",
        name="Nasdaq history availability fixture",
        country_code="US",
        timezone="America/New_York",
        currency="USD",
    )
    db.add(exchange)
    db.flush()
    db.add(
        InstrumentListing(
            instrument_id=instrument.id,
            exchange_id=exchange.id,
            ticker=instrument.symbol,
            currency="USD",
            is_primary=True,
            is_active=True,
            source="offline history availability fixture",
        )
    )
    db.flush()

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", True)
    monkeypatch.setattr(settings, "PROVIDER_CHECKPOINT_OPERATION_HOLDS", {})
    monkeypatch.setattr(settings, "MASSIVE_API_KEY", "unit-test-not-a-real-key")
    monkeypatch.setattr(settings, "MASSIVE_MARKET_DATA_USE_AUTHORIZED", True)
    monkeypatch.setattr(
        settings,
        "MASSIVE_MARKET_DATA_USE_AUTHORITY_REFERENCE",
        "unit-test reviewed scope",
    )
    monkeypatch.setattr(
        settings,
        "MASSIVE_MARKET_DATA_USE_AUTHORITY_SCOPE",
        "written_automated_persistent_archive_and_audience",
    )
    monkeypatch.setattr(settings, "MASSIVE_MARKET_DATA_USE_REVIEWED_AT", now)
    monkeypatch.setattr(settings, "MASSIVE_MARKET_DATA_USE_EXPIRES_AT", now + timedelta(days=1))
    ledger_path = tmp_path / "must-not-be-created.sqlite3"
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_PATH", str(ledger_path))
    monkeypatch.setattr(settings, "PROVIDER_QUOTA_LEDGER_DATABASE_URL", "")
    monkeypatch.setattr(
        "app.routers.instruments.execute_provider_call",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("history availability must never execute a provider call")
        ),
    )
    before_policy = (policy.is_enabled, policy.effective_score, policy.quota_contract)
    before_entitlement = (
        entitlement.revision,
        entitlement.configured_plan,
        entitlement.live_probe_status,
        entitlement.quota_policy,
    )
    before_health = (health.observed_score, health.failure_streak, health.circuit_open_until)

    before = datetime.now(UTC)
    response = client.get(
        f"/api/v1/instruments/{instrument.id}/history-availability?timeframe=D1&adjusted=true",
        headers=auth_headers,
    )
    after = datetime.now(UTC)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "eligible", body
    assert body["reason_code"] is None
    earliest = datetime.fromisoformat(body["earliest_start"].replace("Z", "+00:00"))
    assert before.replace(year=before.year - 2) - timedelta(seconds=1) <= earliest
    assert earliest <= after.replace(year=after.year - 2) + timedelta(seconds=1)
    db.expire_all()
    policy = db.query(ProviderPolicy).filter_by(id=policy.id).one()
    entitlement = db.query(ProviderEntitlement).filter_by(id=entitlement.id).one()
    health = db.query(ProviderHealthState).filter_by(id=health.id).one()
    assert (policy.is_enabled, policy.effective_score, policy.quota_contract) == before_policy
    assert (
        entitlement.revision,
        entitlement.configured_plan,
        entitlement.live_probe_status,
        entitlement.quota_policy,
    ) == before_entitlement
    assert (
        health.observed_score,
        health.failure_streak,
        health.circuit_open_until,
    ) == before_health
    assert not ledger_path.exists()


@pytest.mark.parametrize(
    ("resolved", "expected_reason"),
    [
        ([], "no_eligible_history_provider"),
        (
            [
                SimpleNamespace(
                    provider_name="massive",
                    entitlement=SimpleNamespace(quota_policy={"history_depth": "unknown"}),
                )
            ],
            "history_depth_unknown",
        ),
    ],
)
def test_history_availability_holds_without_a_current_reviewed_bound(
    client, auth_headers, instrument, monkeypatch, resolved, expected_reason
):
    async def _qualified(_db, _instrument):
        return object()

    async def _resolve(*_args, **_kwargs):
        return resolved

    monkeypatch.setattr("app.routers.instruments._qualified_identity", _qualified)
    monkeypatch.setattr("app.routers.instruments.resolve_provider_chain", _resolve)
    response = client.get(
        f"/api/v1/instruments/{instrument.id}/history-availability?timeframe=W1&adjusted=false",
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "held"
    assert body["earliest_start"] is None
    assert body["reason_code"] == expected_reason
    assert body["timeframe"] == "W1"
    assert body["adjusted"] is False


def test_instrument_response_schemas_keep_pydantic_datetime_json_contract():
    naive = datetime(2026, 9, 12, 14, 30)
    aware = datetime(2026, 9, 12, 16, 30, tzinfo=UTC)

    stats = InstrumentStatsOut(computed_at=naive)
    provenance = FieldProvenanceOut(
        source="provider",
        fetched_at=naive,
        observed_at=aware,
    )
    listing = InstrumentListingOut(
        ticker="SPY",
        is_primary=True,
        is_active=True,
        effective_at=naive,
        known_at=aware,
        delisted_at=None,
    )
    identifier = InstrumentIdentifierOut(
        identifier_type="figi",
        identifier_value="BBG000B9XRY4",
        is_primary=True,
        is_active=True,
        effective_at=naive,
        known_at=aware,
        retired_at=None,
    )

    assert stats.model_dump(mode="json")["computed_at"] == "2026-09-12T14:30:00Z"
    assert provenance.model_dump(mode="json")["fetched_at"] == "2026-09-12T14:30:00Z"
    assert provenance.model_dump(mode="json")["observed_at"] == "2026-09-12T16:30:00Z"
    assert listing.model_dump(mode="json")["effective_at"] == "2026-09-12T14:30:00Z"
    assert listing.model_dump(mode="json")["known_at"] == "2026-09-12T16:30:00Z"
    assert identifier.model_dump(mode="json")["effective_at"] == "2026-09-12T14:30:00Z"
    assert identifier.model_dump(mode="json")["known_at"] == "2026-09-12T16:30:00Z"


def test_request_driven_mode_preserves_ordinary_local_instrument_reads(
    client, auth_headers, instrument, monkeypatch
):
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)

    def forbidden_transport(*_args, **_kwargs):
        raise AssertionError("ordinary local instrument reads must not query providers")

    monkeypatch.setattr(
        "app.routers.instruments.search_provider_instruments_async", forbidden_transport
    )
    monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", forbidden_transport)
    monkeypatch.setattr("app.routers.instruments._create_from_provider", forbidden_transport)
    monkeypatch.setattr("app.routers.instruments._needs_52w_stats_refresh", lambda _row: False)

    search = client.get(
        "/api/v1/instruments/search", params={"q": instrument.symbol}, headers=auth_headers
    )
    assert search.status_code == 200, search.text
    assert any(row["symbol"] == instrument.symbol for row in search.json())

    detail = client.get(f"/api/v1/instruments/{instrument.symbol}", headers=auth_headers)
    assert detail.status_code == 200, detail.text

    unknown = client.get("/api/v1/instruments/UNKNOWN_ON_DEMAND", headers=auth_headers)
    assert unknown.status_code == 404
    unknown_search = client.get(
        "/api/v1/instruments/search",
        params={"q": "UNKNOWN_ON_DEMAND"},
        headers=auth_headers,
    )
    assert unknown_search.status_code == 200
    assert unknown_search.json() == []

    expression = client.post(
        "/api/v1/instruments/resolve-expression",
        json={"expression": f"=UNKNOWNONDEMAND/{instrument.symbol}"},
        headers=auth_headers,
    )
    assert expression.status_code == 404


def test_legacy_search_keeps_provider_discovery_when_request_driven_mode_is_disabled(
    client, auth_headers, monkeypatch
):
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", False)
    calls = 0

    async def _search(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return [
            {
                "symbol": "UNSEEDED_PROVIDER_SYMBOL",
                "name": "Provider Search Result",
                "exchange": "XNYS",
                "type": "EQUITY",
            }
        ]

    monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
    response = client.get(
        "/api/v1/instruments/search",
        params={"q": "UNSEEDED_PROVIDER_SYMBOL"},
        headers=auth_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()[0]["symbol"] == "UNSEEDED_PROVIDER_SYMBOL"
    assert calls == 1


def _discovery_exact_profile(symbol: str = "QXDISC") -> InstrumentProfile:
    return InstrumentProfile(
        provider="massive",
        symbol=symbol,
        canonical_symbol=symbol,
        name="Exact discovery profile",
        quote_type="ETF",
        exchange="XNAS",
        identifiers=[
            IdentifierRecord(
                identifier_type="figi",
                identifier_value="BBG00QXDISC01",
                is_primary=True,
            )
        ],
        listings=[
            ListingRecord(
                provider_symbol=symbol,
                exchange_code="XNAS",
                provider_instrument_type="ETF",
                is_primary=True,
            )
        ],
    )


def _discovery_fuzzy_page() -> list[dict]:
    return [
        {
            "symbol": f"A{i}DISC",
            "name": "Unrelated bounded fuzzy result",
            "exchange": "XNAS",
            "type": "ETF",
            "provider": "massive",
        }
        for i in range(10)
    ]


def _discovery_search_outcome() -> dict:
    return {
        "provider": "massive",
        "capability": ProviderCapability.INSTRUMENT_SEARCH.value,
        "operation": "search_instruments",
        "status": "returned",
        "result_count": 10,
    }


@pytest.mark.asyncio
async def test_discovery_exact_profile_fallback_is_selectable_and_does_not_create_canonical_state(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    symbol = "QXDISC"
    profile = _discovery_exact_profile(symbol)
    profile_calls = 0

    async def _search(_db, query, *, source_outcomes=None):
        assert query == symbol
        source_outcomes.append(_discovery_search_outcome())
        return _discovery_fuzzy_page()

    async def _status(_db):
        return [
            {
                "provider": "massive",
                "capability": ProviderCapability.INSTRUMENT_METADATA.value,
                "routing_eligible": True,
            }
        ]

    async def _exact_profile(_db, capability, operation, **kwargs):
        nonlocal profile_calls
        profile_calls += 1
        scope = _EXPLICIT_ACQUISITION_CONTEXT.get()
        assert scope is not None
        assert scope.request_id == "discover-qx-profile"
        assert scope.symbol == symbol
        assert scope.provider_names == frozenset({"massive"})
        assert scope.operations == frozenset(
            {(ProviderCapability.INSTRUMENT_METADATA, "get_instrument_profile")}
        )
        assert capability == ProviderCapability.INSTRUMENT_METADATA
        assert operation == "get_instrument_profile"
        assert kwargs["provider_name"] == "massive"
        assert kwargs["provider_symbol"] == symbol
        assert kwargs["usage_identity"] == symbol
        assert kwargs["treat_empty_as_failure"] is True

        class FakeProvider:
            def get_instrument_profile(self, requested):
                assert requested == symbol
                return profile

        assert kwargs["invoke"](FakeProvider(), symbol) is profile
        assert kwargs["response_items"](profile) == 1
        return SimpleNamespace(provider_name="massive", result=profile)

    monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
    monkeypatch.setattr("app.routers.instruments.list_provider_status", _status)
    monkeypatch.setattr("app.routers.instruments.execute_provider_call", _exact_profile)

    response = await discover_instruments(
        InstrumentDiscoveryRequest(
            query=symbol,
            types=["ETF"],
            request_id="discover-qx-profile",
        ),
        async_db,
        None,
    )

    assert response.status == "complete"
    assert response.candidates[0].model_dump() == {
        "symbol": symbol,
        "name": "Exact discovery profile",
        "exchange": "XNAS",
        "type": "ETF",
        "provider": "massive",
        "instrument_id": None,
        "identity_status": "provider_candidate",
    }
    assert len(response.candidates) == 10
    assert profile_calls == 1
    assert db.query(Instrument).filter_by(symbol=symbol).one_or_none() is None
    assert (
        db.query(InstrumentProviderSymbol).filter_by(provider_symbol=symbol).one_or_none() is None
    )


@pytest.mark.asyncio
async def test_discovery_exact_profile_fallback_respects_metadata_holds_without_transport(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    exact_calls = 0

    async def _search(_db, _query, *, source_outcomes=None):
        source_outcomes.append(_discovery_search_outcome())
        return _discovery_fuzzy_page()

    async def _status(_db):
        return [
            {
                "provider": "massive",
                "capability": ProviderCapability.INSTRUMENT_METADATA.value,
                "routing_eligible": False,
                "quota_state": "unknown",
            }
        ]

    async def _forbidden_exact(*_args, **_kwargs):
        nonlocal exact_calls
        exact_calls += 1
        raise AssertionError("metadata held; exact profile transport is forbidden")

    monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
    monkeypatch.setattr("app.routers.instruments.list_provider_status", _status)
    monkeypatch.setattr("app.routers.instruments.execute_provider_call", _forbidden_exact)

    response = await discover_instruments(
        InstrumentDiscoveryRequest(query="QXDISC", request_id="discover-held-metadata"),
        async_db,
        None,
    )

    assert response.status == "partial"
    assert exact_calls == 0
    assert any(
        item.capability == ProviderCapability.INSTRUMENT_METADATA.value
        and item.status == "held"
        and item.reason_code == "unknown"
        for item in response.source_outcomes
    )
    assert db.query(Instrument).filter_by(symbol="QXDISC").one_or_none() is None


@pytest.mark.asyncio
async def test_discovery_preserves_temporary_search_hold_and_retry_time(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    retry_at = datetime.now(UTC) + timedelta(seconds=29)

    async def _held_search(_db, _query, *, source_outcomes=None):
        source_outcomes.append(
            {
                "provider": "massive",
                "capability": ProviderCapability.INSTRUMENT_SEARCH.value,
                "operation": "search_instruments",
                "status": "held",
                "reason_code": "provider_quota_admission_denied",
                "retry_at": retry_at,
            }
        )
        return []

    monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _held_search)
    response = await discover_instruments(
        InstrumentDiscoveryRequest(query="XLB", request_id="discover-search-window-held"),
        async_db,
        None,
    )

    assert response.status == "held"
    assert response.candidates == []
    assert len(response.source_outcomes) == 1
    assert response.source_outcomes[0].status == "held"
    assert response.source_outcomes[0].retry_at == retry_at


@pytest.mark.asyncio
async def test_discovery_search_hold_prevents_exact_metadata_fallback(db, monkeypatch):
    async_db = AsyncSessionAdapter(db)
    exact_calls = 0

    async def _search(_db, _query, *, source_outcomes=None):
        source_outcomes.append(
            {
                **_discovery_search_outcome(),
                "status": "held",
                "reason_code": "search_policy_disabled",
            }
        )
        return []

    async def _status(_db):
        raise AssertionError("a held search must not trigger metadata admission or fallback")

    async def _forbidden_exact(*_args, **_kwargs):
        nonlocal exact_calls
        exact_calls += 1
        raise AssertionError("a held search must not trigger exact profile transport")

    monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
    monkeypatch.setattr("app.routers.instruments.list_provider_status", _status)
    monkeypatch.setattr("app.routers.instruments.execute_provider_call", _forbidden_exact)

    response = await discover_instruments(
        InstrumentDiscoveryRequest(query="QXDISC", request_id="discover-held-search"),
        async_db,
        None,
    )

    assert response.status == "held"
    assert response.candidates == []
    assert exact_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("hold", "expected_reason"),
    [
        ("quota", "provider_quota_admission_denied"),
        ("rate", "provider_capacity_unavailable"),
        ("scope", "exact_profile_scope_held"),
    ],
)
async def test_discovery_exact_profile_runtime_holds_remain_held(
    db, monkeypatch, hold, expected_reason
):
    async_db = AsyncSessionAdapter(db)

    async def _search(_db, _query, *, source_outcomes=None):
        source_outcomes.append(_discovery_search_outcome())
        return _discovery_fuzzy_page()

    async def _status(_db):
        return [
            {
                "provider": "massive",
                "capability": ProviderCapability.INSTRUMENT_METADATA.value,
                "routing_eligible": True,
            }
        ]

    async def _held_exact(*_args, **_kwargs):
        if hold == "quota":
            raise ProviderQuotaAdmissionError("quota reservation denied")
        if hold == "rate":
            raise ProviderRateLimitError("massive", "capacity denied")
        raise ProviderRequestScopeDeniedError("exact_profile_scope_held")

    monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
    monkeypatch.setattr("app.routers.instruments.list_provider_status", _status)
    monkeypatch.setattr("app.routers.instruments.execute_provider_call", _held_exact)

    response = await discover_instruments(
        InstrumentDiscoveryRequest(query="QXDISC", request_id=f"discover-held-{hold}"),
        async_db,
        None,
    )

    assert response.status == "partial"
    assert all(candidate.symbol != "QXDISC" for candidate in response.candidates)
    assert any(
        item.capability == ProviderCapability.INSTRUMENT_METADATA.value
        and item.status == "held"
        and item.reason_code == expected_reason
        for item in response.source_outcomes
    )


@pytest.mark.asyncio
async def test_discovery_exact_fallback_retains_provider_for_fresh_empty_search_cache(
    monkeypatch,
):
    class EmptySearchCacheDB:
        reads = 0

        async def execute(self, _statement):
            self.reads += 1
            return SimpleNamespace(
                scalar_one_or_none=lambda: SimpleNamespace(payload={"results": []})
            )

    async_db = EmptySearchCacheDB()
    resolved = SimpleNamespace(
        provider_name="massive",
        data_source=SimpleNamespace(id=17),
        policy=SimpleNamespace(freshness_seconds=300),
    )
    profile = _discovery_exact_profile()
    exact_calls = 0

    async def _resolved_chain(*_args, **_kwargs):
        return [resolved]

    async def _status(_db):
        return [
            {
                "provider": "massive",
                "capability": ProviderCapability.INSTRUMENT_METADATA.value,
                "routing_eligible": True,
            }
        ]

    async def _exact_profile(_db, capability, operation, **kwargs):
        nonlocal exact_calls
        exact_calls += 1
        assert capability == ProviderCapability.INSTRUMENT_METADATA
        assert operation == "get_instrument_profile"
        assert kwargs["provider_name"] == "massive"
        return SimpleNamespace(provider_name="massive", result=profile)

    monkeypatch.setattr(market_data, "resolve_provider_chain", _resolved_chain)
    monkeypatch.setattr("app.routers.instruments.list_provider_status", _status)
    monkeypatch.setattr("app.routers.instruments.execute_provider_call", _exact_profile)

    response = await discover_instruments(
        InstrumentDiscoveryRequest(query="QXDISC", request_id="discover-empty-cache"),
        async_db,
        None,
    )

    assert response.candidates[0].symbol == "QXDISC"
    assert response.candidates[0].provider == "massive"
    assert exact_calls == 1
    assert async_db.reads == 1
    search_outcome = next(
        item
        for item in response.source_outcomes
        if item.capability == ProviderCapability.INSTRUMENT_SEARCH.value
    )
    assert search_outcome.status == "cache_hit"
    assert search_outcome.result_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch",
    ["provider", "symbol", "listing", "domain", "type_filter"],
)
async def test_discovery_exact_profile_fallback_rejects_identity_and_filter_mismatches(
    db, monkeypatch, mismatch
):
    async_db = AsyncSessionAdapter(db)
    symbol = "QXDISC"
    profile = _discovery_exact_profile(symbol)
    if mismatch == "provider":
        profile.provider = "fmp"
    elif mismatch == "symbol":
        profile.symbol = "QXOTHER"
        profile.canonical_symbol = "QXOTHER"
    elif mismatch == "listing":
        profile.listings[0].provider_symbol = "QXOTHER"
    elif mismatch == "domain":
        profile.identifiers = []

    async def _search(_db, _query, *, source_outcomes=None):
        source_outcomes.append(_discovery_search_outcome())
        return _discovery_fuzzy_page()

    async def _status(_db):
        return [
            {
                "provider": "massive",
                "capability": ProviderCapability.INSTRUMENT_METADATA.value,
                "routing_eligible": True,
            }
        ]

    async def _exact_profile(*_args, **kwargs):
        class FakeProvider:
            def get_instrument_profile(self, _requested):
                return profile

        return SimpleNamespace(
            provider_name="massive",
            result=kwargs["invoke"](FakeProvider(), symbol),
        )

    monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
    monkeypatch.setattr("app.routers.instruments.list_provider_status", _status)
    monkeypatch.setattr("app.routers.instruments.execute_provider_call", _exact_profile)
    body = InstrumentDiscoveryRequest(
        query=symbol,
        types=["STOCK"] if mismatch == "type_filter" else ["ETF"],
        request_id=f"discover-reject-{mismatch}",
    )

    response = await discover_instruments(body, async_db, None)

    assert all(candidate.symbol != symbol for candidate in response.candidates)
    assert db.query(Instrument).filter_by(symbol=symbol).one_or_none() is None
    if mismatch != "type_filter":
        assert any(
            item.reason_code == "exact_profile_identity_or_listing_mismatch"
            for item in response.source_outcomes
        )
    else:
        assert response.status == "no_match"
        assert any(
            item.reason_code == "exact_profile_excluded_by_type_filter"
            for item in response.source_outcomes
        )


@pytest.mark.asyncio
async def test_discovery_exact_profile_fallback_does_not_run_for_free_text_or_filtered_fuzzy_exact(
    db, monkeypatch
):
    async_db = AsyncSessionAdapter(db)
    exact_calls = 0

    async def _search(_db, query, *, source_outcomes=None):
        source_outcomes.append(_discovery_search_outcome())
        if query == "Ford Motor":
            return _discovery_fuzzy_page()
        return [
            {
                "symbol": "QXDISC",
                "name": "Exact fuzzy result",
                "exchange": "XNAS",
                "type": "ETF",
                "provider": "massive",
            }
        ]

    async def _status(_db):
        return [
            {
                "provider": "massive",
                "capability": ProviderCapability.INSTRUMENT_METADATA.value,
                "routing_eligible": True,
            }
        ]

    async def _forbidden_exact(*_args, **_kwargs):
        nonlocal exact_calls
        exact_calls += 1
        raise AssertionError("free text or an exact fuzzy result must not trigger fallback")

    monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
    monkeypatch.setattr("app.routers.instruments.list_provider_status", _status)
    monkeypatch.setattr("app.routers.instruments.execute_provider_call", _forbidden_exact)

    free_text = await discover_instruments(
        InstrumentDiscoveryRequest(query="Ford Motor", request_id="discover-free-text"),
        async_db,
        None,
    )
    filtered_exact = await discover_instruments(
        InstrumentDiscoveryRequest(
            query="QXDISC",
            types=["STOCK"],
            request_id="discover-filtered-exact",
        ),
        async_db,
        None,
    )

    assert exact_calls == 0
    assert all(candidate.symbol != "QXDISC" for candidate in filtered_exact.candidates)
    assert free_text.candidates


class TestInstrumentAutoCreate:
    @pytest.mark.asyncio
    async def test_rejects_non_exact_provider_match(self, db, monkeypatch):
        async_db = AsyncSessionAdapter(db)

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "CSCOII-USD",
                    "name": "Fake Coin",
                    "exchange": "CoinGecko",
                    "type": "CRYPTOCURRENCY",
                }
            ]

        async def _profile(*_args, **_kwargs):
            return InstrumentProfile(
                provider="coingecko",
                symbol="CSCOII-USD",
                canonical_symbol="CSCOII-USD",
                name="Fake Coin",
                quote_type="CRYPTOCURRENCY",
                listings=[ListingRecord(provider_symbol="CSCOII-USD", is_primary=True)],
            )

        async def _ingest(*_args, **_kwargs):
            raise AssertionError(
                "ingest_provider_profile should not be called for non-exact matches"
            )

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr("app.routers.instruments.ingest_provider_profile", _ingest)

        created = await _create_from_provider("CSCOII", async_db)

        assert created is None
        assert db.query(Instrument).filter(Instrument.symbol == "CSCOII").one_or_none() is None

    @pytest.mark.asyncio
    async def test_creates_from_exact_provider_match(self, db, instrument_type, monkeypatch):
        async_db = AsyncSessionAdapter(db)
        seen_provider_name = None

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "CSCO",
                    "name": "Cisco Systems",
                    "exchange": "NMS",
                    "type": "EQUITY",
                    "provider": "yfinance",
                }
            ]

        async def _profile(*_args, provider_name=None, **_kwargs):
            nonlocal seen_provider_name
            seen_provider_name = provider_name
            return InstrumentProfile(
                provider="yfinance",
                symbol="CSCO",
                canonical_symbol="CSCO",
                name="Cisco Systems",
                currency="USD",
                quote_type="EQUITY",
                exchange="NMS",
                listings=[
                    ListingRecord(provider_symbol="CSCO", exchange_code="NMS", is_primary=True)
                ],
            )

        async def _ingest(db_session, profile, **_kwargs):
            instrument = Instrument(
                symbol=profile.canonical_symbol,
                name=profile.name,
                currency=profile.currency,
                instrument_type_id=instrument_type.id,
                is_active=True,
            )
            db_session.add(instrument)
            await db_session.flush()
            return instrument

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr("app.routers.instruments.ingest_provider_profile", _ingest)

        created = await _create_from_provider("CSCO", async_db)

        assert created is not None
        assert created.symbol == "CSCO"
        assert seen_provider_name == "yfinance"


class TestExplicitAcquireCanonicalIdentity:
    @pytest.mark.asyncio
    async def test_cached_qualified_identity_reconciles_etv_without_provider_transport(
        self, db, instrument_type, monkeypatch
    ):
        async_db = AsyncSessionAdapter(db)
        instrument = Instrument(
            symbol="GENV",
            name="Generic Exchange Traded Vehicle",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            identity_status="resolved",
            domain_key="figi:BBG000GENV001",
            primary_identifier_type="figi",
            primary_identifier_value="BBG000GENV001",
        )
        exchange = Exchange(mic="ARCX", name="NYSE Arca")
        db.add_all([instrument, exchange])
        db.flush()
        db.add(
            InstrumentListing(
                instrument_id=instrument.id,
                exchange_id=exchange.id,
                ticker="GENV",
                currency="USD",
                is_primary=True,
                is_active=True,
                source="massive",
            )
        )
        db.flush()
        profile = InstrumentProfile(
            provider="massive",
            symbol="GENV",
            canonical_symbol="GENV",
            name="Generic Exchange Traded Vehicle",
            currency="USD",
            quote_type="ETV",
            exchange="ARCX",
            raw_payload={"ticker": "GENV", "type": "ETV"},
            listings=[ListingRecord(provider_symbol="GENV", exchange_code="ARCX")],
        )
        retained_classification = await store_profile_snapshot(async_db, instrument, profile)
        later_nonclassifying_profile = InstrumentProfile(
            provider="yfinance",
            symbol="GENV",
            canonical_symbol="GENV",
            name="Generic Exchange Traded Vehicle",
            currency="USD",
            quote_type=None,
            raw_payload={"ticker": "GENV"},
        )
        await store_profile_snapshot(
            async_db,
            instrument,
            later_nonclassifying_profile,
            observed_at=datetime.now(UTC) + timedelta(seconds=1),
        )

        async def forbidden_transport(*_args, **_kwargs):
            raise AssertionError("cached qualified acquisition must not call a provider")

        monkeypatch.setattr(
            "app.routers.instruments.search_provider_instruments_async", forbidden_transport
        )
        monkeypatch.setattr(
            "app.routers.instruments.get_provider_profile_async", forbidden_transport
        )

        response = await acquire_instrument(
            InstrumentAcquireRequest(symbol="GENV", request_id="cached-etv-reconcile"),
            async_db,
        )

        db.refresh(instrument)
        assert response.status == "resolved"
        assert response.instrument.instrument_id == instrument.id
        assert response.instrument.instrument_type == "Exchange Traded Vehicle"
        assert instrument.symbol == "GENV"
        assert instrument.domain_key == "figi:BBG000GENV001"
        assert instrument.primary_identifier_type == "figi"
        assert instrument.primary_identifier_value == "BBG000GENV001"
        assert instrument.field_provenance["instrument_type"]["note"].startswith(
            "provider_quote_type=ETV"
        )
        assert instrument.field_provenance["instrument_type"]["source"] == "massive"
        assert instrument.field_provenance["instrument_type"]["observed_at"] == (
            retained_classification.observed_at.replace(tzinfo=UTC).isoformat()
        )
        assert instrument.field_provenance["instrument_type"]["fetched_at"] == (
            retained_classification.fetched_at.replace(tzinfo=UTC).isoformat()
        )
        assert instrument.field_provenance["instrument_type"]["reconciled_at"]

    @pytest.mark.parametrize(
        ("code", "expected"),
        [
            ("ETF", ("Equity", "ETF", "ETF")),
            ("ETN", ("Exchange Traded Product", "ETN", "ETN")),
            ("ETV", ("Exchange Traded Product", "Exchange Traded Vehicle", "ETV")),
            (
                "UNRECOGNIZED_PROVIDER_CODE",
                ("Unclassified", "Unclassified", "UNRECOGNIZED_PROVIDER_CODE"),
            ),
        ],
    )
    def test_provider_quote_type_does_not_collapse_exchange_traded_categories(self, code, expected):
        assert instrument_type_for_quote_type(code) == expected

    @pytest.mark.asyncio
    async def test_new_profile_persists_provider_etv_as_distinct_vehicle_type(self, db):
        async_db = AsyncSessionAdapter(db)
        profile = InstrumentProfile(
            provider="massive",
            symbol="GENW",
            canonical_symbol="GENW",
            name="Generic Exchange Traded Vehicle",
            quote_type="ETV",
            exchange="ARCX",
            listings=[ListingRecord(provider_symbol="GENW", exchange_code="ARCX")],
            raw_payload={"ticker": "GENW", "type": "ETV"},
        )

        created = await apply_profile_to_instrument(
            async_db, profile, allow_external_identifier=False
        )
        persisted_type = db.get(InstrumentType, created.instrument_type_id)

        assert created.symbol == "GENW"
        assert persisted_type.asset_class.name == "Exchange Traded Product"
        assert persisted_type.name == "Exchange Traded Vehicle"
        assert created.field_provenance["instrument_type"]["note"] == "provider_quote_type=ETV"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("existing_scaffold", [False, True])
    async def test_promotes_scaffold_from_exact_authoritative_provider_profile(
        self, db, instrument_type, monkeypatch, existing_scaffold
    ):
        async_db = AsyncSessionAdapter(db)
        scaffold = None
        if existing_scaffold:
            scaffold = Instrument(
                symbol="OIH",
                name="OIH industry proxy ETF",
                currency="USD",
                instrument_type_id=instrument_type.id,
                is_active=True,
                identity_status="provisional",
                primary_identifier_type="composite_figi",
                primary_identifier_value="BBG000D02J82",
            )
            arca = Exchange(mic="ARCX", name="NYSE Arca")
            massive = DataSource(name="massive", is_active=True, config={})
            db.add_all([scaffold, arca, massive])
            db.flush()
            db.add_all(
                [
                    InstrumentIdentifier(
                        instrument_id=scaffold.id,
                        data_source_id=massive.id,
                        identifier_type=InstrumentIdentifierType.COMPOSITE_FIGI,
                        identifier_value="BBG000D02J82",
                        is_primary=True,
                        is_active=True,
                    ),
                    InstrumentProviderSymbol(
                        instrument_id=scaffold.id,
                        data_source_id=massive.id,
                        provider_symbol="OIH",
                        provider_exchange_code="ARCX",
                        provider_instrument_type="ETF",
                        is_primary=True,
                        is_active=True,
                    ),
                ]
            )
            db.add(
                InstrumentListing(
                    instrument_id=scaffold.id,
                    exchange_id=arca.id,
                    ticker="OIH",
                    currency="USD",
                    is_primary=True,
                    is_active=True,
                    source="massive",
                )
            )
            db.flush()

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "OIH",
                    "name": "VanEck Oil Services ETF",
                    "exchange": "ARCX",
                    "type": "ETF",
                    "provider": "massive",
                }
            ]

        async def _profile(*_args, provider_name=None, **_kwargs):
            assert provider_name == "massive"
            return InstrumentProfile(
                provider="massive",
                symbol="OIH",
                canonical_symbol="OIH",
                name="VanEck Oil Services ETF",
                currency="USD",
                quote_type="ETF",
                exchange="ARCX",
                identifiers=[
                    IdentifierRecord(
                        identifier_type="composite_figi",
                        identifier_value="BBG000D02J82",
                        is_primary=True,
                    )
                ],
                listings=[
                    ListingRecord(
                        provider_symbol="OIH",
                        exchange_code="ARCX",
                        currency="USD",
                        provider_instrument_type="ETF",
                        is_primary=True,
                    )
                ],
            )

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr(
            "app.services.instrument_mastering.ensure_external_identifier",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("explicit acquisition must not run fallback identifier lookup")
            ),
        )

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol="OIH",
                provider_candidate=ProviderCandidateBinding(
                    provider="massive", symbol="OIH", exchange="ARCX"
                ),
                request_id="test-oih-authoritative-profile",
            ),
            async_db,
        )

        assert response.status == "resolved"
        assert response.instrument is not None
        persisted = db.query(Instrument).filter(Instrument.symbol == "OIH").one()
        assert response.instrument.instrument_id == persisted.id
        if scaffold is not None:
            assert persisted.id == scaffold.id
        assert response.instrument.identity_status == "resolved"
        assert response.instrument.domain_key == "composite-figi:BBG000D02J82"
        assert response.instrument.primary_identifier_type == "composite_figi"
        assert response.instrument.primary_identifier_value == "BBG000D02J82"
        assert (
            db.query(InstrumentIdentifier)
            .filter(
                InstrumentIdentifier.instrument_id == response.instrument.instrument_id,
                InstrumentIdentifier.identifier_type == InstrumentIdentifierType.COMPOSITE_FIGI,
                InstrumentIdentifier.identifier_value == "BBG000D02J82",
                InstrumentIdentifier.is_active.is_(True),
            )
            .one_or_none()
            is not None
        )

    @pytest.mark.asyncio
    async def test_exact_profile_resolves_ticker_missing_from_bounded_fuzzy_page(
        self, db, monkeypatch
    ):
        async_db = AsyncSessionAdapter(db)
        symbol = "QXTEST"
        profile = InstrumentProfile(
            provider="massive",
            symbol=symbol,
            canonical_symbol=symbol,
            name="Exact lookup test issuer",
            currency="USD",
            quote_type="ETF",
            exchange="XNAS",
            identifiers=[
                IdentifierRecord(
                    identifier_type="figi",
                    identifier_value="BBG00QXTEST01",
                    is_primary=True,
                )
            ],
            listings=[
                ListingRecord(
                    provider_symbol=symbol,
                    exchange_code="XNAS",
                    currency="USD",
                    provider_instrument_type="ETF",
                    is_primary=True,
                )
            ],
        )
        first_page = [
            {
                "symbol": f"A{i}TEST",
                "name": "Fuzzy result outside exact symbol",
                "exchange": "XNAS",
                "type": "ETF",
                "provider": "massive",
            }
            for i in range(10)
        ]

        async def _search(_db, query, *, source_outcomes=None):
            assert query == symbol
            source_outcomes.append(
                {
                    "provider": "massive",
                    "capability": ProviderCapability.INSTRUMENT_SEARCH.value,
                    "operation": "search_instruments",
                    "status": "returned",
                    "result_count": len(first_page),
                }
            )
            return first_page

        async def _no_status(_db):
            return []

        async def _exact_profile(_db, capability, operation, **kwargs):
            scope = _EXPLICIT_ACQUISITION_CONTEXT.get()
            assert scope is not None
            assert scope.request_id == "exact-profile-beyond-fuzzy-page"
            assert scope.symbol == symbol
            assert scope.operations == frozenset(
                {(ProviderCapability.INSTRUMENT_METADATA, "get_instrument_profile")}
            )
            assert scope.provider_names is None
            assert capability == ProviderCapability.INSTRUMENT_METADATA
            assert operation == "get_instrument_profile"
            assert kwargs["provider_name"] is None
            assert kwargs["provider_symbol"] == symbol
            assert kwargs["usage_identity"] == symbol
            assert kwargs["treat_empty_as_failure"] is True

            class FakeProvider:
                def get_instrument_profile(self, requested):
                    assert requested == symbol
                    return profile

            assert kwargs["invoke"](FakeProvider(), symbol) is profile
            assert kwargs["response_items"](profile) == 1
            return SimpleNamespace(provider_name="massive", result=profile)

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.list_provider_status", _no_status)
        monkeypatch.setattr("app.routers.instruments.execute_provider_call", _exact_profile)
        monkeypatch.setattr(
            "app.routers.instruments.ensure_external_identifier",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("exact profile acquisition must not infer identifiers")
            ),
        )

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol=symbol,
                request_id="exact-profile-beyond-fuzzy-page",
            ),
            async_db,
        )

        assert response.status == "resolved"
        assert response.instrument is not None
        assert response.instrument.symbol == symbol
        assert response.instrument.domain_key == "figi:BBG00QXTEST01"
        assert any(
            item.operation == "get_instrument_profile" and item.status == "returned"
            for item in response.source_outcomes
        )
        binding = db.query(InstrumentProviderSymbol).filter_by(
            instrument_id=response.instrument.instrument_id,
            data_source_id=db.query(DataSource.id).filter_by(name="massive").scalar(),
            provider_symbol=symbol,
            provider_exchange_code="XNAS",
        )
        assert binding.one_or_none() is not None

    @pytest.mark.asyncio
    async def test_exact_profile_absence_stays_no_match(self, db, monkeypatch):
        async_db = AsyncSessionAdapter(db)
        symbol = "QXABSENT"

        async def _search(_db, query, *, source_outcomes=None):
            source_outcomes.append(
                {
                    "provider": "massive",
                    "capability": ProviderCapability.INSTRUMENT_SEARCH.value,
                    "operation": "search_instruments",
                    "status": "returned",
                    "result_count": 10,
                }
            )
            return [{"symbol": f"A{i}", "provider": "massive"} for i in range(10)]

        async def _no_exact_profile(*_args, **_kwargs):
            raise ProviderNoDataError("exact ticker profile absent")

        async def _no_status(_db):
            return []

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.list_provider_status", _no_status)
        monkeypatch.setattr("app.routers.instruments.execute_provider_call", _no_exact_profile)
        monkeypatch.setattr(
            "app.routers.instruments.ingest_provider_profile",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("an absent exact profile must not be ingested")
            ),
        )

        response = await acquire_instrument(
            InstrumentAcquireRequest(symbol=symbol, request_id="exact-profile-absent"),
            async_db,
        )

        assert response.status == "no_match"
        assert response.reason_code == "exact_symbol_profile_not_found"
        assert db.query(Instrument).filter_by(symbol=symbol).one_or_none() is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("mismatch", "expected_status", "expected_reason"),
        [
            ("provider", "identity_conflict", "exact_profile_provider_mismatch"),
            ("symbol", "failed", "provider_profile_unavailable_or_mismatched"),
            ("listing", "identity_conflict", "exact_profile_listing_mismatch"),
            ("domain", "identity_conflict", "existing_placeholder_identity_conflict"),
            (
                "empty_listing",
                "identity_conflict",
                "stable_identity_or_listing_authority_missing",
            ),
        ],
    )
    async def test_exact_profile_rejects_identity_and_listing_mismatches(
        self,
        db,
        instrument_type,
        monkeypatch,
        mismatch,
        expected_status,
        expected_reason,
    ):
        async_db = AsyncSessionAdapter(db)
        symbol = "QXSAFE"
        provider = "other" if mismatch == "provider" else "massive"
        profile_symbol = "QXOTHER" if mismatch == "symbol" else symbol
        listing_symbol = "QXOTHER" if mismatch == "listing" else profile_symbol
        listing_exchange = "XNYS" if mismatch == "listing" else "XNAS"
        profile = InstrumentProfile(
            provider=provider,
            symbol=profile_symbol,
            canonical_symbol=profile_symbol,
            name="Exact profile identity regression",
            currency="USD",
            quote_type="ETF",
            exchange=None if mismatch == "empty_listing" else listing_exchange,
            identifiers=[
                IdentifierRecord(
                    identifier_type="figi",
                    identifier_value="BBG00QXSAFE01",
                    is_primary=True,
                )
            ],
            listings=[]
            if mismatch == "empty_listing"
            else [
                ListingRecord(
                    provider_symbol=listing_symbol,
                    exchange_code=listing_exchange,
                    currency="USD",
                    provider_instrument_type="ETF",
                    is_primary=True,
                )
            ],
        )
        if mismatch == "domain":
            db.add(
                Instrument(
                    symbol=symbol,
                    name="Existing provisional instrument",
                    currency="USD",
                    instrument_type_id=instrument_type.id,
                    is_active=True,
                    identity_status="provisional",
                    domain_key="figi:BBG00QXSAFE99",
                    primary_identifier_type="figi",
                    primary_identifier_value="BBG00QXSAFE99",
                )
            )
            db.flush()

        async def _search(_db, query, *, source_outcomes=None):
            source_outcomes.append(
                {
                    "provider": "massive",
                    "capability": ProviderCapability.INSTRUMENT_SEARCH.value,
                    "operation": "search_instruments",
                    "status": "returned",
                    "result_count": 10,
                }
            )
            return [{"symbol": f"A{i}", "provider": "massive"} for i in range(10)]

        async def _exact_profile(_db, _capability, _operation, **kwargs):
            assert kwargs["provider_name"] == "massive"
            return SimpleNamespace(provider_name="massive", result=profile)

        async def _no_status(_db):
            return []

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.list_provider_status", _no_status)
        monkeypatch.setattr("app.routers.instruments.execute_provider_call", _exact_profile)
        monkeypatch.setattr(
            "app.routers.instruments.ingest_provider_profile",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("mismatched exact profile must not be ingested")
            ),
        )

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol=symbol,
                provider_candidate=ProviderCandidateBinding(
                    provider="massive",
                    symbol=symbol,
                    exchange=None if mismatch in {"symbol", "empty_listing"} else "XNAS",
                ),
                request_id=f"exact-profile-mismatch-{mismatch}",
            ),
            async_db,
        )

        assert response.status == expected_status
        assert response.reason_code == expected_reason
        if mismatch == "domain":
            existing = db.query(Instrument).filter_by(symbol=symbol).one()
            assert existing.domain_key == "figi:BBG00QXSAFE99"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("lookup_error", "expected_reason"),
        [
            (
                ProviderRequestScopeDeniedError("exact_profile_scope_expired"),
                "exact_profile_scope_expired",
            ),
            (ProviderRateLimitError("massive", "rate limit"), "provider_capacity_unavailable"),
            (
                ProviderQuotaAdmissionError("quota admission denied"),
                "provider_quota_admission_denied",
            ),
            (
                ProviderQuotaUnknownError("quota contract unknown"),
                "provider_quota_contract_unknown",
            ),
        ],
    )
    async def test_exact_profile_runtime_holds_remain_held(
        self, db, monkeypatch, lookup_error, expected_reason
    ):
        async_db = AsyncSessionAdapter(db)
        symbol = "QXHELD"

        async def _search(_db, _query, *, source_outcomes=None):
            source_outcomes.append(
                {
                    "provider": "massive",
                    "capability": ProviderCapability.INSTRUMENT_SEARCH.value,
                    "operation": "search_instruments",
                    "status": "returned",
                    "result_count": 10,
                }
            )
            return [{"symbol": f"A{i}", "provider": "massive"} for i in range(10)]

        async def _held_exact(_db, capability, operation, **kwargs):
            scope = _EXPLICIT_ACQUISITION_CONTEXT.get()
            assert scope is not None
            assert scope.request_id == "exact-profile-runtime-hold"
            assert scope.symbol == symbol
            assert capability == ProviderCapability.INSTRUMENT_METADATA
            assert operation == "get_instrument_profile"
            raise lookup_error

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr(
            "app.routers.instruments.list_provider_status", lambda _db: asyncio.sleep(0, result=[])
        )
        monkeypatch.setattr("app.routers.instruments.execute_provider_call", _held_exact)

        response = await acquire_instrument(
            InstrumentAcquireRequest(symbol=symbol, request_id="exact-profile-runtime-hold"),
            async_db,
        )

        assert response.status == "held"
        assert response.reason_code == expected_reason
        held = next(
            item for item in response.source_outcomes if item.operation == "get_instrument_profile"
        )
        assert held.status == "held"
        assert held.error_type == type(lookup_error).__name__

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("lookup_error", "expected_status", "expected_reason"),
        [
            (
                ProviderRequestScopeDeniedError("exact_profile_scope_expired"),
                "held",
                "exact_profile_scope_expired",
            ),
            (
                ProviderRateLimitError(
                    "massive",
                    "capacity denied",
                    retry_at=datetime(2026, 11, 6, 12, 30, tzinfo=UTC),
                ),
                "held",
                "provider_capacity_unavailable",
            ),
            (
                ProviderQuotaAdmissionError(
                    "quota admission denied",
                    retry_at=datetime(2026, 11, 6, 12, 30, tzinfo=UTC),
                ),
                "held",
                "provider_quota_admission_denied",
            ),
            (
                ProviderQuotaCoordinatorError("quota coordinator unavailable"),
                "held",
                "provider_quota_coordinator_unavailable",
            ),
            (
                ProviderQuotaUnknownError("quota contract unknown"),
                "held",
                "provider_quota_contract_unknown",
            ),
            (ProviderNoDataError("profile absent"), "no_match", "exact_profile_not_found"),
            (
                RuntimeError("sensitive adapter detail must not be exposed"),
                "failed",
                "provider_profile_unavailable_or_mismatched",
            ),
        ],
    )
    async def test_selected_candidate_profile_errors_keep_typed_outcomes_without_identity_write(
        self,
        db,
        monkeypatch,
        caplog,
        lookup_error,
        expected_status,
        expected_reason,
    ):
        async_db = AsyncSessionAdapter(db)
        symbol = "QXHOLD"

        async def _search(_db, query, *, source_outcomes=None):
            assert query == symbol
            source_outcomes.append(
                {
                    "provider": "massive",
                    "capability": ProviderCapability.INSTRUMENT_SEARCH.value,
                    "operation": "search_instruments",
                    "status": "returned",
                    "result_count": 1,
                }
            )
            return [
                {
                    "symbol": symbol,
                    "name": "Synthetic selected candidate",
                    "exchange": "XNAS",
                    "type": "ETF",
                    "provider": "massive",
                }
            ]

        async def _profile(_db, provider_symbol, **kwargs):
            assert provider_symbol == symbol
            assert kwargs["provider_name"] == "massive"
            assert kwargs["persist"] is False
            assert kwargs["raise_provider_errors"] is True
            raise lookup_error

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr(
            "app.routers.instruments.ingest_provider_profile",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("a held or failed metadata lookup must not be ingested")
            ),
        )

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol=symbol,
                provider_candidate=ProviderCandidateBinding(
                    provider="massive", symbol=symbol, exchange="XNAS"
                ),
                request_id="selected-profile-error",
            ),
            async_db,
        )

        assert response.status == expected_status
        assert response.reason_code == expected_reason
        outcome = next(
            item for item in response.source_outcomes if item.operation == "get_instrument_profile"
        )
        assert outcome.status == expected_status
        assert outcome.error_type == type(lookup_error).__name__
        if isinstance(lookup_error, ProviderRateLimitError | ProviderQuotaAdmissionError):
            assert outcome.retry_at == lookup_error.retry_at
        assert db.query(Instrument).filter_by(symbol=symbol).one_or_none() is None
        if expected_status == "failed":
            record = next(
                record
                for record in caplog.records
                if record.getMessage() == "Selected provider profile lookup failed"
            )
            assert record.request_id == "selected-profile-error"
            assert record.error_type == "RuntimeError"
            assert "sensitive adapter detail" not in caplog.text

    @pytest.mark.asyncio
    async def test_selected_candidate_empty_profile_result_is_no_match_without_identity_write(
        self, db, monkeypatch
    ):
        async_db = AsyncSessionAdapter(db)
        symbol = "QXEMPTY"

        async def _search(_db, _query, *, source_outcomes=None):
            source_outcomes.append(
                {
                    "provider": "massive",
                    "capability": ProviderCapability.INSTRUMENT_SEARCH.value,
                    "operation": "search_instruments",
                    "status": "returned",
                    "result_count": 1,
                }
            )
            return [{"symbol": symbol, "exchange": "XNAS", "type": "ETF", "provider": "massive"}]

        async def _no_profile(*_args, **_kwargs):
            return None

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _no_profile)

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol=symbol,
                provider_candidate=ProviderCandidateBinding(
                    provider="massive", symbol=symbol, exchange="XNAS"
                ),
                request_id="selected-profile-empty",
            ),
            async_db,
        )

        assert response.status == "no_match"
        assert response.reason_code == "exact_profile_not_found"
        assert response.source_outcomes[-1].status == "no_match"
        assert db.query(Instrument).filter_by(symbol=symbol).one_or_none() is None

    @pytest.mark.asyncio
    async def test_search_hold_does_not_fall_through_to_exact_profile(self, db, monkeypatch):
        async_db = AsyncSessionAdapter(db)
        symbol = "QXHELD"

        async def _search(_db, query, *, source_outcomes=None):
            source_outcomes.append(
                {
                    "provider": "massive",
                    "capability": ProviderCapability.INSTRUMENT_SEARCH.value,
                    "operation": "search_instruments",
                    "status": "held",
                    "reason_code": "reviewed_source_hold",
                }
            )
            return [{"symbol": f"A{i}", "provider": "massive"} for i in range(10)]

        async def _forbidden_exact(*_args, **_kwargs):
            raise AssertionError("a held search must not be bypassed by profile lookup")

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.execute_provider_call", _forbidden_exact)

        response = await acquire_instrument(
            InstrumentAcquireRequest(symbol=symbol, request_id="exact-profile-held"),
            async_db,
        )

        assert response.status == "held"
        assert response.reason_code == "candidate_not_found_or_not_admitted"

    @pytest.mark.asyncio
    async def test_metadata_hold_prevents_exact_profile_lookup(self, db, monkeypatch):
        async_db = AsyncSessionAdapter(db)
        symbol = "QXMETAHOLD"
        metadata_status = [
            {
                "provider": "massive",
                "capability": ProviderCapability.INSTRUMENT_METADATA.value,
                "routing_eligible": False,
                "checkpoint_hold_reason": "reviewed_metadata_hold",
                "entitlement_admission": {},
            }
        ]

        async def _search(_db, _query, *, source_outcomes=None):
            source_outcomes.append(
                {
                    "provider": "massive",
                    "capability": ProviderCapability.INSTRUMENT_SEARCH.value,
                    "operation": "search_instruments",
                    "status": "returned",
                    "result_count": 10,
                }
            )
            return [{"symbol": f"A{i}", "provider": "massive"} for i in range(10)]

        async def _status(_db):
            return metadata_status

        async def _forbidden_exact(*_args, **_kwargs):
            raise AssertionError("a metadata hold must prevent exact profile transport")

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.list_provider_status", _status)
        monkeypatch.setattr("app.routers.instruments.execute_provider_call", _forbidden_exact)

        response = await acquire_instrument(
            InstrumentAcquireRequest(symbol=symbol, request_id="exact-profile-metadata-held"),
            async_db,
        )

        assert response.status == "held"
        assert response.reason_code == "exact_profile_not_admitted"
        assert any(
            item.capability == ProviderCapability.INSTRUMENT_METADATA.value
            and item.status == "held"
            for item in response.source_outcomes
        )

    @pytest.mark.asyncio
    async def test_profile_identifier_owned_by_another_instrument_stays_quarantined(
        self, db, instrument_type, monkeypatch
    ):
        async_db = AsyncSessionAdapter(db)
        scaffold = Instrument(
            symbol="OIH",
            name="OIH industry proxy ETF",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            identity_status="provisional",
        )
        owner = Instrument(
            symbol="OTHER",
            name="Existing owner",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            identity_status="resolved",
            domain_key="composite-figi:BBG000D02J82",
            primary_identifier_type="composite_figi",
            primary_identifier_value="BBG000D02J82",
        )
        arca = Exchange(mic="ARCX", name="NYSE Arca")
        db.add_all([scaffold, owner, arca])
        db.flush()
        db.add(
            InstrumentListing(
                instrument_id=scaffold.id,
                exchange_id=arca.id,
                ticker="OIH",
                currency="USD",
                is_primary=True,
                is_active=True,
                source="massive",
            )
        )
        db.add(
            InstrumentIdentifier(
                instrument_id=owner.id,
                identifier_type=InstrumentIdentifierType.COMPOSITE_FIGI,
                identifier_value="BBG000D02J82",
                is_primary=True,
                is_active=True,
            )
        )
        db.flush()

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "OIH",
                    "name": "VanEck Oil Services ETF",
                    "exchange": "ARCX",
                    "type": "ETF",
                    "provider": "massive",
                }
            ]

        async def _profile(*_args, **_kwargs):
            return InstrumentProfile(
                provider="massive",
                symbol="OIH",
                canonical_symbol="OIH",
                name="VanEck Oil Services ETF",
                currency="USD",
                quote_type="ETF",
                exchange="ARCX",
                identifiers=[
                    IdentifierRecord(
                        identifier_type="composite_figi",
                        identifier_value="BBG000D02J82",
                        is_primary=True,
                    )
                ],
                listings=[
                    ListingRecord(
                        provider_symbol="OIH",
                        exchange_code="ARCX",
                        currency="USD",
                        provider_instrument_type="ETF",
                        is_primary=True,
                    )
                ],
            )

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr(
            "app.services.instrument_mastering.ensure_external_identifier",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("explicit acquisition must not run fallback identifier lookup")
            ),
        )

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol="OIH",
                provider_candidate=ProviderCandidateBinding(
                    provider="massive", symbol="OIH", exchange="ARCX"
                ),
                request_id="test-oih-colliding-profile",
            ),
            async_db,
        )

        db.refresh(scaffold)
        assert response.status == "identity_conflict"
        assert response.reason_code == "canonical_identity_not_fully_qualified"
        assert scaffold.identity_status == "quarantined"
        assert scaffold.domain_key is None
        assert owner.domain_key == "composite-figi:BBG000D02J82"
        assert (
            db.query(InstrumentIdentityQuarantine)
            .filter(
                InstrumentIdentityQuarantine.instrument_id == scaffold.id,
                InstrumentIdentityQuarantine.proposed_domain_key == "composite-figi:BBG000D02J82",
                InstrumentIdentityQuarantine.status == "pending",
            )
            .one_or_none()
            is not None
        )

    @pytest.mark.asyncio
    async def test_existing_conflicting_domain_key_is_preserved_before_ingestion(
        self, db, instrument_type, monkeypatch
    ):
        async_db = AsyncSessionAdapter(db)
        scaffold = Instrument(
            symbol="OIH",
            name="OIH industry proxy ETF",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            identity_status="provisional",
            domain_key="composite-figi:BBG000OLDKEY01",
        )
        arca = Exchange(mic="ARCX", name="NYSE Arca")
        db.add_all([scaffold, arca])
        db.flush()
        db.add(
            InstrumentListing(
                instrument_id=scaffold.id,
                exchange_id=arca.id,
                ticker="OIH",
                currency="USD",
                is_primary=True,
                is_active=True,
                source="massive",
            )
        )
        db.flush()

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "OIH",
                    "name": "VanEck Oil Services ETF",
                    "exchange": "ARCX",
                    "type": "ETF",
                    "provider": "massive",
                }
            ]

        async def _profile(*_args, **_kwargs):
            return InstrumentProfile(
                provider="massive",
                symbol="OIH",
                canonical_symbol="OIH",
                name="VanEck Oil Services ETF",
                currency="USD",
                quote_type="ETF",
                exchange="ARCX",
                identifiers=[
                    IdentifierRecord(
                        identifier_type="composite_figi",
                        identifier_value="BBG000D02J82",
                        is_primary=True,
                    )
                ],
                listings=[
                    ListingRecord(
                        provider_symbol="OIH",
                        exchange_code="ARCX",
                        provider_instrument_type="ETF",
                        is_primary=True,
                    )
                ],
            )

        async def _forbid_ingestion(*_args, **_kwargs):
            raise AssertionError("a conflicting canonical key must stop before profile ingestion")

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr("app.routers.instruments.ingest_provider_profile", _forbid_ingestion)

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol="OIH",
                provider_candidate=ProviderCandidateBinding(
                    provider="massive", symbol="OIH", exchange="ARCX"
                ),
                request_id="test-oih-existing-domain-conflict",
            ),
            async_db,
        )

        db.refresh(scaffold)
        assert response.status == "identity_conflict"
        assert response.reason_code == "existing_placeholder_identity_conflict"
        assert scaffold.domain_key == "composite-figi:BBG000OLDKEY01"
        assert scaffold.identity_status == "provisional"

    @pytest.mark.asyncio
    async def test_missing_profile_listing_authority_does_not_promote_provisional_identity(
        self, db, instrument_type, monkeypatch
    ):
        async_db = AsyncSessionAdapter(db)
        scaffold = Instrument(
            symbol="OIH",
            name="OIH industry proxy ETF",
            currency="USD",
            instrument_type_id=instrument_type.id,
            is_active=True,
            identity_status="provisional",
        )
        db.add(scaffold)
        db.flush()

        async def _search(*_args, **_kwargs):
            return [
                {
                    "symbol": "OIH",
                    "name": "VanEck Oil Services ETF",
                    "exchange": "ARCX",
                    "type": "ETF",
                    "provider": "massive",
                }
            ]

        async def _profile(*_args, **_kwargs):
            return InstrumentProfile(
                provider="massive",
                symbol="OIH",
                canonical_symbol="OIH",
                name="VanEck Oil Services ETF",
                currency="USD",
                quote_type="ETF",
                exchange="ARCX",
                identifiers=[
                    IdentifierRecord(
                        identifier_type="composite_figi",
                        identifier_value="BBG000D02J82",
                        is_primary=True,
                    )
                ],
                listings=[],
            )

        async def _forbid_ingestion(*_args, **_kwargs):
            raise AssertionError("a profile without listing authority must not be ingested")

        monkeypatch.setattr("app.routers.instruments.search_provider_instruments_async", _search)
        monkeypatch.setattr("app.routers.instruments.get_provider_profile_async", _profile)
        monkeypatch.setattr("app.routers.instruments.ingest_provider_profile", _forbid_ingestion)

        response = await acquire_instrument(
            InstrumentAcquireRequest(
                symbol="OIH",
                provider_candidate=ProviderCandidateBinding(
                    provider="massive", symbol="OIH", exchange="ARCX"
                ),
                request_id="test-oih-missing-listing-authority",
            ),
            async_db,
        )

        db.refresh(scaffold)
        assert response.status == "identity_conflict"
        assert response.reason_code == "stable_identity_or_listing_authority_missing"
        assert scaffold.identity_status == "provisional"
        assert scaffold.domain_key is None


def test_search_exchange_prefers_active_primary_listing_mic(instrument_type):
    instrument = Instrument(
        symbol="SPY",
        name="SPDR S&P 500 ETF Trust",
        instrument_type_id=instrument_type.id,
    )
    instrument.listings = [
        InstrumentListing(
            ticker="SPY",
            is_active=True,
            is_primary=True,
            exchange=Exchange(mic="ARCX", name="NYSE Arca"),
        ),
        InstrumentListing(
            ticker="SPY",
            is_active=False,
            is_primary=False,
            exchange=Exchange(mic="XNAS", name="Nasdaq"),
        ),
    ]

    assert _instrument_search_exchange(instrument) == "ARCX"


class TestInstrument52WStats:
    @pytest.mark.asyncio
    async def test_concurrent_refreshes_keep_one_stats_row(self, db, instrument):
        async_db = AsyncSessionAdapter(db)
        base = datetime.now(UTC) - timedelta(days=90)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=base,
                    open=Decimal("150"),
                    high=Decimal("200"),
                    low=Decimal("145"),
                    close=Decimal("190"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=base + timedelta(days=30),
                    open=Decimal("140"),
                    high=Decimal("142"),
                    low=Decimal("120"),
                    close=Decimal("130"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
            ]
        )
        db.flush()

        await asyncio.gather(
            _ensure_52w_stats(instrument, async_db),
            _ensure_52w_stats(instrument, async_db),
        )

        rows = (
            db.query(InstrumentStats).filter(InstrumentStats.instrument_id == instrument.id).all()
        )
        assert len(rows) == 1
        assert float(rows[0].week52_high) == 200.0
        assert float(rows[0].week52_low) == 120.0

    @pytest.mark.asyncio
    async def test_refreshes_provider_sourced_52w_provenance_from_ohlcv(self, db, instrument):
        async_db = AsyncSessionAdapter(db)
        stats = InstrumentStats(
            instrument_id=instrument.id,
            week52_high=Decimal("222.00"),
            week52_low=Decimal("111.00"),
            field_provenance={
                "week52_high": {"source": "yfinance", "observed_at": datetime.now(UTC).isoformat()},
                "week52_low": {"source": "yfinance", "observed_at": datetime.now(UTC).isoformat()},
            },
        )
        db.add(stats)
        instrument.stats = stats

        base = datetime.now(UTC) - timedelta(days=90)
        db.add_all(
            [
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=base,
                    open=Decimal("150"),
                    high=Decimal("200"),
                    low=Decimal("145"),
                    close=Decimal("190"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
                OHLCVBar(
                    instrument_id=instrument.id,
                    timeframe=Timeframe.D1,
                    ts=base + timedelta(days=30),
                    open=Decimal("140"),
                    high=Decimal("142"),
                    low=Decimal("120"),
                    close=Decimal("130"),
                    volume=Decimal("1000"),
                    is_adjusted=True,
                ),
            ]
        )
        db.flush()

        assert _needs_52w_stats_refresh(instrument) is True

        refreshed = await _ensure_52w_stats(instrument, async_db)

        assert float(refreshed.stats.week52_high) == 200.0
        assert float(refreshed.stats.week52_low) == 120.0
        assert refreshed.stats.field_provenance["week52_high"]["source"] == "internal_ohlcv_52w"
        fetched_at = refreshed.stats.field_provenance["week52_high"]["fetched_at"]
        fetched_at_datetime = datetime.fromisoformat(fetched_at)
        assert fetched_at_datetime.tzinfo is not None
        assert fetched_at_datetime.utcoffset() == timedelta(0)
        assert (
            refreshed.stats.field_provenance["week52_high"]["observed_at"]
            == base.date().isoformat()
        )
        assert (
            refreshed.stats.field_provenance["week52_low"]["observed_at"]
            == (base + timedelta(days=30)).date().isoformat()
        )

    def test_skips_52w_refresh_when_internal_provenance_already_has_occurrence_dates(
        self, instrument
    ):
        instrument.stats = InstrumentStats(
            instrument_id=instrument.id,
            week52_high=Decimal("222.00"),
            week52_low=Decimal("111.00"),
            field_provenance={
                "week52_high": {
                    "source": "internal_ohlcv_52w",
                    "observed_at": "2025-02-01T00:00:00+00:00",
                },
                "week52_low": {
                    "source": "internal_ohlcv_52w",
                    "observed_at": "2025-01-10T00:00:00+00:00",
                },
            },
        )

        assert _needs_52w_stats_refresh(instrument) is False
