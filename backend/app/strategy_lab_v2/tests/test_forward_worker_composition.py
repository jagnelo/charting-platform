from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.forward_worker_composition import (
    AuthenticatedForwardWorkerRuntimeInputResolver,
    OwnerScopedForwardEventHandler,
    create_forward_worker_callbacks,
)
from app.strategy_lab_v2.nautilus_forward_delivery import (
    create_nautilus_forward_delivery_callback_factory,
)
from app.strategy_lab_v2.nautilus_forward_session import NautilusForwardSessionEventHandler
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver


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


def _delivery_factory():
    return create_nautilus_forward_delivery_callback_factory(
        lambda **_kwargs: None,  # type: ignore[arg-type]
        event_type_by_dependency={"dependency": "ohlcv"},
    )
