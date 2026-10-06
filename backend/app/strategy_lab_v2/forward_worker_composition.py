"""Owner-isolated composition for the dedicated forward-event worker.

Redis dispatch groups may contain instances belonging to different platform
owners.  A handler, its authenticated plan/checkpoint resolvers, and its
persistent Nautilus process coordinator must therefore be bound to the owner
recorded in the authenticated PostgreSQL dispatch, never to a process-wide
default principal.  This module provides that routing boundary while leaving
canonical-event and frozen-artifact adapters to their owning platform layer.
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.contracts import ForwardInstance
from app.strategy_lab_v2.forward_execution_plan_resolution import (
    AuthenticatedForwardExecutionPlanResolver,
    ForwardExecutionPlanReader,
    ResolvedForwardExecutionPlan,
)
from app.strategy_lab_v2.forward_history_resolution import (
    AuthenticatedForwardContextHistoryResolver,
    ForwardProcessedPrefixResolver,
    FrozenForwardEventWindowResolver,
    FrozenForwardPayloadReader,
)
from app.strategy_lab_v2.forward_worker_handoff import (
    ForwardEventWorkItem,
    create_authenticated_forward_event_materializer,
)
from app.strategy_lab_v2.nautilus_forward_delivery import (
    NautilusForwardDeliveryCallbackFactory,
    VerifiedForwardMarketPayloadResolver,
    create_nautilus_forward_delivery_callback_factory,
)
from app.strategy_lab_v2.nautilus_forward_input import NautilusForwardDeliveryInput
from app.strategy_lab_v2.nautilus_forward_recovery import (
    AuthenticatedNautilusForwardCheckpointResolver,
    ResolvedNautilusForwardCheckpoint,
)
from app.strategy_lab_v2.nautilus_forward_session import (
    AuthenticatedForwardPortfolioContextWindowResolver,
    ForwardVerifiedHistoryResolver,
    NautilusForwardSessionEventHandler,
    NautilusForwardSessionProcessFactory,
    PersistentNautilusForwardSessionRuntime,
    ResolvedForwardContextWindow,
    ResolvedForwardPortfolioContextWindows,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.worker_consumer import WorkerHandleResult

if TYPE_CHECKING:
    from app.strategy_lab_v2.forward_worker_entrypoint import ForwardWorkerCallbacks


@dataclass(frozen=True, slots=True)
class ResolvedForwardWorkerRuntimeInputs:
    """Owner-authenticated immutable plan and exact durable native checkpoint."""

    execution_plan: ResolvedForwardExecutionPlan
    checkpoint: ResolvedNautilusForwardCheckpoint

    def __post_init__(self) -> None:
        if not isinstance(self.execution_plan, ResolvedForwardExecutionPlan):
            raise TypeError("execution_plan must use ResolvedForwardExecutionPlan")
        if not isinstance(self.checkpoint, ResolvedNautilusForwardCheckpoint):
            raise TypeError("checkpoint must use ResolvedNautilusForwardCheckpoint")
        instance = self.execution_plan.instance
        if self.checkpoint.admission_state.checkpoint.instance != instance:
            raise ValueError("forward execution plan and checkpoint instance revisions differ")
        if self.checkpoint.warmup_receipt.instance_id != instance.instance_id:
            raise ValueError("forward warm-up receipt belongs to another execution plan")


class AuthenticatedForwardWorkerRuntimeInputResolver:
    """Load a forward instance, immutable plan, and exact checkpoint by owner."""

    def __init__(
        self,
        resource_reader: ForwardExecutionPlanReader,
        execution_plan_resolver: AuthenticatedForwardExecutionPlanResolver,
        checkpoint_resolver: AuthenticatedNautilusForwardCheckpointResolver,
        *,
        principal: Any,
    ) -> None:
        if not callable(getattr(resource_reader, "get_domain_contract", None)):
            raise TypeError("resource_reader must expose owner-scoped domain reads")
        if not callable(getattr(execution_plan_resolver, "resolve", None)):
            raise TypeError("execution_plan_resolver must resolve authenticated plans")
        if not callable(getattr(checkpoint_resolver, "resolve", None)):
            raise TypeError("checkpoint_resolver must resolve authenticated checkpoints")
        self._resource_reader = resource_reader
        self._execution_plan_resolver = execution_plan_resolver
        self._checkpoint_resolver = checkpoint_resolver
        self._principal = principal

    async def resolve(
        self,
        *,
        instance_id: str,
        checkpoint_fingerprint: str,
    ) -> ResolvedForwardWorkerRuntimeInputs:
        """Fail closed unless all three owner-scoped records agree exactly."""

        instance = await self._resource_reader.get_domain_contract(
            principal=self._principal,
            resource_type=ApiResourceType.FORWARD_INSTANCE,
            resource_id=instance_id,
        )
        if not isinstance(instance, ForwardInstance):
            raise ValueError("owner-scoped forward instance is unavailable")
        if instance.instance_id != instance_id:
            raise ValueError("owner-scoped forward instance identity differs from its key")
        plan, checkpoint = await asyncio.gather(
            self._execution_plan_resolver.resolve(instance),
            self._checkpoint_resolver.resolve(
                instance_id=instance_id,
                checkpoint_fingerprint=checkpoint_fingerprint,
            ),
        )
        if not isinstance(plan, ResolvedForwardExecutionPlan):
            raise TypeError("execution plan resolver returned invalid runtime inputs")
        if not isinstance(checkpoint, ResolvedNautilusForwardCheckpoint):
            raise TypeError("checkpoint resolver returned invalid runtime inputs")
        if plan.instance != instance:
            raise ValueError("resolved execution plan differs from the owner-scoped instance")
        if checkpoint.checkpoint_fingerprint != checkpoint_fingerprint:
            raise ValueError("resolved checkpoint differs from the requested durable cursor")
        return ResolvedForwardWorkerRuntimeInputs(plan, checkpoint)


def create_authenticated_forward_worker_runtime_input_resolver(
    persistence: PostgresStrategyLabV2Persistence,
    package_resolver: StrategyPackageArtifactResolver,
    *,
    principal: Any,
) -> AuthenticatedForwardWorkerRuntimeInputResolver:
    """Bind production PostgreSQL readers and local package bytes to one owner."""

    if not isinstance(persistence, PostgresStrategyLabV2Persistence):
        raise TypeError("persistence must use PostgresStrategyLabV2Persistence")
    if not isinstance(package_resolver, StrategyPackageArtifactResolver):
        raise TypeError("package_resolver must use StrategyPackageArtifactResolver")
    return AuthenticatedForwardWorkerRuntimeInputResolver(
        persistence.resources,
        AuthenticatedForwardExecutionPlanResolver(
            persistence.resources,
            package_resolver,
            principal=principal,
        ),
        AuthenticatedNautilusForwardCheckpointResolver(
            persistence.forward_state,
            persistence.forward_account,
            principal=principal,
        ),
        principal=principal,
    )


class ForwardRuntimeInputResolver(Protocol):
    async def resolve(
        self,
        *,
        instance_id: str,
        checkpoint_fingerprint: str,
    ) -> ResolvedForwardWorkerRuntimeInputs: ...


class AuthenticatedForwardDeliveryContextResolver:
    """Resolve one delivery's portfolio context at its exact owner checkpoint.

    Execution plans and durable checkpoints are resolved through the same
    owner-bound resolver used when bootstrapping a native process. The platform
    supplies frozen/canonical readers explicitly; this class only joins their
    verified history to the immutable plan and exact persisted account state.
    """

    def __init__(
        self,
        persistence: PostgresStrategyLabV2Persistence,
        runtime_input_resolver: ForwardRuntimeInputResolver,
        history_resolver: ForwardVerifiedHistoryResolver,
        *,
        principal: Any,
    ) -> None:
        if not isinstance(persistence, PostgresStrategyLabV2Persistence):
            raise TypeError("persistence must use PostgresStrategyLabV2Persistence")
        if not callable(getattr(runtime_input_resolver, "resolve", None)):
            raise TypeError("runtime_input_resolver must expose authenticated resolve()")
        if not callable(history_resolver):
            raise TypeError("history_resolver must resolve verified canonical history")
        self._persistence = persistence
        self._runtime_input_resolver = runtime_input_resolver
        self._history_resolver = history_resolver
        self._principal = principal

    async def __call__(
        self, delivery: NautilusForwardDeliveryInput
    ) -> ResolvedForwardContextWindow | ResolvedForwardPortfolioContextWindows:
        if not isinstance(delivery, NautilusForwardDeliveryInput):
            raise TypeError("delivery must use NautilusForwardDeliveryInput")
        binding = delivery.delivery_binding
        inputs = await self._runtime_input_resolver.resolve(
            instance_id=binding.instance_id,
            checkpoint_fingerprint=binding.pre_event_checkpoint_fingerprint,
        )
        if not isinstance(inputs, ResolvedForwardWorkerRuntimeInputs):
            raise TypeError("runtime input resolver returned invalid authenticated inputs")
        if inputs.execution_plan.instance.instance_id != binding.instance_id:
            raise ValueError("forward delivery differs from its owner-scoped execution plan")
        if inputs.checkpoint.checkpoint_fingerprint != binding.pre_event_checkpoint_fingerprint:
            raise ValueError("forward delivery differs from its exact durable checkpoint")
        if inputs.checkpoint.warmup_receipt.fingerprint != binding.warmup_receipt_fingerprint:
            raise ValueError("forward delivery differs from its persisted warm-up receipt")

        resolver = AuthenticatedForwardPortfolioContextWindowResolver.from_execution_plan(
            inputs.execution_plan,
            self._persistence.forward_state,
            self._persistence.forward_account,
            self._history_resolver,
            principal=self._principal,
        )
        return await resolver(delivery)


def create_authenticated_forward_context_history_resolver(
    *,
    snapshot_window_resolver: FrozenForwardEventWindowResolver,
    frozen_payload_reader: FrozenForwardPayloadReader,
    processed_prefix_resolver: ForwardProcessedPrefixResolver,
    principal: Any,
) -> AuthenticatedForwardContextHistoryResolver:
    """Bind explicit platform-owned history readers to one authenticated owner."""

    return AuthenticatedForwardContextHistoryResolver(
        snapshot_window_resolver,
        frozen_payload_reader,
        processed_prefix_resolver,
        principal=principal,
    )


def create_authenticated_forward_delivery_context_resolver(
    persistence: PostgresStrategyLabV2Persistence,
    runtime_input_resolver: ForwardRuntimeInputResolver,
    *,
    snapshot_window_resolver: FrozenForwardEventWindowResolver,
    frozen_payload_reader: FrozenForwardPayloadReader,
    processed_prefix_resolver: ForwardProcessedPrefixResolver,
    principal: Any,
) -> AuthenticatedForwardDeliveryContextResolver:
    """Compose exact-checkpoint portfolio context with verified data adapters."""

    history_resolver = create_authenticated_forward_context_history_resolver(
        snapshot_window_resolver=snapshot_window_resolver,
        frozen_payload_reader=frozen_payload_reader,
        processed_prefix_resolver=processed_prefix_resolver,
        principal=principal,
    )
    return AuthenticatedForwardDeliveryContextResolver(
        persistence,
        runtime_input_resolver,
        history_resolver,
        principal=principal,
    )


def create_authenticated_forward_session_event_handler(
    persistence: PostgresStrategyLabV2Persistence,
    delivery_factory: NautilusForwardDeliveryCallbackFactory,
    runtime_input_resolver: ForwardRuntimeInputResolver,
    process_factory: NautilusForwardSessionProcessFactory,
    *,
    snapshot_window_resolver: FrozenForwardEventWindowResolver,
    frozen_payload_reader: FrozenForwardPayloadReader,
    processed_prefix_resolver: ForwardProcessedPrefixResolver,
    principal: Any,
) -> NautilusForwardSessionEventHandler:
    """Compose owner-authenticated context, durable account, and native runtime."""

    if not isinstance(persistence, PostgresStrategyLabV2Persistence):
        raise TypeError("persistence must use PostgresStrategyLabV2Persistence")
    if not isinstance(delivery_factory, NautilusForwardDeliveryCallbackFactory):
        raise TypeError("delivery_factory must use NautilusForwardDeliveryCallbackFactory")
    if not callable(getattr(process_factory, "start", None)):
        raise TypeError("process_factory must launch hardened forward processes")
    context_resolver = create_authenticated_forward_delivery_context_resolver(
        persistence,
        runtime_input_resolver,
        snapshot_window_resolver=snapshot_window_resolver,
        frozen_payload_reader=frozen_payload_reader,
        processed_prefix_resolver=processed_prefix_resolver,
        principal=principal,
    )
    runtime = PersistentNautilusForwardSessionRuntime(process_factory)
    return NautilusForwardSessionEventHandler(
        delivery_factory,
        context_resolver,
        runtime,
        persistence.forward_account,
        principal=principal,
    )


OwnerForwardHandlerFactory = Callable[
    [str, NautilusForwardDeliveryCallbackFactory, ForwardRuntimeInputResolver],
    NautilusForwardSessionEventHandler | Awaitable[NautilusForwardSessionEventHandler],
]
OwnerRuntimeInputResolverFactory = Callable[[str], ForwardRuntimeInputResolver]


class OwnerScopedForwardEventHandler:
    """Route authenticated dispatches to a handler pinned to their owner.

    One handler is retained per owner for the life of the worker.  In
    particular, this keeps a persistent Nautilus runtime and its context
    resolvers from being accidentally shared across owner scopes.
    """

    def __init__(
        self,
        handler_factory: OwnerForwardHandlerFactory,
        delivery_factory: NautilusForwardDeliveryCallbackFactory,
        runtime_input_resolver_factory: OwnerRuntimeInputResolverFactory,
    ) -> None:
        if not callable(handler_factory):
            raise TypeError("handler_factory must be callable")
        if not isinstance(delivery_factory, NautilusForwardDeliveryCallbackFactory):
            raise TypeError("delivery_factory must use NautilusForwardDeliveryCallbackFactory")
        if not callable(runtime_input_resolver_factory):
            raise TypeError("runtime_input_resolver_factory must be callable")
        self._handler_factory = handler_factory
        self._delivery_factory = delivery_factory
        self._runtime_input_resolver_factory = runtime_input_resolver_factory
        self._handlers: dict[str, NautilusForwardSessionEventHandler] = {}
        self._handlers_lock = asyncio.Lock()

    async def __call__(
        self,
        entry: RedisStreamEntry,
        work_item: ForwardEventWorkItem,
    ) -> WorkerHandleResult:
        if not isinstance(entry, RedisStreamEntry):
            raise TypeError("entry must be a RedisStreamEntry")
        if not isinstance(work_item, ForwardEventWorkItem):
            raise TypeError("work_item must be a ForwardEventWorkItem")
        owner_id = work_item.dispatch.owner_id
        if not isinstance(owner_id, str) or not owner_id.strip():
            raise ValueError("authenticated forward dispatch has no owner identity")
        handler = await self._handler_for(owner_id)
        result = handler(entry, work_item)
        resolved = await result if inspect.isawaitable(result) else result
        if not isinstance(resolved, WorkerHandleResult):
            raise TypeError("owner-scoped forward handler returned an invalid result")
        return resolved

    async def _handler_for(self, owner_id: str) -> NautilusForwardSessionEventHandler:
        async with self._handlers_lock:
            handler = self._handlers.get(owner_id)
            if handler is None:
                runtime_input_resolver = self._runtime_input_resolver_factory(owner_id)
                if not callable(getattr(runtime_input_resolver, "resolve", None)):
                    raise TypeError("owner runtime input resolver must expose resolve()")
                resolution = self._handler_factory(
                    owner_id,
                    self._delivery_factory,
                    runtime_input_resolver,
                )
                resolved_handler = (
                    await resolution if inspect.isawaitable(resolution) else resolution
                )
                if not isinstance(resolved_handler, NautilusForwardSessionEventHandler):
                    raise TypeError(
                        "owner handler factory must return a NautilusForwardSessionEventHandler"
                    )
                if resolved_handler.principal != owner_id:
                    raise ValueError("owner handler is not bound to the dispatch owner")
                handler = resolved_handler
                self._handlers[owner_id] = handler
            return handler

    async def close(self) -> None:
        """Dispose every cached per-owner runtime before worker shutdown."""

        async with self._handlers_lock:
            handlers = tuple(self._handlers.values())
            self._handlers.clear()
        for handler in handlers:
            close_all = getattr(handler.runtime, "close_all", None)
            if callable(close_all):
                result = close_all()
                if inspect.isawaitable(result):
                    await result


def create_forward_worker_callbacks(
    persistence: PostgresStrategyLabV2Persistence,
    *,
    queue_name: str,
    payload_resolver: VerifiedForwardMarketPayloadResolver,
    event_type_by_dependency: Mapping[str, str],
    package_resolver: StrategyPackageArtifactResolver,
    owner_handler_factory: OwnerForwardHandlerFactory,
) -> ForwardWorkerCallbacks:
    """Build the production worker callbacks over authenticated persistence.

    The dispatch materializer obtains owner identity from the PostgreSQL row;
    this callback set then routes to that owner's isolated handler/runtime.
    Market payload resolution remains an explicit platform-owned adapter.
    """

    if not isinstance(persistence, PostgresStrategyLabV2Persistence):
        raise TypeError("persistence must use PostgresStrategyLabV2Persistence")
    materializer = create_authenticated_forward_event_materializer(
        persistence.forward_dispatch,
        queue_name=queue_name,
    )
    delivery_factory = create_nautilus_forward_delivery_callback_factory(
        payload_resolver,
        event_type_by_dependency=event_type_by_dependency,
    )
    owner_handler = OwnerScopedForwardEventHandler(
        owner_handler_factory,
        delivery_factory,
        lambda principal: create_authenticated_forward_worker_runtime_input_resolver(
            persistence,
            package_resolver,
            principal=principal,
        ),
    )

    async def handler(
        entry: RedisStreamEntry,
        work_item: ForwardEventWorkItem,
    ) -> WorkerHandleResult:
        return await owner_handler(entry, work_item)

    # Import locally to keep worker entrypoint definitions independent from
    # host composition and avoid a module cycle during callback loading.
    from app.strategy_lab_v2.forward_worker_entrypoint import ForwardWorkerCallbacks

    return ForwardWorkerCallbacks(
        materializer=materializer,
        handler=handler,
        close=owner_handler.close,
    )


__all__ = [
    "AuthenticatedForwardDeliveryContextResolver",
    "AuthenticatedForwardWorkerRuntimeInputResolver",
    "ForwardRuntimeInputResolver",
    "OwnerForwardHandlerFactory",
    "OwnerScopedForwardEventHandler",
    "ResolvedForwardWorkerRuntimeInputs",
    "create_authenticated_forward_worker_runtime_input_resolver",
    "create_authenticated_forward_context_history_resolver",
    "create_authenticated_forward_delivery_context_resolver",
    "create_authenticated_forward_session_event_handler",
    "create_forward_worker_callbacks",
]
