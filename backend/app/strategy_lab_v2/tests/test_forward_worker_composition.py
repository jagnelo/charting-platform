from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_execution_plan_resolution import ResolvedForwardExecutionPlan
from app.strategy_lab_v2.forward_worker_composition import (
    AuthenticatedForwardDeliveryContextResolver,
    AuthenticatedForwardWorkerRuntimeInputResolver,
    OwnerScopedForwardEventHandler,
    ResolvedForwardWorkerRuntimeInputs,
    build_forward_tape_manifest,
    create_authenticated_forward_delivery_context_resolver,
    create_authenticated_forward_session_event_handler,
    create_forward_worker_callbacks,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusForwardDeliveryBinding,
    materialize_nautilus_forward_tape,
)
from app.strategy_lab_v2.nautilus_forward_delivery import (
    create_nautilus_forward_delivery_callback_factory,
)
from app.strategy_lab_v2.nautilus_forward_input import NautilusForwardDeliveryInput
from app.strategy_lab_v2.nautilus_forward_recovery import ResolvedNautilusForwardCheckpoint
from app.strategy_lab_v2.nautilus_forward_session import (
    NautilusForwardSessionEventHandler,
    PersistentNautilusForwardSessionRuntime,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.sdk import MarketEvent
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


def _delivery_factory():
    return create_nautilus_forward_delivery_callback_factory(
        lambda **_kwargs: None,  # type: ignore[arg-type]
        event_type_by_dependency={"dependency": "ohlcv"},
    )
