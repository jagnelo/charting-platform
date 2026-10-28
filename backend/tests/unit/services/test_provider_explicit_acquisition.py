from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.config import Settings, settings
from app.models.market_data_foundation import AdjustmentBasis, MarketSeries, MarketSeriesDefault
from app.models.ohlcv import OHLCVBar, Timeframe
from app.models.provider_runtime import ProviderCapability
from app.routers import instruments as instruments_router
from app.routers.instruments import _history_application_limit_reason
from app.schemas.instrument_acquisition import (
    HistoryAcquisitionRequest,
    InstrumentAcquireRequest,
)
from app.services import provider_runtime
from app.services.provider_runtime import (
    ProviderRequestScopeDeniedError,
    bind_explicit_etf_holdings_acquisition,
    bind_explicit_provider_acquisition,
    execute_provider_call,
    resolve_provider_chain,
)


def test_request_schemas_reject_unbounded_or_mismatched_identity_inputs():
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="end must be after start"):
        HistoryAcquisitionRequest(
            timeframe=Timeframe.D1,
            start=now,
            end=now,
            request_id="00000000-0000-0000-0000-000000000001",
        )
    with pytest.raises(ValidationError, match="timezone"):
        HistoryAcquisitionRequest(
            timeframe=Timeframe.D1,
            start=now.replace(tzinfo=None),
            end=now + timedelta(days=1),
            request_id="00000000-0000-0000-0000-000000000001",
        )
    with pytest.raises(ValidationError, match="must match"):
        InstrumentAcquireRequest(
            symbol="OIH",
            provider_candidate={"provider": "edgar", "symbol": "XLE"},
            request_id="00000000-0000-0000-0000-000000000001",
        )
    assert (
        HistoryAcquisitionRequest(
            timeframe=Timeframe.D1,
            start=now,
            end=now + timedelta(days=1),
            source_provider=" Massive ",
            request_id="history-source-bound",
        ).source_provider
        == "massive"
    )
    for invalid_provider in ("", "*", "all", "any"):
        with pytest.raises(ValidationError, match="source_provider"):
            HistoryAcquisitionRequest(
                timeframe=Timeframe.D1,
                start=now,
                end=now + timedelta(days=1),
                source_provider=invalid_provider,
                request_id="history-source-bound",
            )


@pytest.mark.asyncio
async def test_request_driven_only_denies_unscoped_call_before_database_or_transport(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(
        provider_runtime,
        "resolve_provider_chain",
        lambda *_args, **_kwargs: pytest.fail("resolver must not run"),
    )
    invoked = False

    def invoke(_provider, _symbol):
        nonlocal invoked
        invoked = True

    with pytest.raises(ProviderRequestScopeDeniedError) as error:
        await execute_provider_call(
            None,
            ProviderCapability.PRICE_HISTORY,
            "fetch_ohlcv:D1",
            instrument_id=12,
            provider_symbol="OIH",
            invoke=invoke,
        )
    assert error.value.reason_code == "explicit_acquisition_required"
    assert invoked is False


@pytest.mark.asyncio
async def test_symbol_scope_rejects_missing_target_before_resolver(monkeypatch):
    monkeypatch.setattr(
        provider_runtime,
        "resolve_provider_chain",
        lambda *_args, **_kwargs: pytest.fail("missing symbol must fail before resolver"),
    )

    with bind_explicit_provider_acquisition(
        request_id="00000000-0000-0000-0000-000000000002",
        operations=frozenset({(ProviderCapability.INSTRUMENT_METADATA, "get_instrument_profile")}),
        symbol="OIH",
        provider_names=frozenset({"massive"}),
    ):
        with pytest.raises(ProviderRequestScopeDeniedError) as error:
            await execute_provider_call(
                None,
                ProviderCapability.INSTRUMENT_METADATA,
                "get_instrument_profile",
                invoke=lambda _provider, _symbol: pytest.fail("must not transport"),
            )
    assert error.value.reason_code == "explicit_acquisition_scope_mismatch"


@pytest.mark.asyncio
async def test_scope_context_isolated_between_concurrent_requests_and_resets(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)

    async def scoped(symbol: str, request_id: str) -> str | None:
        with bind_explicit_provider_acquisition(
            request_id=request_id,
            operations=frozenset({(ProviderCapability.INSTRUMENT_SEARCH, "search_instruments")}),
            symbol=symbol,
        ):
            await asyncio.sleep(0)
            return provider_runtime._explicit_acquisition_scope_denial(
                capability=ProviderCapability.INSTRUMENT_SEARCH,
                operation="search_instruments",
                instrument_id=None,
                provider_symbol=symbol,
            )

    results = await asyncio.gather(
        scoped("OIH", "00000000-0000-0000-0000-000000000003"),
        scoped("SPY", "00000000-0000-0000-0000-000000000004"),
    )
    assert results == [None, None]
    assert (
        provider_runtime._explicit_acquisition_scope_denial(
            capability=ProviderCapability.INSTRUMENT_SEARCH,
            operation="search_instruments",
            instrument_id=None,
            provider_symbol="OIH",
        )
        == "explicit_acquisition_required"
    )


@pytest.mark.asyncio
async def test_etf_helper_binds_exact_issuer_and_never_edgar_fallback():
    with bind_explicit_etf_holdings_acquisition(
        request_id="00000000-0000-0000-0000-000000000005",
        instrument_id=77,
        symbol="OIH",
        issuer_provider_name="VanEck",
    ) as scope:
        assert scope.provider_names == frozenset({"vaneck"})
        assert scope.operations == frozenset(
            {(ProviderCapability.ETF_HOLDINGS, "fetch_etf_holdings_latest")}
        )
        assert (
            provider_runtime._explicit_acquisition_scope_denial(
                capability=ProviderCapability.ETF_HOLDINGS,
                operation="fetch_etf_holdings_latest",
                instrument_id=77,
                provider_symbol="OIH",
            )
            is None
        )
        assert (
            provider_runtime._explicit_acquisition_scope_denial(
                capability=ProviderCapability.MARKET_EVENTS,
                operation="fetch_market_events",
                instrument_id=77,
                provider_symbol="OIH",
            )
            == "explicit_acquisition_scope_mismatch"
        )
        assert (
            provider_runtime._explicit_acquisition_scope_denial(
                capability=ProviderCapability.ETF_HOLDINGS,
                operation="fetch_etf_holdings_latest",
                instrument_id=77,
                provider_symbol="OIH",
            )
            is None
        )
    for forbidden in ("edgar", "sec"):
        with pytest.raises(ValueError, match="issuer provider"):
            with bind_explicit_etf_holdings_acquisition(
                request_id="00000000-0000-0000-0000-000000000007",
                instrument_id=77,
                symbol="OIH",
                issuer_provider_name=forbidden,
            ):
                pytest.fail("SEC must not enter the issuer-only acquisition scope")


@pytest.mark.asyncio
async def test_vaneck_initial_qualification_is_exact_and_one_shot(monkeypatch):
    from app.services.provider_runtime import (
        ProviderNoDataError,
        bind_vaneck_initial_etf_qualification,
    )

    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", True)
    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"vaneck:issuer_account": "reviewed-vaneck-issuer-account"},
    )
    resolver_calls = []

    async def no_candidate(_db, _capability, **kwargs):
        resolver_calls.append(kwargs)
        return []

    monkeypatch.setattr(provider_runtime, "resolve_provider_chain", no_candidate)
    with bind_vaneck_initial_etf_qualification(
        job_id=51,
        fund_profile_id=17,
        instrument_id=23,
        provider_symbol=" OIH ",
        account_scope="reviewed-vaneck-issuer-account",
        review_revision=4,
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    ) as authority:
        scope = provider_runtime._EXPLICIT_ACQUISITION_CONTEXT.get()
        assert scope.provider_names == frozenset({"vaneck"})
        assert scope.operations == frozenset(
            {(ProviderCapability.ETF_HOLDINGS, "fetch_etf_holdings_latest")}
        )
        invoke_calls = []
        args = {
            "db": object(),
            "capability": ProviderCapability.ETF_HOLDINGS,
            "operation": "fetch_etf_holdings_latest",
            "instrument_id": 23,
            "profile_id": 17,
            "provider_symbol": "OIH",
            "provider_name": "vaneck",
            "invoke": lambda *_args: invoke_calls.append(True),
        }
        with pytest.raises(ProviderNoDataError, match="No currently-supported providers"):
            await execute_provider_call(**args)
        assert authority.started is True
        assert resolver_calls[0]["profile_id"] == 17
        assert invoke_calls == []
        with pytest.raises(ProviderRequestScopeDeniedError, match="replay_denied"):
            await execute_provider_call(**args)
        assert len(resolver_calls) == 1
        assert invoke_calls == []


def test_vaneck_initial_qualification_matches_only_not_run_exact_revision_and_account(
    monkeypatch,
):
    from app.services.provider_runtime import bind_vaneck_initial_etf_qualification

    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"vaneck:issuer_account": "reviewed-vaneck-issuer-account"},
    )
    with bind_vaneck_initial_etf_qualification(
        job_id=52,
        fund_profile_id=17,
        instrument_id=23,
        provider_symbol="OIH",
        account_scope="reviewed-vaneck-issuer-account",
        review_revision=4,
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    ):
        values = {
            "provider_name": "vaneck",
            "capability": ProviderCapability.ETF_HOLDINGS,
            "operation": "fetch_etf_holdings_latest",
            "instrument_id": 23,
            "provider_symbol": "OIH",
            "profile_id": 17,
            "policy": SimpleNamespace(quota_scope="issuer_account"),
            "entitlement": SimpleNamespace(live_probe_status="not_run", revision=4),
        }

        def matches(**overrides):
            return provider_runtime._vaneck_initial_qualification_matches(**{**values, **overrides})

        assert matches() is True
        assert matches(profile_id=18) is False
        assert matches(instrument_id=24) is False
        assert matches(provider_symbol=None) is False
        assert matches(operation="fetch_etf_holdings_sec_filing") is False
        assert matches(provider_name="edgar") is False
        assert matches(policy=SimpleNamespace(quota_scope="api_key")) is False
        assert matches(entitlement=SimpleNamespace(live_probe_status="passed", revision=4)) is False
        assert (
            matches(entitlement=SimpleNamespace(live_probe_status="not_run", revision=5)) is False
        )


def test_vaneck_initial_qualification_rejects_invalid_scope_inputs():
    from app.services.provider_runtime import bind_vaneck_initial_etf_qualification

    valid = {
        "job_id": 53,
        "fund_profile_id": 17,
        "instrument_id": 23,
        "provider_symbol": "OIH",
        "account_scope": "reviewed-vaneck-issuer-account",
        "review_revision": 4,
        "expires_at": datetime.now(UTC) + timedelta(minutes=1),
    }
    invalid = (
        ("job_id", 0),
        ("fund_profile_id", 0),
        ("instrument_id", 0),
        ("provider_symbol", "*"),
        ("account_scope", "*"),
        ("review_revision", 0),
        ("expires_at", datetime.now(UTC) - timedelta(seconds=1)),
    )
    for field, value in invalid:
        with pytest.raises(ValueError, match="invalid VanEck initial qualification scope"):
            with bind_vaneck_initial_etf_qualification(**{**valid, field: value}):
                pytest.fail("invalid authority must not be bound")


@pytest.mark.asyncio
async def test_vaneck_qualification_can_resolve_disabled_policy_only_in_exact_context(monkeypatch):
    from app.services.provider_runtime import bind_vaneck_initial_etf_qualification

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", False)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", True)
    monkeypatch.setattr(settings, "APP_ENV", "test")
    monkeypatch.setattr(
        settings,
        "PROVIDER_QUOTA_ACCOUNT_SCOPES",
        {"vaneck:issuer_account": "reviewed-vaneck-issuer-account"},
    )
    data_source = SimpleNamespace(id=19, name="vaneck", is_active=True)
    policy = SimpleNamespace(
        is_enabled=False,
        is_pinned=False,
        auto_weight_enabled=False,
        base_priority=80,
        score_floor=Decimal("0"),
        score_ceiling=Decimal("100"),
        learned_weight=Decimal("0"),
        effective_score=Decimal("0"),
        quota_scope="issuer_account",
        quota_contract={"dimensions": [{"name": "request"}]},
    )
    health = SimpleNamespace(
        circuit_open_until=None,
        ewma_success_rate=Decimal("0"),
        ewma_completeness=Decimal("0"),
        ewma_freshness=Decimal("0"),
        ewma_consistency=Decimal("0"),
        ewma_latency_ms=Decimal("0"),
        observed_score=Decimal("0"),
    )
    entitlement = SimpleNamespace(
        live_probe_status="not_run",
        revision=4,
        configured_plan="reviewed-free-issuer",
        is_free=True,
        enabled_environments=["test"],
        review_due_at=None,
        authentication_required=False,
    )

    class Result:
        def all(self):
            return [(policy, health, data_source, entitlement)]

        def one_or_none(self):
            return ("etf", "exchange_traded_fund")

    class FakeDB:
        def __init__(self):
            self.statements = []

        async def execute(self, statement):
            self.statements.append(str(statement))
            return Result()

    async def no_seed(_db):
        return None

    async def empty_support(_db, _instrument_id, _capability):
        return {}

    async def bindings(_db, _instrument_id):
        return {data_source.id}

    monkeypatch.setattr(provider_runtime, "seed_provider_runtime", no_seed)
    monkeypatch.setattr(provider_runtime, "get_provider_support_map", empty_support)
    monkeypatch.setattr(provider_runtime, "get_provider_binding_ids", bindings)
    admission_kwargs = []

    def allow_reviewed_free(_entitlement, **kwargs):
        admission_kwargs.append(kwargs)
        return {"allowed": True}

    monkeypatch.setattr(provider_runtime, "provider_entitlement_admission", allow_reviewed_free)
    monkeypatch.setattr(
        provider_runtime, "provider_checkpoint_operation_hold_reason", lambda *_a, **_k: None
    )
    monkeypatch.setattr(provider_runtime, "provider_missing_routing_controls", lambda *_a, **_k: [])
    monkeypatch.setattr(
        provider_runtime, "provider_configuration_required", lambda *_a, **_k: False
    )
    monkeypatch.setattr(provider_runtime, "policy_has_known_quota", lambda _policy: True)
    monkeypatch.setattr(
        provider_runtime, "provider_contract_operation_cost_known", lambda *_a, **_k: True
    )
    adapter = SimpleNamespace(
        source_provider="vaneck",
        fetch_latest=lambda *_a, **_k: None,
        fetch_for_date=lambda *_a, **_k: None,
    )
    db = FakeDB()
    with bind_vaneck_initial_etf_qualification(
        job_id=54,
        fund_profile_id=17,
        instrument_id=23,
        provider_symbol="OIH",
        account_scope="reviewed-vaneck-issuer-account",
        review_revision=4,
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    ) as authority:
        # execute_provider_call consumes this before awaiting the resolver.
        authority.started = True
        chain = await resolve_provider_chain(
            db,
            ProviderCapability.ETF_HOLDINGS,
            instrument_id=23,
            provider_symbol="OIH",
            profile_id=17,
            operation="fetch_etf_holdings_latest",
            etf_holdings_adapters={"vaneck": adapter},
        )

    assert [candidate.provider_name for candidate in chain] == ["vaneck"]
    assert policy.is_enabled is False
    assert admission_kwargs == [
        {
            "provider_name": "vaneck",
            "capability": ProviderCapability.ETF_HOLDINGS,
            "checkpoint_free_only": True,
            "allow_paid": False,
        }
    ]


@pytest.mark.asyncio
async def test_vaneck_qualification_does_not_bypass_global_routing_stop(monkeypatch):
    from app.services.provider_runtime import (
        ProviderNoDataError,
        bind_vaneck_initial_etf_qualification,
    )

    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", False)

    async def no_seed(_db):
        return None

    monkeypatch.setattr(provider_runtime, "seed_provider_runtime", no_seed)
    with bind_vaneck_initial_etf_qualification(
        job_id=55,
        fund_profile_id=17,
        instrument_id=23,
        provider_symbol="OIH",
        account_scope="reviewed-vaneck-issuer-account",
        review_revision=4,
        expires_at=datetime.now(UTC) + timedelta(minutes=1),
    ):
        with pytest.raises(ProviderNoDataError, match="No currently-supported providers"):
            await execute_provider_call(
                object(),
                ProviderCapability.ETF_HOLDINGS,
                "fetch_etf_holdings_latest",
                instrument_id=23,
                profile_id=17,
                provider_symbol="OIH",
                provider_name="vaneck",
                invoke=lambda *_args: pytest.fail("global routing stop must prevent transport"),
            )


def test_history_application_bounds_reject_oversized_range_and_slice_count(monkeypatch):
    monkeypatch.setattr(settings, "PROVIDER_ON_DEMAND_MAX_REQUESTED_BARS", 2000)
    monkeypatch.setattr(settings, "PROVIDER_ON_DEMAND_MAX_MISSING_SLICES", 1)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    assert (
        _history_application_limit_reason(
            timeframe=Timeframe.D1,
            start=start,
            end=start + timedelta(days=2000),
            cached_bars=[],
        )
        == "application_requested_range_limit_exceeded"
    )
    separated = [
        OHLCVBar(ts=start, timeframe=Timeframe.D1),
        OHLCVBar(ts=start + timedelta(days=1), timeframe=Timeframe.D1),
        OHLCVBar(ts=start + timedelta(days=7), timeframe=Timeframe.D1),
        OHLCVBar(ts=start + timedelta(days=8), timeframe=Timeframe.D1),
        OHLCVBar(ts=start + timedelta(days=14), timeframe=Timeframe.D1),
        OHLCVBar(ts=start + timedelta(days=15), timeframe=Timeframe.D1),
    ]
    assert (
        _history_application_limit_reason(
            timeframe=Timeframe.D1,
            start=start,
            end=start + timedelta(days=15),
            cached_bars=separated,
        )
        == "application_missing_slice_limit_exceeded"
    )


def test_history_application_settings_cannot_raise_hard_workload_ceilings():
    with pytest.raises(ValidationError):
        Settings(PROVIDER_ON_DEMAND_MAX_REQUESTED_BARS=2001)
    with pytest.raises(ValidationError):
        Settings(PROVIDER_ON_DEMAND_MAX_MISSING_SLICES=9)


@pytest.mark.asyncio
async def test_history_readback_excludes_overlapping_alternate_series(monkeypatch, db, instrument):
    selected = MarketSeries(
        instrument_id=instrument.id,
        feed_scope="selected",
        session_code="regular",
        timeframe="D1",
        adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
        is_canonical=True,
        is_active=True,
    )
    alternate = MarketSeries(
        instrument_id=instrument.id,
        feed_scope="alternate",
        session_code="regular",
        timeframe="D1",
        adjustment_basis=AdjustmentBasis.SPLIT_ADJUSTED,
        is_canonical=True,
        is_active=True,
    )
    db.add_all([selected, alternate])
    db.flush()
    db.add(
        MarketSeriesDefault(
            instrument_id=instrument.id,
            timeframe="D1",
            is_adjusted=True,
            market_series_id=selected.id,
            selection_reason="on-demand-acquisition-regression",
        )
    )
    start = datetime(2026, 1, 2, tzinfo=UTC)
    overlapping = [
        OHLCVBar(
            instrument_id=instrument.id,
            market_series_id=selected.id,
            timeframe=Timeframe.D1,
            ts=start,
            open=Decimal("10"),
            high=Decimal("11"),
            low=Decimal("9"),
            close=Decimal("10"),
            volume=Decimal("100"),
            is_adjusted=True,
        )
    ]
    overlapping.extend(
        OHLCVBar(
            instrument_id=instrument.id,
            market_series_id=alternate.id,
            timeframe=Timeframe.D1,
            ts=start + timedelta(days=offset),
            open=Decimal("11"),
            high=Decimal("12"),
            low=Decimal("10"),
            close=Decimal("11"),
            volume=Decimal("101"),
            is_adjusted=True,
        )
        for offset in (1, 2, 3)
    )
    db.add_all(overlapping)
    db.flush()

    class AsyncSessionAdapter:
        async def execute(self, statement):
            return db.execute(statement)

    async def stable_identity(_db, _instrument, *_args):
        return object()

    fetch_calls = 0
    observed_provider_scopes = []

    async def no_fetch(*_args, **_kwargs):
        nonlocal fetch_calls
        fetch_calls += 1
        scope = provider_runtime._EXPLICIT_ACQUISITION_CONTEXT.get()
        observed_provider_scopes.append(scope.provider_names)
        return []

    async def no_held_status(*_args, **_kwargs):
        return []

    monkeypatch.setattr(instruments_router, "_qualified_identity", stable_identity)
    monkeypatch.setattr(instruments_router, "fetch_ohlcv", no_fetch)
    monkeypatch.setattr(instruments_router, "_held_provider_outcomes", no_held_status)
    response = await instruments_router.acquire_instrument_history(
        instrument.id,
        HistoryAcquisitionRequest(
            timeframe=Timeframe.D1,
            adjusted=True,
            start=start,
            end=start + timedelta(days=3),
            source_provider="massive",
            request_id="00000000-0000-0000-0000-000000000008",
        ),
        db=AsyncSessionAdapter(),
        current_user=SimpleNamespace(id=1),
    )
    assert [bar.ts.replace(tzinfo=UTC) for bar in response.bars] == [start]
    assert response.coverage.bar_count == 1
    assert response.status == "partial"
    assert fetch_calls == 1
    assert observed_provider_scopes == [frozenset({"massive"})]

    oversized = await instruments_router.acquire_instrument_history(
        instrument.id,
        HistoryAcquisitionRequest(
            timeframe=Timeframe.D1,
            adjusted=True,
            start=start,
            end=start + timedelta(days=2500),
            request_id="00000000-0000-0000-0000-000000000009",
        ),
        db=AsyncSessionAdapter(),
        current_user=SimpleNamespace(id=1),
    )
    assert oversized.status == "held"
    assert oversized.reason_code == "application_requested_range_limit_exceeded"
    assert fetch_calls == 1


@pytest.mark.asyncio
async def test_active_scope_forces_free_only_even_when_global_paid_routing_is_on(
    monkeypatch,
):
    monkeypatch.setattr(settings, "PROVIDER_REQUEST_DRIVEN_ONLY", False)
    monkeypatch.setattr(settings, "PROVIDER_ROUTING_ENABLED", True)
    monkeypatch.setattr(settings, "PROVIDER_FREE_ONLY_CHECKPOINT", False)
    monkeypatch.setattr(settings, "ALLOW_PAID_PROVIDER_ROUTING", True)
    row = (
        SimpleNamespace(capability=ProviderCapability.PRICE_HISTORY, is_enabled=True),
        SimpleNamespace(),
        SimpleNamespace(name="reviewed-paid-provider"),
        SimpleNamespace(configured_plan="reviewed-paid"),
    )

    class Rows:
        def all(self):
            return [row]

    class FakeDB:
        async def execute(self, _statement):
            return Rows()

    async def no_seed(_db):
        return None

    seen = {}

    def deny_paid(_entitlement, **kwargs):
        seen.update(kwargs)
        return {"allowed": False, "reason_code": "checkpoint_free_only"}

    monkeypatch.setattr(provider_runtime, "seed_provider_runtime", no_seed)
    monkeypatch.setattr(provider_runtime, "provider_entitlement_admission", deny_paid)
    with bind_explicit_provider_acquisition(
        request_id="00000000-0000-0000-0000-000000000006",
        operations=frozenset({(ProviderCapability.PRICE_HISTORY, "fetch_ohlcv")}),
        symbol="OIH",
        provider_names=frozenset({"reviewed-paid-provider"}),
    ):
        chain = await resolve_provider_chain(
            FakeDB(),
            ProviderCapability.PRICE_HISTORY,
            operation="fetch_ohlcv",
            provider_symbol="OIH",
        )
    assert chain == []
    assert seen["checkpoint_free_only"] is True
    assert seen["allow_paid"] is False
