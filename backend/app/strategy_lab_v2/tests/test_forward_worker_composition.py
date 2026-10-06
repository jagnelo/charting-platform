from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.authenticated_event_tape import AuthenticatedFrozenEventTapeResolver
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.event_tape import bind_event_tape
from app.strategy_lab_v2.event_tape_artifacts import FrozenEventTapeArtifactResolution
from app.strategy_lab_v2.forward_context import ForwardStrategyContextPreparation
from app.strategy_lab_v2.forward_execution_plan import (
    ForwardComponentExecutionPlan,
    ForwardExecutionPlan,
)
from app.strategy_lab_v2.forward_execution_plan_resolution import ResolvedForwardExecutionPlan
from app.strategy_lab_v2.forward_processed_prefix import ForwardProcessedEventPrefix
from app.strategy_lab_v2.forward_warmup import CarryInMode, ForwardWarmupReceipt
from app.strategy_lab_v2.forward_worker_composition import (
    AuthenticatedForwardDeliveryContextResolver,
    AuthenticatedForwardSandboxPlanFactory,
    AuthenticatedForwardSandboxPlanInputResolver,
    AuthenticatedForwardWorkerRuntimeInputResolver,
    ForwardNautilusMarketContext,
    OwnerScopedForwardEventHandler,
    ResolvedForwardWorkerRuntimeInputs,
    _cut_forward_warmup_at_receipt,
    _verify_complete_forward_warmup_payloads,
    build_forward_tape_manifest,
    create_authenticated_forward_delivery_context_resolver,
    create_authenticated_forward_session_event_handler,
    create_authenticated_forward_worker_handler_factory,
    create_forward_worker_callbacks,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusForwardDeliveryBinding,
    materialize_nautilus_forward_tape,
)
from app.strategy_lab_v2.nautilus_forward_delivery import (
    VerifiedForwardMarketPayload,
    create_nautilus_forward_delivery_callback_factory,
)
from app.strategy_lab_v2.nautilus_forward_input import NautilusForwardDeliveryInput
from app.strategy_lab_v2.nautilus_forward_recovery import ResolvedNautilusForwardCheckpoint
from app.strategy_lab_v2.nautilus_forward_session import (
    NautilusForwardSessionEventHandler,
    PersistentNautilusForwardSessionRuntime,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.sdk import MarketEvent, StrategyContext
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import _inputs as _trial_inputs


class _Runtime:
    def __init__(self) -> None:
        self.closed = 0

    async def execute(self, *_args: Any) -> None:
        return None

    async def restore(self, **_kwargs: Any) -> None:
        return None

    async def close_all(self) -> None:
        self.closed += 1


class _RuntimeInputResolver:
    async def resolve(self, **_kwargs: Any) -> Any:
        raise AssertionError("runtime inputs are resolved only when starting native execution")


def _handler(principal: str, runtime: _Runtime) -> NautilusForwardSessionEventHandler:
    return NautilusForwardSessionEventHandler(
        lambda *_args: None,  # type: ignore[arg-type]
        lambda *_args: None,  # type: ignore[arg-type]
        runtime,  # type: ignore[arg-type]
        type("AccountStore", (), {"apply": lambda *_args, **_kwargs: None})(),
        principal=principal,
    )


@pytest.mark.asyncio
async def test_owner_handlers_are_cached_separately_and_closed_at_shutdown() -> None:
    calls: list[str] = []
    runtimes: dict[str, _Runtime] = {}

    async def factory(
        owner_id: str, _delivery_factory: Any, _inputs: Any
    ) -> NautilusForwardSessionEventHandler:
        calls.append(owner_id)
        await asyncio.sleep(0)
        runtime = _Runtime()
        runtimes[owner_id] = runtime
        return _handler(owner_id, runtime)

    routed = OwnerScopedForwardEventHandler(
        factory,
        _delivery_factory(),
        lambda _owner: _RuntimeInputResolver(),  # type: ignore[arg-type]
    )
    first = await routed._handler_for("owner-a")
    same_owner = await routed._handler_for("owner-a")
    other_owner = await routed._handler_for("owner-b")

    assert first is same_owner
    assert other_owner is not first
    assert calls == ["owner-a", "owner-b"]

    await routed.close()

    assert runtimes["owner-a"].closed == 1
    assert runtimes["owner-b"].closed == 1


@pytest.mark.asyncio
async def test_owner_handler_factory_cannot_return_a_cross_owner_runtime() -> None:
    runtime = _Runtime()
    routed = OwnerScopedForwardEventHandler(
        lambda _owner, _delivery, _inputs: _handler("owner-b", runtime),
        _delivery_factory(),
        lambda _owner: _RuntimeInputResolver(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="dispatch owner"):
        await routed._handler_for("owner-a")


@pytest.mark.asyncio
async def test_concurrent_first_dispatches_create_only_one_owner_handler() -> None:
    calls = 0

    async def factory(
        owner_id: str, _delivery_factory: Any, _inputs: Any
    ) -> NautilusForwardSessionEventHandler:
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return _handler(owner_id, _Runtime())

    routed = OwnerScopedForwardEventHandler(
        factory,
        _delivery_factory(),
        lambda _owner: _RuntimeInputResolver(),  # type: ignore[arg-type]
    )
    first, second = await asyncio.gather(
        routed._handler_for("owner-a"),
        routed._handler_for("owner-a"),
    )

    assert first is second
    assert calls == 1


@pytest.mark.asyncio
async def test_production_callback_assembly_uses_durable_dispatch_and_shutdown_hook(
    tmp_path: Any,
) -> None:
    persistence = PostgresStrategyLabV2Persistence.build(lambda: None)
    runtime = _Runtime()
    package_resolver = StrategyPackageArtifactResolver(
        LocalArtifactStore(tmp_path / "artifacts"),
        runtime_abi="strategy-runtime.test.v1",
    )

    callbacks = create_forward_worker_callbacks(
        persistence,
        queue_name="forward-events",
        payload_resolver=lambda **_kwargs: None,  # type: ignore[arg-type]
        event_type_by_dependency={"dependency": "ohlcv"},
        package_resolver=package_resolver,
        owner_handler_factory=lambda owner_id, _delivery, _inputs: _handler(owner_id, runtime),
    )

    assert callable(callbacks.materializer)
    assert callable(callbacks.handler)
    assert callbacks.close is not None
    close_result = callbacks.close()
    if close_result is not None:
        await close_result
    assert runtime.closed == 0


@pytest.mark.asyncio
async def test_runtime_input_resolution_fails_closed_before_plan_lookup_for_missing_owner() -> None:
    reads: list[dict[str, Any]] = []

    class Reader:
        async def get_domain_contract(self, **kwargs: Any) -> None:
            reads.append(kwargs)
            return None

        async def get_domain_contracts_by_fingerprint(self, **_kwargs: Any) -> dict[str, Any]:
            raise AssertionError("plan lookup must not start without an owned instance")

    class PlanResolver:
        async def resolve(self, _instance: Any) -> Any:
            raise AssertionError("plan lookup must not start without an owned instance")

    class CheckpointResolver:
        async def resolve(self, **_kwargs: Any) -> Any:
            raise AssertionError("checkpoint lookup must not start without an owned instance")

    resolver = AuthenticatedForwardWorkerRuntimeInputResolver(
        Reader(),  # type: ignore[arg-type]
        PlanResolver(),  # type: ignore[arg-type]
        CheckpointResolver(),  # type: ignore[arg-type]
        principal="owner-a",
    )

    with pytest.raises(ValueError, match="owner-scoped forward instance is unavailable"):
        await resolver.resolve(
            instance_id="forward-1",
            checkpoint_fingerprint="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        )

    assert reads == [
        {
            "principal": "owner-a",
            "resource_type": ApiResourceType.FORWARD_INSTANCE,
            "resource_id": "forward-1",
        }
    ]


def _delivery() -> NautilusForwardDeliveryInput:
    canonical = CanonicalForwardEvent(
        "event-1",
        1,
        datetime(2026, 10, 6, tzinfo=UTC),
        datetime(2026, 10, 6, 0, 0, 1, tzinfo=UTC),
        content_digest("canonical-source"),
    )
    market = MarketEvent(
        "dependency-1",
        canonical.event_id,
        "US.ABC",
        canonical.event_time,
        canonical.sequence,
        {"open": 10, "high": 10, "low": 10, "close": 10, "volume": 1},
    )
    binding = NautilusForwardDeliveryBinding(
        "forward-1",
        content_digest(canonical),
        "1-0",
        content_digest("redis-entry"),
        content_digest("dispatch"),
        content_digest("request"),
        content_digest("checkpoint"),
        content_digest("warmup"),
        "enqueue",
    )
    tape = materialize_nautilus_forward_tape(
        "forward-1",
        (canonical,),
        (market,),
        event_type_by_dependency={"dependency-1": "ohlcv"},
        delivery_bindings=(binding,),
    )
    return NautilusForwardDeliveryInput(binding, tape, market, canonical.source_digest)


def _runtime_inputs(
    *,
    checkpoint_fingerprint: str | None = None,
    warmup_fingerprint: str | None = None,
) -> ResolvedForwardWorkerRuntimeInputs:
    plan = object.__new__(ResolvedForwardExecutionPlan)
    object.__setattr__(plan, "instance", SimpleNamespace(instance_id="forward-1"))
    checkpoint = object.__new__(ResolvedNautilusForwardCheckpoint)
    object.__setattr__(
        checkpoint,
        "admission_state",
        SimpleNamespace(
            checkpoint=SimpleNamespace(
                fingerprint=checkpoint_fingerprint or content_digest("checkpoint")
            )
        ),
    )
    object.__setattr__(
        checkpoint,
        "warmup_receipt",
        SimpleNamespace(fingerprint=warmup_fingerprint or content_digest("warmup")),
    )
    inputs = object.__new__(ResolvedForwardWorkerRuntimeInputs)
    object.__setattr__(inputs, "execution_plan", plan)
    object.__setattr__(inputs, "checkpoint", checkpoint)
    return inputs


def _unreachable_history(**_kwargs: Any) -> Any:
    raise AssertionError("verified history is resolved only after context binding")


def test_forward_sandbox_input_resolver_requires_one_authenticated_owner() -> None:
    snapshot_tape_resolver = object.__new__(AuthenticatedFrozenEventTapeResolver)
    snapshot_tape_resolver._principal = "owner-a"

    class RuntimeInputs:
        principal = "owner-a"

        async def resolve(self, **_kwargs: Any) -> Any:
            return None

    class WarmupReader:
        def read_warmup_payloads(self, **_kwargs: Any) -> Any:
            return ()

    class MarketContext:
        def resolve(self, **_kwargs: Any) -> Any:
            return None

    runtime_inputs = RuntimeInputs()
    warmup_reader = WarmupReader()
    market_context = MarketContext()
    profile = RuntimeIsolationProfile(
        content_digest("forward-runtime-image"), "strategy-runtime.test.v1"
    )
    resolver = AuthenticatedForwardSandboxPlanInputResolver(
        runtime_inputs,
        snapshot_tape_resolver,
        warmup_reader,
        _unreachable_history,
        market_context,
        principal="owner-a",
        runtime_profile=profile,
        expected_version="2.0.0rc5",
    )

    assert resolver is not None
    with pytest.raises(ValueError, match="share the authenticated principal"):
        AuthenticatedForwardSandboxPlanInputResolver(
            runtime_inputs,
            snapshot_tape_resolver,
            warmup_reader,
            _unreachable_history,
            market_context,
            principal="owner-b",
            runtime_profile=profile,
            expected_version="2.0.0rc5",
        )


@pytest.mark.asyncio
async def test_authenticated_sandbox_input_resolver_composes_exact_plan_and_tape() -> None:
    values = _trial_inputs()
    snapshot = values["snapshot"]
    manifest = values["strategy_manifest"]
    source_tape = values["event_tape"]
    source_resolution = FrozenEventTapeArtifactResolution(
        snapshot.fingerprint,
        manifest.fingerprint,
        source_tape,
        bind_event_tape(source_tape, snapshot, manifest),
        tuple(sorted(item.content_digest for item in snapshot.series)),
    )
    strategy = values["strategy_manifest"].strategy
    package = values["strategy_package"]
    instance = SimpleNamespace(
        instance_id="forward-1",
        warmup_snapshot_fingerprint=snapshot.fingerprint,
    )
    portfolio = values["portfolio"]
    component_binding = ForwardComponentExecutionPlan(
        "component-1",
        strategy.fingerprint,
        package.fingerprint,
        {"window": 20},
        13,
    )
    resolved_component = SimpleNamespace(
        binding=component_binding,
        strategy=strategy,
        package=package,
        resolved_package=SimpleNamespace(
            manifest=manifest,
            source=values["strategy_source"],
        ),
    )
    plan = object.__new__(ResolvedForwardExecutionPlan)
    object.__setattr__(plan, "instance", instance)
    object.__setattr__(plan, "portfolio", portfolio)
    object.__setattr__(
        plan,
        "plan",
        ForwardExecutionPlan("forward-1", portfolio.fingerprint, (component_binding,)),
    )
    object.__setattr__(plan, "components", {"component-1": resolved_component})

    full_payloads = tuple(
        VerifiedForwardMarketPayload(
            CanonicalForwardEvent(
                event.event_id,
                100 + index * 100,
                event.event_time,
                event.event_time,
                content_digest(event.values),
            ),
            replace(event, sequence=100 + index * 100),
            content_digest(event.values),
        )
        for index, event in enumerate(source_tape.events)
    )
    cursor = full_payloads[0].canonical_event
    receipt = ForwardWarmupReceipt(
        "forward-1",
        snapshot.fingerprint,
        CarryInMode.FLAT,
        content_digest("forward-warmup-result"),
        cursor.event_time,
        cursor.event_id,
        cursor.sequence,
        content_digest(cursor),
    )
    checkpoint_fingerprint = content_digest("forward-checkpoint")
    before_time = cursor.event_time + timedelta(
        seconds=(full_payloads[1].canonical_event.event_time - cursor.event_time).total_seconds()
        / 2
    )
    before_event = CanonicalForwardEvent(
        "live-current",
        150,
        before_time,
        before_time + timedelta(seconds=1),
        content_digest("live-source"),
    )
    current_market = replace(
        source_tape.events[0],
        event_id=before_event.event_id,
        event_time=before_event.event_time,
        sequence=before_event.sequence,
    )
    delivery_binding = NautilusForwardDeliveryBinding(
        "forward-1",
        content_digest(before_event),
        "1-0",
        content_digest("forward-redis-entry"),
        content_digest("forward-dispatch"),
        content_digest("forward-request"),
        checkpoint_fingerprint,
        receipt.fingerprint,
        "enqueue",
    )
    delivery = NautilusForwardDeliveryInput(
        delivery_binding,
        materialize_nautilus_forward_tape(
            "forward-1",
            (before_event,),
            (current_market,),
            event_type_by_dependency={"daily-bars": "ohlcv"},
            delivery_bindings=(delivery_binding,),
        ),
        current_market,
        before_event.source_digest,
    )
    preparation = ForwardStrategyContextPreparation(
        "forward-1",
        delivery.verified_market_payload.fingerprint,
        content_digest("base-context-window"),
        content_digest("next-context-window"),
        StrategyContext(
            before_event.event_time,
            before_event.sequence,
            13,
            component_binding.parameters,
            {},
        ),
        delivery_binding_fingerprint=content_digest(delivery_binding),
        dispatch_fingerprint=delivery_binding.dispatch_record_fingerprint,
        pre_event_checkpoint_fingerprint=checkpoint_fingerprint,
        warmup_receipt_fingerprint=receipt.fingerprint,
    )

    admission = SimpleNamespace(
        checkpoint=SimpleNamespace(instance=instance, fingerprint=checkpoint_fingerprint)
    )
    checkpoint = object.__new__(ResolvedNautilusForwardCheckpoint)
    object.__setattr__(checkpoint, "admission_state", admission)
    object.__setattr__(checkpoint, "warmup_receipt", receipt)
    object.__setattr__(checkpoint, "account_state", object())
    runtime_inputs = ResolvedForwardWorkerRuntimeInputs(plan, checkpoint)

    class RuntimeResolver:
        principal = "owner-a"

        async def resolve(self, **kwargs: Any) -> ResolvedForwardWorkerRuntimeInputs:
            assert kwargs == {
                "instance_id": "forward-1",
                "checkpoint_fingerprint": checkpoint_fingerprint,
            }
            return runtime_inputs

    snapshot_resolver = object.__new__(AuthenticatedFrozenEventTapeResolver)
    snapshot_resolver._principal = "owner-a"

    async def resolve_materialized(
        snapshot_fingerprint: str, requested_manifest: Any
    ) -> tuple[Any, FrozenEventTapeArtifactResolution]:
        assert snapshot_fingerprint == snapshot.fingerprint
        assert requested_manifest.fingerprint == manifest.fingerprint
        return snapshot, source_resolution

    setattr(snapshot_resolver, "resolve_materialized", resolve_materialized)

    class WarmupReader:
        def read_warmup_payloads(self, **kwargs: Any) -> Any:
            assert kwargs["principal"] == "owner-a"
            assert kwargs["instance_id"] == "forward-1"
            return full_payloads

    class PrefixResolver:
        async def __call__(self, **kwargs: Any) -> ForwardProcessedEventPrefix:
            return ForwardProcessedEventPrefix(
                "forward-1",
                checkpoint_fingerprint,
                receipt.fingerprint,
                manifest.fingerprint,
                content_digest(before_event),
                (("daily-bars", manifest.data_dependencies[0].lookback_periods + 1),),
                (),
            )

    class MarketContextResolver:
        def resolve(self, **kwargs: Any) -> ForwardNautilusMarketContext:
            assert kwargs["principal"] == "owner-a"
            return ForwardNautilusMarketContext(
                snapshot.fingerprint,
                portfolio.fingerprint,
                values["instruments"],
                values["venue"],
            )

    resolver = AuthenticatedForwardSandboxPlanInputResolver(
        RuntimeResolver(),
        snapshot_resolver,
        WarmupReader(),
        PrefixResolver(),
        MarketContextResolver(),
        principal="owner-a",
        runtime_profile=RuntimeIsolationProfile(
            content_digest("forward-runtime-image"), package.runtime_abi
        ),
        expected_version="2.0.0rc5",
    )

    result = await resolver.resolve(
        instance_id="forward-1",
        checkpoint_fingerprint=checkpoint_fingerprint,
        principal="owner-a",
        delivery=delivery,
        preparation=preparation,
    )

    assert result.execution_plan is plan
    assert result.snapshot is snapshot
    assert result.tape_manifest == manifest
    assert result.warmup_receipt == receipt
    assert tuple(item.canonical_event.event_id for item in result.warmup_payloads) == (
        cursor.event_id,
    )
    assert result.processed_prefix.pre_event_checkpoint_fingerprint == checkpoint_fingerprint
    assert result.engine_input.data_snapshot_fingerprint == snapshot.fingerprint
    assert result.engine_input.portfolio == portfolio
    assert (
        result.engine_input.event_tape.source_tape_fingerprint
        == result.warmup_tape.tape.fingerprint
    )


def test_forward_warmup_composition_cuts_by_global_canonical_cursor() -> None:
    values = _trial_inputs()
    snapshot = values["snapshot"]
    manifest = values["strategy_manifest"]
    tape = values["event_tape"]
    resolution = FrozenEventTapeArtifactResolution(
        snapshot.fingerprint,
        manifest.fingerprint,
        tape,
        bind_event_tape(tape, snapshot, manifest),
        tuple(sorted(item.content_digest for item in snapshot.series)),
    )
    canonical_payloads = tuple(
        VerifiedForwardMarketPayload(
            CanonicalForwardEvent(
                event.event_id,
                100 + index,
                event.event_time,
                event.event_time,
                content_digest(event.values),
            ),
            replace(event, sequence=100 + index),
            content_digest(event.values),
        )
        for index, event in enumerate(tape.events)
    )
    cursor = canonical_payloads[0].canonical_event
    receipt = ForwardWarmupReceipt(
        "forward-1",
        snapshot.fingerprint,
        CarryInMode.FLAT,
        content_digest("warmup-result"),
        cursor.event_time,
        cursor.event_id,
        cursor.sequence,
        content_digest(cursor),
    )
    before_event = CanonicalForwardEvent(
        "live-current",
        101,
        cursor.event_time
        + (canonical_payloads[1].canonical_event.event_time - cursor.event_time) / 2,
        canonical_payloads[1].canonical_event.event_time,
        content_digest("live-source"),
    )

    by_id = _verify_complete_forward_warmup_payloads(
        resolution,
        canonical_payloads,
        manifest=manifest,
        warmup_receipt=receipt,
        before_event=before_event,
    )
    warmup_tape, warmup_payloads = _cut_forward_warmup_at_receipt(
        snapshot,
        resolution,
        by_id,
        manifest=manifest,
        warmup_receipt=receipt,
    )

    assert tuple(item.canonical_event.event_id for item in warmup_payloads) == (cursor.event_id,)
    assert warmup_tape.tape.event_count == 1
    assert warmup_tape.tape.events[0].sequence == tape.events[0].sequence
    assert warmup_payloads[0].market_event.sequence == cursor.sequence


def test_forward_warmup_composition_rejects_unverified_snapshot_row() -> None:
    values = _trial_inputs()
    snapshot = values["snapshot"]
    manifest = values["strategy_manifest"]
    tape = values["event_tape"]
    resolution = FrozenEventTapeArtifactResolution(
        snapshot.fingerprint,
        manifest.fingerprint,
        tape,
        bind_event_tape(tape, snapshot, manifest),
        tuple(sorted(item.content_digest for item in snapshot.series)),
    )
    event = tape.events[0]
    payload = VerifiedForwardMarketPayload(
        CanonicalForwardEvent(
            event.event_id,
            100,
            event.event_time,
            event.event_time,
            content_digest(event.values),
        ),
        replace(event, sequence=100, values={"close": Decimal("999")}),
        content_digest(event.values),
    )
    following = tape.events[1]
    following_payload = VerifiedForwardMarketPayload(
        CanonicalForwardEvent(
            following.event_id,
            101,
            following.event_time,
            following.event_time,
            content_digest(following.values),
        ),
        replace(following, sequence=101),
        content_digest(following.values),
    )
    receipt = ForwardWarmupReceipt(
        "forward-1",
        snapshot.fingerprint,
        CarryInMode.FLAT,
        content_digest("warmup-result"),
        event.event_time,
        event.event_id,
        100,
        content_digest(payload.canonical_event),
    )

    with pytest.raises(ValueError, match="differs from its frozen source row"):
        _verify_complete_forward_warmup_payloads(
            resolution,
            (payload, following_payload),
            manifest=manifest,
            warmup_receipt=receipt,
            before_event=CanonicalForwardEvent(
                "live-current",
                101,
                event.event_time
                + (values["event_tape"].events[1].event_time - event.event_time) / 2,
                values["event_tape"].events[1].event_time,
                content_digest("live-source"),
            ),
        )


def test_forward_tape_manifest_uses_all_owner_plan_component_requirements() -> None:
    source_manifest = _trial_inputs()["strategy_manifest"]
    longer_dependency = type(source_manifest.data_dependencies[0])(
        source_manifest.data_dependencies[0].dependency_id,
        source_manifest.data_dependencies[0].requirement,
        source_manifest.data_dependencies[0].fields,
        source_manifest.data_dependencies[0].lookback_periods + 3,
    )
    longer_manifest = type(source_manifest)(
        source_manifest.strategy,
        (longer_dependency,),
        source_manifest.model_dependencies,
    )
    plan = object.__new__(ResolvedForwardExecutionPlan)
    object.__setattr__(
        plan,
        "components",
        {
            "component-a": SimpleNamespace(
                strategy=source_manifest.strategy,
                resolved_package=SimpleNamespace(manifest=source_manifest),
            ),
            "component-b": SimpleNamespace(
                strategy=source_manifest.strategy,
                resolved_package=SimpleNamespace(manifest=longer_manifest),
            ),
        },
    )

    combined = build_forward_tape_manifest(plan)

    assert combined.data_dependencies == (longer_dependency,)


@pytest.mark.asyncio
async def test_delivery_context_resolver_binds_exact_checkpoint_plan_and_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persistence = PostgresStrategyLabV2Persistence.build(lambda: None)
    delivery = _delivery()
    inputs = _runtime_inputs()
    calls: list[dict[str, Any]] = []
    context_window = object()

    class RuntimeInputs:
        async def resolve(self, **kwargs: Any) -> ResolvedForwardWorkerRuntimeInputs:
            calls.append({"runtime": kwargs})
            return inputs

    class ContextResolver:
        async def __call__(self, resolved_delivery: NautilusForwardDeliveryInput) -> object:
            calls.append({"delivery": resolved_delivery})
            return context_window

    def build_resolver(
        cls: type[Any],
        execution_plan: Any,
        admission_store: Any,
        account_store: Any,
        history_resolver: Any,
        *,
        principal: Any,
    ) -> ContextResolver:
        calls.append(
            {
                "builder": (execution_plan, admission_store, account_store, history_resolver),
                "principal": principal,
            }
        )
        return ContextResolver()

    monkeypatch.setattr(
        "app.strategy_lab_v2.forward_worker_composition.AuthenticatedForwardPortfolioContextWindowResolver.from_execution_plan",
        classmethod(build_resolver),
    )
    resolver = AuthenticatedForwardDeliveryContextResolver(
        persistence,
        RuntimeInputs(),  # type: ignore[arg-type]
        _unreachable_history,
        principal="owner-a",
    )

    resolved = await resolver(delivery)

    assert resolved is context_window
    assert calls[0] == {
        "runtime": {
            "instance_id": "forward-1",
            "checkpoint_fingerprint": delivery.delivery_binding.pre_event_checkpoint_fingerprint,
        }
    }
    assert calls[1]["principal"] == "owner-a"
    assert calls[1]["builder"][1] is persistence.forward_state
    assert calls[1]["builder"][2] is persistence.forward_account
    assert calls[2] == {"delivery": delivery}


@pytest.mark.asyncio
async def test_delivery_context_resolver_rejects_warmup_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persistence = PostgresStrategyLabV2Persistence.build(lambda: None)
    inputs = _runtime_inputs(warmup_fingerprint=content_digest("other-warmup"))

    class RuntimeInputs:
        async def resolve(self, **_kwargs: Any) -> ResolvedForwardWorkerRuntimeInputs:
            return inputs

    def unexpected_builder(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("context builders must not run for mismatched warm-up")

    monkeypatch.setattr(
        "app.strategy_lab_v2.forward_worker_composition.AuthenticatedForwardPortfolioContextWindowResolver.from_execution_plan",
        unexpected_builder,
    )
    resolver = AuthenticatedForwardDeliveryContextResolver(
        persistence,
        RuntimeInputs(),  # type: ignore[arg-type]
        _unreachable_history,
        principal="owner-a",
    )

    with pytest.raises(ValueError, match="warm-up receipt"):
        await resolver(_delivery())


@pytest.mark.asyncio
async def test_delivery_context_resolver_rejects_checkpoint_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persistence = PostgresStrategyLabV2Persistence.build(lambda: None)
    inputs = _runtime_inputs(checkpoint_fingerprint=content_digest("stale-checkpoint"))

    class RuntimeInputs:
        async def resolve(self, **_kwargs: Any) -> ResolvedForwardWorkerRuntimeInputs:
            return inputs

    def unexpected_builder(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("context builders must not run for a stale checkpoint")

    monkeypatch.setattr(
        "app.strategy_lab_v2.forward_worker_composition.AuthenticatedForwardPortfolioContextWindowResolver.from_execution_plan",
        classmethod(unexpected_builder),
    )
    resolver = AuthenticatedForwardDeliveryContextResolver(
        persistence,
        RuntimeInputs(),  # type: ignore[arg-type]
        _unreachable_history,
        principal="owner-a",
    )

    with pytest.raises(ValueError, match="exact durable checkpoint"):
        await resolver(_delivery())


def test_authenticated_history_factory_requires_explicit_platform_readers() -> None:
    calls: list[dict[str, Any]] = []

    class SnapshotReader:
        def resolve_bounded_window(self, *_args: Any, **_kwargs: Any) -> Any:
            return None

    class FrozenReader:
        def read_frozen_payloads(self, **_kwargs: Any) -> Any:
            return ()

    def processed_prefix(**kwargs: Any) -> Any:
        calls.append(kwargs)
        return None

    persistence = PostgresStrategyLabV2Persistence.build(lambda: None)
    runtime_inputs = _RuntimeInputResolver()
    resolver = create_authenticated_forward_delivery_context_resolver(
        persistence,
        runtime_inputs,  # type: ignore[arg-type]
        snapshot_window_resolver=SnapshotReader(),  # type: ignore[arg-type]
        frozen_payload_reader=FrozenReader(),  # type: ignore[arg-type]
        processed_prefix_resolver=processed_prefix,
        principal="owner-a",
    )

    assert isinstance(resolver, AuthenticatedForwardDeliveryContextResolver)
    assert calls == []


def test_owner_session_handler_composes_authenticated_context_and_native_runtime() -> None:
    persistence = PostgresStrategyLabV2Persistence.build(lambda: None)

    class ProcessFactory:
        async def start(self, **_kwargs: Any) -> Any:
            raise AssertionError("the runtime process starts only for accepted events")

    class SnapshotReader:
        def resolve_bounded_window(self, *_args: Any, **_kwargs: Any) -> Any:
            return None

    class FrozenReader:
        def read_frozen_payloads(self, **_kwargs: Any) -> Any:
            return ()

    def processed_prefix(**_kwargs: Any) -> Any:
        return None

    handler = create_authenticated_forward_session_event_handler(
        persistence,
        _delivery_factory(),
        _RuntimeInputResolver(),  # type: ignore[arg-type]
        ProcessFactory(),  # type: ignore[arg-type]
        snapshot_window_resolver=SnapshotReader(),  # type: ignore[arg-type]
        frozen_payload_reader=FrozenReader(),  # type: ignore[arg-type]
        processed_prefix_resolver=processed_prefix,
        principal="owner-a",
    )

    assert isinstance(handler, NautilusForwardSessionEventHandler)
    assert handler.principal == "owner-a"
    assert isinstance(handler.runtime, PersistentNautilusForwardSessionRuntime)


def test_production_owner_handler_factory_binds_plan_and_process_factory(tmp_path: Any) -> None:
    owner = "owner-a"
    persistence = PostgresStrategyLabV2Persistence.build(lambda: None)
    store = LocalArtifactStore(tmp_path / "artifacts")
    package_resolver = StrategyPackageArtifactResolver(
        store,
        runtime_abi="strategy-runtime.test.v1",
    )

    class SnapshotResolver(AuthenticatedFrozenEventTapeResolver):
        @property
        def principal(self) -> Any:
            return self._principal

        def resolve_bounded_window(self, *_args: Any, **_kwargs: Any) -> Any:
            return None

    class RuntimeResolver:
        principal = owner

        async def resolve(self, **_kwargs: Any) -> Any:
            raise AssertionError("runtime plan is resolved only when a process starts")

    class FrozenReader:
        def read_frozen_payloads(self, **_kwargs: Any) -> Any:
            return ()

    class WarmupReader:
        def read_warmup_payloads(self, **_kwargs: Any) -> Any:
            return ()

    class MarketContextResolver:
        def resolve(self, **_kwargs: Any) -> Any:
            return None

    def prefix_factory(principal: Any) -> Any:
        assert principal == owner
        return _unreachable_history

    def market_context_factory(principal: Any) -> MarketContextResolver:
        assert principal == owner
        return MarketContextResolver()

    def snapshot_factory(principal: Any) -> SnapshotResolver:
        resolver = SnapshotResolver.__new__(SnapshotResolver)
        resolver._principal = principal
        return resolver

    handler_factory = create_authenticated_forward_worker_handler_factory(
        persistence,
        package_resolver,
        store,
        snapshot_resolver_factory=snapshot_factory,
        frozen_payload_reader=FrozenReader(),
        warmup_payload_reader=WarmupReader(),
        processed_prefix_resolver_factory=prefix_factory,
        market_context_resolver_factory=market_context_factory,
        runtime_profile=RuntimeIsolationProfile(
            content_digest("forward-runtime-image"), "strategy-runtime.test.v1"
        ),
        image_name="nautilus-forward:rc5",
        expected_version="2.0.0rc5",
        output_path_resolver=lambda _owner, _instance, _checkpoint: tmp_path / "output.json",
    )

    handler = cast(
        NautilusForwardSessionEventHandler,
        handler_factory(owner, _delivery_factory(), RuntimeResolver()),
    )

    assert handler.principal == owner
    assert isinstance(handler.runtime, PersistentNautilusForwardSessionRuntime)
    process_factory = getattr(handler.runtime, "_process_factory")
    sandbox_factory = getattr(process_factory, "_plan_factory")
    assert isinstance(sandbox_factory, AuthenticatedForwardSandboxPlanFactory)
    assert sandbox_factory._principal == owner
    input_resolver = cast(
        AuthenticatedForwardSandboxPlanInputResolver,
        sandbox_factory._input_resolver,
    )
    assert input_resolver._snapshot_tape_resolver.principal == owner


def _delivery_factory():
    return create_nautilus_forward_delivery_callback_factory(
        lambda **_kwargs: None,  # type: ignore[arg-type]
        event_type_by_dependency={"dependency": "ohlcv"},
    )
