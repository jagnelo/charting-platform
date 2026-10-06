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
import os
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.authenticated_event_tape import AuthenticatedFrozenEventTapeResolver
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import DataSnapshot, ForwardInstance
from app.strategy_lab_v2.event_tape import FrozenEventTape, bind_event_tape
from app.strategy_lab_v2.event_tape_artifacts import (
    FrozenEventTapeArtifactResolution,
    FrozenEventTapeStreamResolution,
)
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
from app.strategy_lab_v2.forward_processed_prefix import ForwardProcessedEventPrefix
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt
from app.strategy_lab_v2.forward_warmup_stream import (
    ForwardWarmupStreamResolution,
    iter_verified_forward_warmup_payloads,
    materialize_forward_warmup_stream,
)
from app.strategy_lab_v2.forward_worker_authorization import (
    DurableForwardWorkerAuthorizationResolver,
)
from app.strategy_lab_v2.forward_worker_handoff import (
    ForwardEventWorkItem,
    create_authenticated_forward_event_materializer,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_engine_input import (
    NautilusComponentStrategyBinding,
    NautilusEngineInput,
    NautilusInstrumentDefinition,
    NautilusVenueDefinition,
)
from app.strategy_lab_v2.nautilus_event_adapter import NautilusEventTape
from app.strategy_lab_v2.nautilus_forward_bootstrap import (
    NautilusForwardBootstrapArtifactReference,
    NautilusForwardRuntimeBootstrap,
    materialize_nautilus_forward_bootstrap_artifact,
)
from app.strategy_lab_v2.nautilus_forward_delivery import (
    NautilusForwardDeliveryCallbackFactory,
    VerifiedForwardMarketPayload,
    VerifiedForwardMarketPayloadResolver,
    create_nautilus_forward_delivery_callback_factory,
)
from app.strategy_lab_v2.nautilus_forward_input import NautilusForwardDeliveryInput
from app.strategy_lab_v2.nautilus_forward_process import (
    ForwardPreparation,
    HardenedNautilusForwardSessionProcessFactory,
)
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
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    NautilusContextStreamArtifactReference,
    NautilusNativeEventStreamArtifactReference,
    NautilusRuntimeInputArtifactReference,
    build_nautilus_runtime_bundle,
    materialize_nautilus_component_context_stream_artifact,
    materialize_nautilus_forward_warmup_artifact_stream,
    materialize_nautilus_runtime_bundle,
    materialize_nautilus_verified_forward_warmup_stream,
    runtime_input_engine_wire_fingerprint,
)
from app.strategy_lab_v2.nautilus_trial_assembly import strategy_runtime_identity
from app.strategy_lab_v2.nautilus_trial_materializer import build_frozen_tape_manifest
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.rebalance import RebalanceExecutionPlan
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.replay import iter_event_tape_contexts
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import StrategyRuntimeRequest
from app.strategy_lab_v2.sandbox import (
    SandboxCommandPlan,
    build_nautilus_forward_runtime_sandbox_command,
)
from app.strategy_lab_v2.sdk import StrategySdkManifest
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.worker_consumer import WorkerHandleResult
from app.strategy_lab_v2.workers import WorkerKind, WorkerProfile
from strategy_runtime import InvocationContextStreamSource

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


@dataclass(frozen=True, slots=True)
class MaterializedForwardRuntimeInputArtifacts:
    """Pinned context/native streams and runtime bundle for one owner plan."""

    context_stream: NautilusContextStreamArtifactReference
    native_event_stream: NautilusNativeEventStreamArtifactReference
    runtime_input: NautilusRuntimeInputArtifactReference

    def __post_init__(self) -> None:
        if not isinstance(self.context_stream, NautilusContextStreamArtifactReference):
            raise TypeError("context_stream must be a NautilusContextStreamArtifactReference")
        if not isinstance(self.native_event_stream, NautilusNativeEventStreamArtifactReference):
            raise TypeError(
                "native_event_stream must be a NautilusNativeEventStreamArtifactReference"
            )
        if not isinstance(self.runtime_input, NautilusRuntimeInputArtifactReference):
            raise TypeError("runtime_input must be a NautilusRuntimeInputArtifactReference")
        if (
            self.runtime_input.context_stream != self.context_stream
            or self.runtime_input.native_event_stream != self.native_event_stream
        ):
            raise ValueError("runtime bundle artifacts differ from their materialized streams")


@dataclass(frozen=True, slots=True)
class MaterializedForwardSandboxPlan:
    """Exact owner-bound bootstrap, runtime evidence, and hardened launch plan."""

    runtime_artifacts: MaterializedForwardRuntimeInputArtifacts
    bootstrap_artifact: NautilusForwardBootstrapArtifactReference
    runtime_request: StrategyRuntimeRequest
    sandbox_plan: SandboxCommandPlan

    def __post_init__(self) -> None:
        if not isinstance(self.runtime_artifacts, MaterializedForwardRuntimeInputArtifacts):
            raise TypeError("runtime_artifacts must be materialized forward inputs")
        if not isinstance(self.bootstrap_artifact, NautilusForwardBootstrapArtifactReference):
            raise TypeError("bootstrap_artifact must be a pinned forward bootstrap")
        if not isinstance(self.runtime_request, StrategyRuntimeRequest):
            raise TypeError("runtime_request must use StrategyRuntimeRequest")
        if not isinstance(self.sandbox_plan, SandboxCommandPlan):
            raise TypeError("sandbox_plan must use SandboxCommandPlan")
        if (
            self.runtime_request.input_bundle_digest
            != self.runtime_artifacts.runtime_input.input_bundle_digest
            or self.runtime_request.attempt_id != self.runtime_artifacts.runtime_input.attempt_id
            or self.sandbox_plan.request_fingerprint != self.runtime_request.fingerprint
        ):
            raise ValueError("forward sandbox plan differs from its pinned runtime attempt")


@dataclass(frozen=True, slots=True)
class ForwardSandboxPlanInputs:
    """Source-verified market/runtime inputs resolved for an exact checkpoint."""

    execution_plan: ResolvedForwardExecutionPlan
    snapshot: DataSnapshot
    tape_manifest: StrategySdkManifest
    warmup_stream: ForwardWarmupStreamResolution
    warmup_receipt: ForwardWarmupReceipt
    processed_prefix: ForwardProcessedEventPrefix
    engine_input: NautilusEngineInput
    runtime_profile: RuntimeIsolationProfile
    expected_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.execution_plan, ResolvedForwardExecutionPlan):
            raise TypeError("execution_plan must use ResolvedForwardExecutionPlan")
        if not isinstance(self.snapshot, DataSnapshot):
            raise TypeError("snapshot must use DataSnapshot")
        if not isinstance(self.tape_manifest, StrategySdkManifest):
            raise TypeError("tape_manifest must use StrategySdkManifest")
        if not isinstance(self.warmup_stream, ForwardWarmupStreamResolution):
            raise TypeError("warmup_stream must use ForwardWarmupStreamResolution")
        if not isinstance(self.warmup_receipt, ForwardWarmupReceipt):
            raise TypeError("warmup_receipt must use ForwardWarmupReceipt")
        if not isinstance(self.processed_prefix, ForwardProcessedEventPrefix):
            raise TypeError("processed_prefix must use ForwardProcessedEventPrefix")
        if not isinstance(self.engine_input, NautilusEngineInput):
            raise TypeError("engine_input must use NautilusEngineInput")
        if not isinstance(self.runtime_profile, RuntimeIsolationProfile):
            raise TypeError("runtime_profile must use RuntimeIsolationProfile")
        if not isinstance(self.expected_version, str) or not self.expected_version.strip():
            raise ValueError("expected_version must not be empty")
        instance = self.execution_plan.instance
        if (
            self.snapshot.fingerprint != instance.warmup_snapshot_fingerprint
            or self.warmup_stream.snapshot_fingerprint != self.snapshot.fingerprint
            or self.warmup_stream.manifest_fingerprint != self.tape_manifest.fingerprint
            or self.warmup_receipt.instance_id != instance.instance_id
            or self.warmup_receipt.warmup_snapshot_fingerprint != self.snapshot.fingerprint
            or self.warmup_stream.cursor_event_id != self.warmup_receipt.final_event_id
            or self.warmup_stream.cursor_event_fingerprint
            != self.warmup_receipt.final_event_fingerprint
            or self.warmup_stream.warmup_receipt_fingerprint != self.warmup_receipt.fingerprint
            or self.processed_prefix.instance_id != instance.instance_id
            or self.processed_prefix.warmup_receipt_fingerprint != self.warmup_receipt.fingerprint
            or self.processed_prefix.manifest_fingerprint != self.tape_manifest.fingerprint
            or self.engine_input.data_snapshot_fingerprint != self.snapshot.fingerprint
            or self.engine_input.portfolio.fingerprint != self.execution_plan.portfolio.fingerprint
            or self.engine_input.event_tape.source_tape_fingerprint
            != self.warmup_stream.tape.tape_fingerprint
            or self.engine_input.event_tape.events
        ):
            raise ValueError("forward sandbox inputs do not share the exact owner snapshot")


class ForwardSandboxPlanInputResolver(Protocol):
    """Resolve only owner-scoped frozen/canonical inputs for one delivery."""

    async def resolve(
        self,
        *,
        instance_id: str,
        checkpoint_fingerprint: str,
        principal: Any,
        delivery: NautilusForwardDeliveryInput,
        preparation: ForwardPreparation,
    ) -> ForwardSandboxPlanInputs: ...


def build_forward_tape_manifest(
    execution_plan: ResolvedForwardExecutionPlan,
) -> StrategySdkManifest:
    """Create the exact shared frozen-tape contract for every plan component."""

    if not isinstance(execution_plan, ResolvedForwardExecutionPlan):
        raise TypeError("execution_plan must use ResolvedForwardExecutionPlan")
    components = tuple(execution_plan.components.values())
    if not components:
        raise ValueError("forward execution plan must contain resolved components")
    primary = components[0]
    return build_frozen_tape_manifest(
        primary.strategy,
        tuple(component.resolved_package.manifest for component in components),
    )


class ForwardWarmupPayloadReader(Protocol):
    """Resolve every frozen tape row to source-verified canonical identity."""

    def read_warmup_payloads(
        self,
        *,
        principal: Any,
        instance_id: str,
        warmup_receipt: ForwardWarmupReceipt,
        manifest: StrategySdkManifest,
        tape: FrozenEventTapeStreamResolution,
    ) -> (
        Iterable[VerifiedForwardMarketPayload] | Awaitable[Iterable[VerifiedForwardMarketPayload]]
    ): ...


@dataclass(frozen=True, slots=True)
class ForwardNautilusMarketContext:
    """Trusted engine metadata resolved for the exact forward portfolio."""

    snapshot_fingerprint: str
    portfolio_fingerprint: str
    instruments: tuple[NautilusInstrumentDefinition, ...]
    venue: NautilusVenueDefinition
    rebalance_plan: RebalanceExecutionPlan | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.snapshot_fingerprint, field_name="snapshot_fingerprint")
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        instruments = tuple(self.instruments)
        if not instruments or any(
            not isinstance(item, NautilusInstrumentDefinition) for item in instruments
        ):
            raise TypeError("instruments must contain NautilusInstrumentDefinition values")
        if not isinstance(self.venue, NautilusVenueDefinition):
            raise TypeError("venue must use NautilusVenueDefinition")
        if self.rebalance_plan is not None and not isinstance(
            self.rebalance_plan, RebalanceExecutionPlan
        ):
            raise TypeError("rebalance_plan must use RebalanceExecutionPlan")
        instrument_ids = tuple(item.instrument_id for item in instruments)
        if len(set(instrument_ids)) != len(instrument_ids):
            raise ValueError("market context instrument ids must be unique")
        if any(item.venue_id != self.venue.venue_id for item in instruments):
            raise ValueError("market context instruments must use the resolved venue")
        object.__setattr__(self, "instruments", instruments)


class ForwardNautilusMarketContextResolver(Protocol):
    """Resolve venue, instruments, and optional frozen rebalance schedule."""

    def resolve(
        self,
        *,
        principal: Any,
        snapshot: DataSnapshot,
        execution_plan: ResolvedForwardExecutionPlan,
        tape_manifest: StrategySdkManifest,
    ) -> ForwardNautilusMarketContext | Awaitable[ForwardNautilusMarketContext]: ...


class AuthenticatedForwardSandboxPlanInputResolver:
    """Join owner plan/checkpoint, frozen source data, and canonical platform adapters.

    This resolver owns deterministic portfolio composition. The snapshot/tape,
    global canonical identity, processed-prefix, and instrument/catalog reads
    remain explicit injected adapters owned by their respective platform layer.
    """

    def __init__(
        self,
        runtime_input_resolver: ForwardRuntimeInputResolver,
        snapshot_tape_resolver: AuthenticatedFrozenEventTapeResolver,
        warmup_payload_reader: ForwardWarmupPayloadReader,
        processed_prefix_resolver: ForwardProcessedPrefixResolver,
        market_context_resolver: ForwardNautilusMarketContextResolver,
        *,
        principal: Any,
        runtime_profile: RuntimeIsolationProfile,
        expected_version: str,
        max_intents_per_event: int = 100,
    ) -> None:
        if not callable(getattr(runtime_input_resolver, "resolve", None)):
            raise TypeError("runtime_input_resolver must resolve owner plan and checkpoint")
        if not isinstance(snapshot_tape_resolver, AuthenticatedFrozenEventTapeResolver):
            raise TypeError("snapshot_tape_resolver must authenticate frozen snapshots")
        if not callable(getattr(warmup_payload_reader, "read_warmup_payloads", None)):
            raise TypeError("warmup_payload_reader must resolve canonical frozen payloads")
        if not callable(processed_prefix_resolver):
            raise TypeError("processed_prefix_resolver must resolve the exact processed prefix")
        if not callable(getattr(market_context_resolver, "resolve", None)):
            raise TypeError("market_context_resolver must resolve canonical engine metadata")
        if principal is None or snapshot_tape_resolver.principal != principal:
            raise ValueError("forward sandbox adapters must share the authenticated principal")
        if getattr(runtime_input_resolver, "principal", None) != principal:
            raise ValueError("runtime plan resolver belongs to another principal")
        if not isinstance(runtime_profile, RuntimeIsolationProfile):
            raise TypeError("runtime_profile must use RuntimeIsolationProfile")
        if not isinstance(expected_version, str) or not expected_version.strip():
            raise ValueError("expected_version must not be empty")
        if (
            not isinstance(max_intents_per_event, int)
            or isinstance(max_intents_per_event, bool)
            or max_intents_per_event < 1
        ):
            raise ValueError("max_intents_per_event must be a positive integer")
        self._runtime_input_resolver = runtime_input_resolver
        self._snapshot_tape_resolver = snapshot_tape_resolver
        self._warmup_payload_reader = warmup_payload_reader
        self._processed_prefix_resolver = processed_prefix_resolver
        self._market_context_resolver = market_context_resolver
        self._principal = principal
        self._runtime_profile = runtime_profile
        self._expected_version = expected_version
        self._max_intents_per_event = max_intents_per_event

    async def resolve(
        self,
        *,
        instance_id: str,
        checkpoint_fingerprint: str,
        principal: Any,
        delivery: NautilusForwardDeliveryInput,
        preparation: ForwardPreparation,
    ) -> ForwardSandboxPlanInputs:
        if principal != self._principal:
            raise ValueError("forward sandbox plan belongs to another principal")
        if not isinstance(delivery, NautilusForwardDeliveryInput):
            raise TypeError("delivery must use NautilusForwardDeliveryInput")
        binding = delivery.delivery_binding
        if (
            binding.instance_id != instance_id
            or binding.pre_event_checkpoint_fingerprint != checkpoint_fingerprint
            or binding.warmup_receipt_fingerprint != preparation.warmup_receipt_fingerprint
            or preparation.instance_id != instance_id
            or preparation.payload_fingerprint != delivery.verified_market_payload.fingerprint
            or preparation.pre_event_checkpoint_fingerprint != checkpoint_fingerprint
        ):
            raise ValueError("forward preparation differs from its authenticated delivery cursor")

        runtime_inputs = self._runtime_input_resolver.resolve(
            instance_id=instance_id,
            checkpoint_fingerprint=checkpoint_fingerprint,
        )
        runtime_inputs = (
            await runtime_inputs if inspect.isawaitable(runtime_inputs) else runtime_inputs
        )
        if not isinstance(runtime_inputs, ResolvedForwardWorkerRuntimeInputs):
            raise TypeError("runtime input resolver returned invalid authenticated inputs")
        plan = runtime_inputs.execution_plan
        checkpoint = runtime_inputs.checkpoint
        if (
            plan.instance.instance_id != instance_id
            or checkpoint.checkpoint_fingerprint != checkpoint_fingerprint
            or checkpoint.warmup_receipt.fingerprint != binding.warmup_receipt_fingerprint
        ):
            raise ValueError("resolved owner plan or checkpoint differs from the delivery")

        tape_manifest = build_forward_tape_manifest(plan)
        _validate_forward_dependency_payload(
            delivery.verified_market_payload,
            tape_manifest,
        )
        snapshot, complete_tape = await self._snapshot_tape_resolver.resolve_with_snapshot(
            plan.instance.warmup_snapshot_fingerprint,
            tape_manifest,
        )
        payload_resolution = self._warmup_payload_reader.read_warmup_payloads(
            principal=self._principal,
            instance_id=instance_id,
            warmup_receipt=checkpoint.warmup_receipt,
            manifest=tape_manifest,
            tape=complete_tape,
        )
        complete_payloads = (
            await payload_resolution
            if inspect.isawaitable(payload_resolution)
            else payload_resolution
        )
        warmup_stream = await asyncio.to_thread(
            materialize_forward_warmup_stream,
            self._snapshot_tape_resolver.artifact_store,
            snapshot=snapshot,
            manifest=tape_manifest,
            complete_tape=complete_tape,
            payloads=complete_payloads,
            receipt=checkpoint.warmup_receipt,
            before_event=delivery.verified_market_payload.canonical_event,
        )

        prefix_resolution = self._processed_prefix_resolver(
            principal=self._principal,
            admission_state=checkpoint.admission_state,
            warmup_receipt=checkpoint.warmup_receipt,
            manifest=tape_manifest,
            before_event=delivery.verified_market_payload.canonical_event,
        )
        processed_prefix = (
            await prefix_resolution if inspect.isawaitable(prefix_resolution) else prefix_resolution
        )
        if not isinstance(processed_prefix, ForwardProcessedEventPrefix):
            raise TypeError("processed-prefix resolver returned an invalid prefix")
        expected_limits = tuple(
            sorted(
                (
                    dependency.dependency_id,
                    dependency.lookback_periods + 1,
                )
                for dependency in tape_manifest.data_dependencies
            )
        )
        if (
            processed_prefix.instance_id != instance_id
            or processed_prefix.pre_event_checkpoint_fingerprint != checkpoint_fingerprint
            or processed_prefix.warmup_receipt_fingerprint != checkpoint.warmup_receipt.fingerprint
            or processed_prefix.manifest_fingerprint != tape_manifest.fingerprint
            or processed_prefix.before_event_fingerprint
            != content_digest(delivery.verified_market_payload.canonical_event)
            or processed_prefix.dependency_event_limits != expected_limits
        ):
            raise ValueError("processed prefix differs from the exact forward delivery cursor")

        context_resolution = self._market_context_resolver.resolve(
            principal=self._principal,
            snapshot=snapshot,
            execution_plan=plan,
            tape_manifest=tape_manifest,
        )
        market_context = (
            await context_resolution
            if inspect.isawaitable(context_resolution)
            else context_resolution
        )
        if not isinstance(market_context, ForwardNautilusMarketContext):
            raise TypeError("market-context resolver returned invalid engine metadata")
        if (
            market_context.snapshot_fingerprint != snapshot.fingerprint
            or market_context.portfolio_fingerprint != plan.portfolio.fingerprint
        ):
            raise ValueError("market context differs from the exact frozen owner portfolio")
        strategies = tuple(component.strategy for component in plan.components.values())
        packages = {
            component.strategy.fingerprint: component.package
            for component in plan.components.values()
        }
        identity = strategy_runtime_identity(strategies, packages)
        if self._runtime_profile.runtime_abi != identity.runtime_abi:
            raise ValueError("forward runtime profile differs from the exact owner package ABI")
        engine_input = _build_forward_nautilus_engine_input(
            execution_plan=plan,
            snapshot=snapshot,
            tape_manifest=tape_manifest,
            warmup_stream=warmup_stream,
            market_context=market_context,
            checkpoint_fingerprint=checkpoint_fingerprint,
            max_intents_per_event=self._max_intents_per_event,
        )
        return ForwardSandboxPlanInputs(
            execution_plan=plan,
            snapshot=snapshot,
            tape_manifest=tape_manifest,
            warmup_stream=warmup_stream,
            warmup_receipt=checkpoint.warmup_receipt,
            processed_prefix=processed_prefix,
            engine_input=engine_input,
            runtime_profile=self._runtime_profile,
            expected_version=self._expected_version,
        )


class AuthenticatedForwardSandboxPlanFactory:
    """Async owner-bound adapter consumed by the hardened process factory."""

    def __init__(
        self,
        store: LocalArtifactStore,
        input_resolver: ForwardSandboxPlanInputResolver,
        *,
        principal: Any,
        image_name: str,
        output_path_resolver: Callable[[str, str], str | os.PathLike[str]],
    ) -> None:
        if not isinstance(store, LocalArtifactStore):
            raise TypeError("store must be a LocalArtifactStore")
        if not callable(getattr(input_resolver, "resolve", None)):
            raise TypeError("input_resolver must expose async resolve()")
        if not isinstance(image_name, str) or not image_name.strip():
            raise ValueError("image_name must not be empty")
        if principal is None:
            raise ValueError("principal must be owner-authenticated")
        if not callable(output_path_resolver):
            raise TypeError("output_path_resolver must be callable")
        self._store = store
        self._input_resolver = input_resolver
        self._principal = principal
        self._image_name = image_name
        self._output_path_resolver = output_path_resolver

    async def __call__(
        self,
        instance_id: str,
        checkpoint_fingerprint: str,
        delivery: NautilusForwardDeliveryInput,
        preparation: ForwardPreparation,
    ) -> SandboxCommandPlan:
        if delivery.delivery_binding.instance_id != instance_id:
            raise ValueError("forward launch delivery differs from the requested instance")
        if delivery.delivery_binding.pre_event_checkpoint_fingerprint != checkpoint_fingerprint:
            raise ValueError("forward launch delivery differs from the requested checkpoint")
        if preparation.instance_id != instance_id:
            raise ValueError("forward launch preparation belongs to another instance")
        if preparation.payload_fingerprint != delivery.verified_market_payload.fingerprint:
            raise ValueError("forward launch preparation differs from its canonical delivery")
        if (
            preparation.pre_event_checkpoint_fingerprint != checkpoint_fingerprint
            or preparation.warmup_receipt_fingerprint
            != delivery.delivery_binding.warmup_receipt_fingerprint
        ):
            raise ValueError("forward launch preparation differs from its checkpoint binding")

        resolved = self._input_resolver.resolve(
            instance_id=instance_id,
            checkpoint_fingerprint=checkpoint_fingerprint,
            principal=self._principal,
            delivery=delivery,
            preparation=preparation,
        )
        inputs = await resolved if inspect.isawaitable(resolved) else resolved
        if not isinstance(inputs, ForwardSandboxPlanInputs):
            raise TypeError("forward sandbox input resolver returned invalid host inputs")
        if inputs.execution_plan.instance.instance_id != instance_id:
            raise ValueError("resolved forward plan belongs to another instance")
        if (
            inputs.warmup_receipt.fingerprint
            != delivery.delivery_binding.warmup_receipt_fingerprint
        ):
            raise ValueError("resolved forward warm-up receipt differs from the delivery")
        if inputs.processed_prefix.pre_event_checkpoint_fingerprint != checkpoint_fingerprint:
            raise ValueError("resolved processed prefix differs from the requested checkpoint")
        if inputs.processed_prefix.before_event_fingerprint != content_digest(
            delivery.verified_market_payload.canonical_event
        ):
            raise ValueError("resolved processed prefix is not bound to the canonical delivery")
        output_path = self._output_path_resolver(instance_id, checkpoint_fingerprint)
        result = await asyncio.to_thread(
            materialize_authenticated_forward_sandbox_plan,
            self._store,
            execution_plan=inputs.execution_plan,
            checkpoint_fingerprint=checkpoint_fingerprint,
            warmup_receipt=inputs.warmup_receipt,
            snapshot=inputs.snapshot,
            tape_manifest=inputs.tape_manifest,
            warmup_stream=inputs.warmup_stream,
            processed_prefix=inputs.processed_prefix,
            engine_input=inputs.engine_input,
            runtime_profile=inputs.runtime_profile,
            image_name=self._image_name,
            expected_version=inputs.expected_version,
            output_path=os.fspath(output_path),
            submitted_at=delivery.verified_market_payload.canonical_event.event_time,
        )
        return result.sandbox_plan


def materialize_authenticated_forward_sandbox_plan(
    store: LocalArtifactStore,
    *,
    execution_plan: ResolvedForwardExecutionPlan,
    checkpoint_fingerprint: str,
    warmup_receipt: ForwardWarmupReceipt,
    snapshot: DataSnapshot,
    tape_manifest: StrategySdkManifest,
    warmup_stream: ForwardWarmupStreamResolution | None = None,
    warmup_tape: FrozenEventTapeArtifactResolution | None = None,
    warmup_payloads: Sequence[VerifiedForwardMarketPayload] | None = None,
    processed_prefix: ForwardProcessedEventPrefix,
    engine_input: NautilusEngineInput,
    runtime_profile: RuntimeIsolationProfile,
    image_name: str,
    expected_version: str,
    output_path: str,
    submitted_at: datetime,
) -> MaterializedForwardSandboxPlan:
    """Compose exact owner/checkpoint inputs into an RC5-capable sandbox plan.

    Snapshot, canonical history, venue/instrument definitions, runtime image,
    and output location are explicit host-owned inputs. The function never
    reads a provider, derives canonical identities, or substitutes mutable
    history for the frozen snapshot.
    """

    if not isinstance(warmup_receipt, ForwardWarmupReceipt):
        raise TypeError("warmup_receipt must use ForwardWarmupReceipt")
    if not isinstance(checkpoint_fingerprint, str) or not checkpoint_fingerprint.strip():
        raise ValueError("checkpoint_fingerprint must not be empty")
    if not isinstance(runtime_profile, RuntimeIsolationProfile):
        raise TypeError("runtime_profile must use RuntimeIsolationProfile")
    if not isinstance(processed_prefix, ForwardProcessedEventPrefix):
        raise TypeError("processed_prefix must use ForwardProcessedEventPrefix")
    if not isinstance(image_name, str) or not image_name.strip():
        raise ValueError("image_name must not be empty")
    if not isinstance(expected_version, str) or not expected_version.strip():
        raise ValueError("expected_version must not be empty")
    if not isinstance(output_path, str) or not output_path.strip():
        raise ValueError("output_path must not be empty")
    if not isinstance(submitted_at, datetime):
        raise TypeError("submitted_at must be a timezone-aware datetime")
    instance = execution_plan.instance
    if (
        warmup_receipt.instance_id != instance.instance_id
        or warmup_receipt.warmup_snapshot_fingerprint != instance.warmup_snapshot_fingerprint
        or processed_prefix.instance_id != instance.instance_id
        or processed_prefix.pre_event_checkpoint_fingerprint != checkpoint_fingerprint
        or processed_prefix.warmup_receipt_fingerprint != warmup_receipt.fingerprint
    ):
        raise ValueError("forward sandbox inputs differ from the exact owner checkpoint")
    if warmup_stream is not None and (
        warmup_stream.snapshot_fingerprint != snapshot.fingerprint
        or warmup_stream.warmup_receipt_fingerprint != warmup_receipt.fingerprint
        or warmup_stream.cursor_event_id != warmup_receipt.final_event_id
        or warmup_stream.cursor_event_fingerprint != warmup_receipt.final_event_fingerprint
    ):
        raise ValueError("streamed forward warm-up differs from the exact receipt")

    # The runtime CLI validates STRATEGY_ATTEMPT_ID against the immutable
    # engine_input.attempt_id inside the bundle. Derive this process-attempt
    # identity once and bind it before any bundle/bootstrap bytes are published.
    attempt_id = forward_runtime_attempt_id(instance.instance_id, checkpoint_fingerprint)
    engine_input = replace(
        engine_input,
        trial_id=instance.instance_id,
        attempt_id=attempt_id,
    )

    if warmup_stream is not None:
        if warmup_tape is not None or warmup_payloads is not None:
            raise ValueError("streaming warm-up cannot be mixed with materialized rows")
        runtime_artifacts = materialize_authenticated_forward_runtime_bundle_from_stream(
            store,
            execution_plan=execution_plan,
            snapshot=snapshot,
            tape_manifest=tape_manifest,
            warmup_stream=warmup_stream,
            engine_input=engine_input,
        )
        bootstrap = NautilusForwardRuntimeBootstrap.build(
            execution_plan=execution_plan,
            snapshot=snapshot,
            warmup_receipt=warmup_receipt,
            warmup_stream=warmup_stream,
            processed_prefix=processed_prefix,
            engine_input=engine_input,
            runtime_engine_input_fingerprint=runtime_input_engine_wire_fingerprint(
                store, runtime_artifacts.runtime_input
            ),
            runtime_input_bundle_digest=runtime_artifacts.runtime_input.input_bundle_digest,
            native_event_stream=runtime_artifacts.native_event_stream,
        )
    else:
        if warmup_tape is None or warmup_payloads is None:
            raise TypeError("materialized warm-up requires both tape and canonical payloads")
        runtime_artifacts = materialize_authenticated_forward_runtime_bundle(
            store,
            execution_plan=execution_plan,
            snapshot=snapshot,
            tape_manifest=tape_manifest,
            warmup_tape=warmup_tape,
            warmup_payloads=warmup_payloads,
            engine_input=engine_input,
        )
        bootstrap = NautilusForwardRuntimeBootstrap.build(
            execution_plan=execution_plan,
            snapshot=snapshot,
            warmup_receipt=warmup_receipt,
            warmup_tape=warmup_tape,
            warmup_payloads=warmup_payloads,
            processed_prefix=processed_prefix,
            engine_input=engine_input,
            runtime_engine_input_fingerprint=runtime_input_engine_wire_fingerprint(
                store, runtime_artifacts.runtime_input
            ),
            runtime_input_bundle_digest=runtime_artifacts.runtime_input.input_bundle_digest,
            native_event_stream=runtime_artifacts.native_event_stream,
        )
    bootstrap_artifact = materialize_nautilus_forward_bootstrap_artifact(store, bootstrap)

    strategies = tuple(item.strategy for item in execution_plan.components.values())
    packages = {
        item.strategy.fingerprint: item.package for item in execution_plan.components.values()
    }
    identity = strategy_runtime_identity(strategies, packages)
    if runtime_profile.runtime_abi != identity.runtime_abi:
        raise ValueError("forward runtime isolation ABI differs from its exact strategy packages")
    runtime_request = StrategyRuntimeRequest(
        request_id=content_digest(
            {
                "attempt_id": attempt_id,
                "bootstrap_fingerprint": bootstrap.fingerprint,
                "runtime_input_digest": runtime_artifacts.runtime_input.input_bundle_digest,
            }
        ),
        attempt_id=attempt_id,
        package_fingerprint=identity.package_fingerprint,
        source_digest=identity.source_digest,
        input_bundle_digest=runtime_artifacts.runtime_input.input_bundle_digest,
        runtime_profile_fingerprint=runtime_profile.fingerprint,
        entrypoint=identity.entrypoint,
        isolation_request=RuntimeIsolationRequest(
            attempt_id=attempt_id,
            dependency_digests=identity.dependency_digests,
        ),
        submitted_at=submitted_at,
    )
    sandbox_plan = build_nautilus_forward_runtime_sandbox_command(
        runtime_request,
        runtime_profile,
        image_name=image_name,
        input_bundle_path=store.path_for(runtime_artifacts.runtime_input.artifact.storage_key),
        forward_bootstrap_path=bootstrap_artifact.path,
        bootstrap_fingerprint=bootstrap_artifact.bootstrap_fingerprint,
        context_stream_path=store.path_for(runtime_artifacts.context_stream.artifact.storage_key),
        context_stream_digest=runtime_artifacts.context_stream.artifact.content_digest,
        native_event_stream_path=store.path_for(
            runtime_artifacts.native_event_stream.artifact.storage_key
        ),
        native_event_stream_digest=runtime_artifacts.native_event_stream.artifact.content_digest,
        output_path=output_path,
        instance_id=instance.instance_id,
        expected_version=expected_version,
        snapshot_fingerprint=snapshot.fingerprint,
    )
    return MaterializedForwardSandboxPlan(
        runtime_artifacts,
        bootstrap_artifact,
        runtime_request,
        sandbox_plan,
    )


def forward_runtime_attempt_id(instance_id: str, checkpoint_fingerprint: str) -> str:
    """Return the deterministic runtime request identity for one exact cursor."""

    if not isinstance(instance_id, str) or not instance_id.strip():
        raise ValueError("instance_id must not be empty")
    if not isinstance(checkpoint_fingerprint, str) or not checkpoint_fingerprint.strip():
        raise ValueError("checkpoint_fingerprint must not be empty")
    return content_digest(
        {
            "checkpoint_fingerprint": checkpoint_fingerprint,
            "instance_id": instance_id,
            "kind": "forward-process-bootstrap",
        }
    )


def materialize_authenticated_forward_runtime_bundle(
    store: LocalArtifactStore,
    *,
    execution_plan: ResolvedForwardExecutionPlan,
    snapshot: DataSnapshot,
    tape_manifest: StrategySdkManifest,
    warmup_tape: FrozenEventTapeArtifactResolution,
    warmup_payloads: Sequence[VerifiedForwardMarketPayload],
    engine_input: NautilusEngineInput,
) -> MaterializedForwardRuntimeInputArtifacts:
    """Build owner-plan component contexts and immutable RC runtime inputs.

    Host-owned canonical readers supply ``warmup_payloads`` and the aggregate
    tape manifest. This composer checks their binding against the exact owner
    plan and engine input; it never infers global ordering from tape-local row
    counters.
    """

    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must be a LocalArtifactStore")
    if not isinstance(execution_plan, ResolvedForwardExecutionPlan):
        raise TypeError("execution_plan must use ResolvedForwardExecutionPlan")
    if not isinstance(snapshot, DataSnapshot):
        raise TypeError("snapshot must be a DataSnapshot")
    if not isinstance(tape_manifest, StrategySdkManifest):
        raise TypeError("tape_manifest must use StrategySdkManifest")
    if not isinstance(warmup_tape, FrozenEventTapeArtifactResolution):
        raise TypeError("warmup_tape must use FrozenEventTapeArtifactResolution")
    if not isinstance(engine_input, NautilusEngineInput):
        raise TypeError("engine_input must use NautilusEngineInput")

    instance = execution_plan.instance
    if (
        snapshot.fingerprint != instance.warmup_snapshot_fingerprint
        or warmup_tape.snapshot_fingerprint != snapshot.fingerprint
        or engine_input.data_snapshot_fingerprint != snapshot.fingerprint
        or engine_input.portfolio.fingerprint != execution_plan.portfolio.fingerprint
    ):
        raise ValueError("forward runtime bundle inputs differ from their owner plan snapshot")
    if (
        engine_input.event_tape.source_tape_fingerprint != warmup_tape.tape.fingerprint
        or len(engine_input.event_tape.events) != warmup_tape.tape.event_count
    ):
        raise ValueError("forward engine input differs from the exact frozen warm-up tape")

    bindings = {item.component_id: item for item in engine_input.strategy_bindings}
    if set(bindings) != set(execution_plan.components):
        raise ValueError("forward engine input bindings differ from the owner execution plan")
    ordered_payloads = tuple(
        sorted(
            warmup_payloads,
            key=lambda item: (item.canonical_event.event_time, item.canonical_event.sequence),
        )
    )
    component_streams: list[InvocationContextStreamSource] = []
    for component_id, resolved in execution_plan.components.items():
        binding = bindings[component_id]
        manifest = resolved.resolved_package.manifest
        if (
            binding.strategy_fingerprint != resolved.strategy.fingerprint
            or binding.strategy_source_digest != manifest.strategy.source_digest
            or binding.strategy_manifest_fingerprint != manifest.fingerprint
            or binding.entrypoint != resolved.package.entrypoint
            or binding.parameters_digest != content_digest(resolved.binding.parameters)
        ):
            raise ValueError("forward runtime strategy binding differs from its owner package")
        dependency_ids = {item.dependency_id for item in manifest.data_dependencies}
        events = (
            payload.market_event
            for payload in ordered_payloads
            if payload.market_event.dependency_id in dependency_ids
        )
        component_streams.append(
            InvocationContextStreamSource(
                component_id=component_id,
                source=resolved.resolved_package.source,
                manifest=manifest,
                contexts=iter_event_tape_contexts(
                    events,
                    manifest,
                    random_seed=resolved.binding.random_seed,
                    parameters=resolved.binding.parameters,
                ),
                entrypoint=resolved.package.entrypoint,
                max_intents_per_event=binding.max_intents_per_event,
            )
        )

    native_stream = materialize_nautilus_verified_forward_warmup_stream(
        store,
        snapshot=snapshot,
        manifest=tape_manifest,
        warmup_tape=warmup_tape,
        payloads=ordered_payloads,
    )
    context_stream = materialize_nautilus_component_context_stream_artifact(
        store,
        components=tuple(component_streams),
    )
    bundle = build_nautilus_runtime_bundle(
        engine_input,
        context_stream=context_stream,
        native_event_stream=native_stream,
    )
    runtime_input = materialize_nautilus_runtime_bundle(bundle, store)
    return MaterializedForwardRuntimeInputArtifacts(
        context_stream,
        native_stream,
        runtime_input,
    )


def materialize_authenticated_forward_runtime_bundle_from_stream(
    store: LocalArtifactStore,
    *,
    execution_plan: ResolvedForwardExecutionPlan,
    snapshot: DataSnapshot,
    tape_manifest: StrategySdkManifest,
    warmup_stream: ForwardWarmupStreamResolution,
    engine_input: NautilusEngineInput,
) -> MaterializedForwardRuntimeInputArtifacts:
    """Build runtime artifacts by streaming the verified canonical warm-up rows."""

    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must be a LocalArtifactStore")
    if not isinstance(execution_plan, ResolvedForwardExecutionPlan):
        raise TypeError("execution_plan must use ResolvedForwardExecutionPlan")
    if not isinstance(snapshot, DataSnapshot):
        raise TypeError("snapshot must use DataSnapshot")
    if not isinstance(tape_manifest, StrategySdkManifest):
        raise TypeError("tape_manifest must use StrategySdkManifest")
    if not isinstance(warmup_stream, ForwardWarmupStreamResolution):
        raise TypeError("warmup_stream must use ForwardWarmupStreamResolution")
    if not isinstance(engine_input, NautilusEngineInput):
        raise TypeError("engine_input must use NautilusEngineInput")

    instance = execution_plan.instance
    if (
        snapshot.fingerprint != instance.warmup_snapshot_fingerprint
        or warmup_stream.snapshot_fingerprint != snapshot.fingerprint
        or warmup_stream.manifest_fingerprint != tape_manifest.fingerprint
        or engine_input.data_snapshot_fingerprint != snapshot.fingerprint
        or engine_input.portfolio.fingerprint != execution_plan.portfolio.fingerprint
        or engine_input.event_tape.source_tape_fingerprint != warmup_stream.tape.tape_fingerprint
        or engine_input.event_tape.events
    ):
        raise ValueError("forward streaming runtime inputs differ from their owner plan")

    bindings = {item.component_id: item for item in engine_input.strategy_bindings}
    if set(bindings) != set(execution_plan.components):
        raise ValueError("forward engine input bindings differ from the owner execution plan")
    component_streams: list[InvocationContextStreamSource] = []
    for component_id, resolved in execution_plan.components.items():
        binding = bindings[component_id]
        manifest = resolved.resolved_package.manifest
        if (
            binding.strategy_fingerprint != resolved.strategy.fingerprint
            or binding.strategy_source_digest != manifest.strategy.source_digest
            or binding.strategy_manifest_fingerprint != manifest.fingerprint
            or binding.entrypoint != resolved.package.entrypoint
            or binding.parameters_digest != content_digest(resolved.binding.parameters)
        ):
            raise ValueError("forward runtime strategy binding differs from its owner package")
        dependency_ids = {item.dependency_id for item in manifest.data_dependencies}
        market_events = (
            payload.market_event
            for payload in iter_verified_forward_warmup_payloads(warmup_stream, store)
            if payload.market_event.dependency_id in dependency_ids
        )
        component_streams.append(
            InvocationContextStreamSource(
                component_id=component_id,
                source=resolved.resolved_package.source,
                manifest=manifest,
                contexts=iter_event_tape_contexts(
                    market_events,
                    manifest,
                    random_seed=resolved.binding.random_seed,
                    parameters=resolved.binding.parameters,
                ),
                entrypoint=resolved.package.entrypoint,
                max_intents_per_event=binding.max_intents_per_event,
            )
        )

    native_stream = materialize_nautilus_forward_warmup_artifact_stream(
        store,
        snapshot=snapshot,
        manifest=tape_manifest,
        warmup=warmup_stream,
    )
    if native_stream.event_count != warmup_stream.event_count:
        raise ValueError("native and canonical warm-up stream counts differ")
    context_stream = materialize_nautilus_component_context_stream_artifact(
        store,
        components=tuple(component_streams),
    )
    bundle = build_nautilus_runtime_bundle(
        engine_input,
        context_stream=context_stream,
        native_event_stream=native_stream,
    )
    runtime_input = materialize_nautilus_runtime_bundle(bundle, store)
    return MaterializedForwardRuntimeInputArtifacts(
        context_stream,
        native_stream,
        runtime_input,
    )


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

    @property
    def principal(self) -> Any:
        """Authenticated owner principal used for all runtime-input reads."""

        return self._principal

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


def _verify_complete_forward_warmup_payloads(
    tape: FrozenEventTapeArtifactResolution,
    payloads: Sequence[VerifiedForwardMarketPayload],
    *,
    manifest: StrategySdkManifest,
    warmup_receipt: ForwardWarmupReceipt,
    before_event: CanonicalForwardEvent,
) -> dict[str, VerifiedForwardMarketPayload]:
    if not isinstance(tape, FrozenEventTapeArtifactResolution):
        raise TypeError("tape must use FrozenEventTapeArtifactResolution")
    if not isinstance(before_event, CanonicalForwardEvent):
        raise TypeError("before_event must use CanonicalForwardEvent")
    if not isinstance(payloads, Sequence) or isinstance(payloads, str | bytes):
        raise TypeError("warmup payload reader must return a sequence")
    resolved = tuple(payloads)
    if any(not isinstance(item, VerifiedForwardMarketPayload) for item in resolved):
        raise TypeError("warmup payload reader returned an invalid canonical payload")
    by_id = {item.canonical_event.event_id: item for item in resolved}
    tape_by_id = {item.event_id: item for item in tape.tape.events}
    if len(by_id) != len(resolved) or set(by_id) != set(tape_by_id):
        raise ValueError("canonical payloads do not exactly cover the frozen snapshot tape")
    sequence_values = [item.canonical_event.sequence for item in resolved]
    if len(sequence_values) != len(set(sequence_values)):
        raise ValueError("canonical frozen event sequences must be unique")
    ordered = sorted(
        resolved,
        key=lambda item: (item.canonical_event.event_time, item.canonical_event.sequence),
    )
    if any(item.canonical_event.correction_of is not None for item in ordered):
        raise ValueError("correction events cannot enter immutable forward warm-up")
    for item in ordered:
        tape_event = tape_by_id[item.canonical_event.event_id]
        market = item.market_event
        if (
            market.dependency_id != tape_event.dependency_id
            or market.event_id != tape_event.event_id
            or market.instrument_id != tape_event.instrument_id
            or market.event_time != tape_event.event_time
            or market.values != tape_event.values
        ):
            raise ValueError("canonical warm-up payload differs from its frozen source row")
        dependency = next(
            (
                candidate
                for candidate in manifest.data_dependencies
                if candidate.dependency_id == market.dependency_id
            ),
            None,
        )
        if (
            dependency is None
            or dependency.requirement.instrument_id != market.instrument_id
            or set(market.values) != set(dependency.fields)
            or not dependency.requirement.start <= market.event_time < dependency.requirement.end
        ):
            raise ValueError("canonical warm-up payload is outside its declared dependency")

    receipt_event = by_id.get(warmup_receipt.final_event_id or "")
    if (
        receipt_event is None
        or content_digest(receipt_event.canonical_event) != warmup_receipt.final_event_fingerprint
        or receipt_event.canonical_event.sequence != warmup_receipt.final_event_sequence
    ):
        raise ValueError("canonical warm-up payloads do not contain the exact durable cursor")
    if (
        receipt_event.canonical_event.event_time,
        receipt_event.canonical_event.sequence,
    ) >= (before_event.event_time, before_event.sequence):
        raise ValueError("current event does not follow the frozen warm-up cursor")
    return by_id


def _validate_forward_dependency_payload(
    payload: VerifiedForwardMarketPayload,
    manifest: StrategySdkManifest,
) -> None:
    if not isinstance(payload, VerifiedForwardMarketPayload):
        raise TypeError("payload must use VerifiedForwardMarketPayload")
    dependency = next(
        (
            item
            for item in manifest.data_dependencies
            if item.dependency_id == payload.market_event.dependency_id
        ),
        None,
    )
    if (
        dependency is None
        or payload.canonical_event.correction_of is not None
        or dependency.requirement.instrument_id != payload.market_event.instrument_id
        or set(payload.market_event.values) != set(dependency.fields)
        or not dependency.requirement.start
        <= payload.market_event.event_time
        < dependency.requirement.end
    ):
        raise ValueError("forward delivery payload is outside its declared strategy inputs")


def _cut_forward_warmup_at_receipt(
    snapshot: DataSnapshot,
    complete_tape: FrozenEventTapeArtifactResolution,
    payloads_by_id: Mapping[str, VerifiedForwardMarketPayload],
    *,
    manifest: StrategySdkManifest,
    warmup_receipt: ForwardWarmupReceipt,
) -> tuple[FrozenEventTapeArtifactResolution, tuple[VerifiedForwardMarketPayload, ...]]:
    cursor = payloads_by_id.get(warmup_receipt.final_event_id or "")
    if cursor is None:
        raise ValueError("forward warm-up receipt has no frozen cursor event")
    cursor_key = (cursor.canonical_event.event_time, cursor.canonical_event.sequence)
    selected_payloads = tuple(
        sorted(
            (
                item
                for item in payloads_by_id.values()
                if (item.canonical_event.event_time, item.canonical_event.sequence) <= cursor_key
            ),
            key=lambda item: (item.canonical_event.event_time, item.canonical_event.sequence),
        )
    )
    selected_ids = {item.canonical_event.event_id for item in selected_payloads}
    if cursor.canonical_event.event_id not in selected_ids:
        raise ValueError("frozen warm-up prefix omitted its exact durable cursor")
    frozen_events_by_id = {item.event_id: item for item in complete_tape.tape.events}
    tape = FrozenEventTape(
        snapshot.fingerprint,
        tuple(frozen_events_by_id[item.canonical_event.event_id] for item in selected_payloads),
    )
    binding = bind_event_tape(tape, snapshot, manifest)
    return (
        FrozenEventTapeArtifactResolution(
            snapshot.fingerprint,
            manifest.fingerprint,
            tape,
            binding,
            complete_tape.source_artifact_digests,
        ),
        selected_payloads,
    )


def _build_forward_nautilus_engine_input(
    *,
    execution_plan: ResolvedForwardExecutionPlan,
    snapshot: DataSnapshot,
    tape_manifest: StrategySdkManifest,
    warmup_stream: ForwardWarmupStreamResolution,
    market_context: ForwardNautilusMarketContext,
    checkpoint_fingerprint: str,
    max_intents_per_event: int,
) -> NautilusEngineInput:
    portfolio = execution_plan.portfolio
    venue = market_context.venue
    if venue.base_currency != portfolio.base_currency:
        raise ValueError("native account base currency differs from the forward portfolio")
    if (
        len(venue.cash) != 1
        or venue.cash[0].currency != portfolio.base_currency
        or venue.cash[0].amount != portfolio.initial_capital
    ):
        raise ValueError("native account cash differs from the forward portfolio capital")
    if (portfolio.rebalance_policy is None) != (market_context.rebalance_plan is None):
        raise ValueError("forward market context must bind exactly the portfolio rebalance policy")
    required_instruments = {
        instrument_id
        for component in portfolio.components
        for instrument_id in component.instrument_ids
    }
    if not required_instruments.issubset(
        {item.instrument_id for item in market_context.instruments}
    ):
        raise ValueError("forward market context is missing a portfolio instrument")

    ordered_components = tuple(sorted(execution_plan.components.items()))
    primary_component_id, primary = ordered_components[0]
    bindings = tuple(
        NautilusComponentStrategyBinding(
            component_id=component_id,
            strategy_fingerprint=component.strategy.fingerprint,
            strategy_source_digest=component.resolved_package.manifest.strategy.source_digest,
            strategy_manifest_fingerprint=component.resolved_package.manifest.fingerprint,
            entrypoint=component.package.entrypoint,
            parameters_digest=content_digest(component.binding.parameters),
            max_intents_per_event=max_intents_per_event,
        )
        for component_id, component in ordered_components
    )
    return NautilusEngineInput(
        trial_id=execution_plan.instance.instance_id,
        attempt_id=checkpoint_fingerprint,
        data_snapshot_fingerprint=snapshot.fingerprint,
        event_tape=NautilusEventTape(warmup_stream.tape.tape_fingerprint, ()),
        instruments=market_context.instruments,
        venue=venue,
        portfolio=portfolio,
        strategy_source_digest=primary.resolved_package.manifest.strategy.source_digest,
        strategy_manifest_fingerprint=primary.resolved_package.manifest.fingerprint,
        entrypoint=primary.package.entrypoint,
        parameters=primary.binding.parameters,
        random_seed=primary.binding.random_seed,
        strategy_bindings=bindings,
        rebalance_plan=market_context.rebalance_plan,
    )


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


def create_authenticated_forward_worker_handler_factory(
    persistence: PostgresStrategyLabV2Persistence,
    package_resolver: StrategyPackageArtifactResolver,
    store: LocalArtifactStore,
    *,
    snapshot_resolver_factory: Callable[[Any], AuthenticatedFrozenEventTapeResolver],
    frozen_payload_reader: FrozenForwardPayloadReader,
    warmup_payload_reader: ForwardWarmupPayloadReader,
    processed_prefix_resolver_factory: Callable[[Any], ForwardProcessedPrefixResolver],
    market_context_resolver_factory: Callable[[Any], ForwardNautilusMarketContextResolver],
    runtime_profile: RuntimeIsolationProfile,
    image_name: str,
    expected_version: str,
    output_path_resolver: Callable[[Any, str, str], str | os.PathLike[str]],
) -> OwnerForwardHandlerFactory:
    """Compose an owner-isolated handler with its exact sandbox plan factory.

    Platform-owned canonical readers and market metadata remain injected. This
    factory binds their authenticated owner once, then uses the same exact plan
    resolver for initial process start and checkpoint replacement.
    """

    if not isinstance(persistence, PostgresStrategyLabV2Persistence):
        raise TypeError("persistence must use PostgresStrategyLabV2Persistence")
    if not isinstance(package_resolver, StrategyPackageArtifactResolver):
        raise TypeError("package_resolver must use StrategyPackageArtifactResolver")
    if not isinstance(store, LocalArtifactStore):
        raise TypeError("store must use LocalArtifactStore")
    if not callable(snapshot_resolver_factory):
        raise TypeError("snapshot_resolver_factory must bind a snapshot resolver per owner")
    if not callable(getattr(frozen_payload_reader, "read_frozen_payloads", None)):
        raise TypeError("frozen_payload_reader must expose read_frozen_payloads")
    if not callable(getattr(warmup_payload_reader, "read_warmup_payloads", None)):
        raise TypeError("warmup_payload_reader must expose read_warmup_payloads")
    if not callable(processed_prefix_resolver_factory):
        raise TypeError("processed_prefix_resolver_factory must bind a resolver per owner")
    if not callable(market_context_resolver_factory):
        raise TypeError("market_context_resolver_factory must bind a resolver per owner")
    if not isinstance(runtime_profile, RuntimeIsolationProfile):
        raise TypeError("runtime_profile must use RuntimeIsolationProfile")
    if not isinstance(image_name, str) or not image_name.strip():
        raise ValueError("image_name must not be empty")
    if not isinstance(expected_version, str) or not expected_version.strip():
        raise ValueError("expected_version must not be empty")
    if not callable(output_path_resolver):
        raise TypeError("output_path_resolver must be callable")

    def build_for_owner(
        principal: str,
        delivery_factory: NautilusForwardDeliveryCallbackFactory,
        runtime_input_resolver: ForwardRuntimeInputResolver,
    ) -> NautilusForwardSessionEventHandler:
        snapshot_resolver = snapshot_resolver_factory(principal)
        if not isinstance(snapshot_resolver, AuthenticatedFrozenEventTapeResolver):
            raise TypeError("snapshot resolver factory returned an invalid owner resolver")
        if snapshot_resolver.principal != principal:
            raise ValueError("snapshot resolver factory returned another owner's resolver")
        processed_prefix_resolver = processed_prefix_resolver_factory(principal)
        market_context_resolver = market_context_resolver_factory(principal)
        input_resolver = AuthenticatedForwardSandboxPlanInputResolver(
            runtime_input_resolver,
            snapshot_resolver,
            warmup_payload_reader,
            processed_prefix_resolver,
            market_context_resolver,
            principal=principal,
            runtime_profile=runtime_profile,
            expected_version=expected_version,
        )
        sandbox_plan_factory = AuthenticatedForwardSandboxPlanFactory(
            store,
            input_resolver,
            principal=principal,
            image_name=image_name,
            output_path_resolver=lambda instance_id, checkpoint_fingerprint: (
                output_path_resolver(principal, instance_id, checkpoint_fingerprint)
            ),
        )
        process_factory = HardenedNautilusForwardSessionProcessFactory(sandbox_plan_factory)
        return create_authenticated_forward_session_event_handler(
            persistence,
            delivery_factory,
            runtime_input_resolver,
            process_factory,
            snapshot_window_resolver=snapshot_resolver,
            frozen_payload_reader=frozen_payload_reader,
            processed_prefix_resolver=processed_prefix_resolver,
            principal=principal,
        )

    return build_for_owner


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
    worker_profile: WorkerProfile,
) -> ForwardWorkerCallbacks:
    """Build the production worker callbacks over authenticated persistence.

    The dispatch materializer obtains owner identity from the PostgreSQL row;
    this callback set then routes to that owner's isolated handler/runtime.
    Market payload resolution remains an explicit platform-owned adapter.
    """

    if not isinstance(persistence, PostgresStrategyLabV2Persistence):
        raise TypeError("persistence must use PostgresStrategyLabV2Persistence")
    if (
        not isinstance(worker_profile, WorkerProfile)
        or worker_profile.kind is not WorkerKind.FORWARD
    ):
        raise TypeError("worker_profile must be a FORWARD WorkerProfile")
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
        authorization_resolver=DurableForwardWorkerAuthorizationResolver(
            persistence.worker_state,
            profile=worker_profile,
        ),
        close=owner_handler.close,
    )


__all__ = [
    "AuthenticatedForwardDeliveryContextResolver",
    "AuthenticatedForwardSandboxPlanInputResolver",
    "AuthenticatedForwardWorkerRuntimeInputResolver",
    "AuthenticatedForwardSandboxPlanFactory",
    "ForwardNautilusMarketContext",
    "ForwardNautilusMarketContextResolver",
    "ForwardRuntimeInputResolver",
    "ForwardSandboxPlanInputResolver",
    "ForwardSandboxPlanInputs",
    "ForwardWarmupPayloadReader",
    "build_forward_tape_manifest",
    "MaterializedForwardRuntimeInputArtifacts",
    "MaterializedForwardSandboxPlan",
    "OwnerForwardHandlerFactory",
    "OwnerScopedForwardEventHandler",
    "ResolvedForwardWorkerRuntimeInputs",
    "create_authenticated_forward_worker_runtime_input_resolver",
    "materialize_authenticated_forward_runtime_bundle",
    "materialize_authenticated_forward_sandbox_plan",
    "forward_runtime_attempt_id",
    "create_authenticated_forward_context_history_resolver",
    "create_authenticated_forward_delivery_context_resolver",
    "create_authenticated_forward_session_event_handler",
    "create_authenticated_forward_worker_handler_factory",
    "create_forward_worker_callbacks",
]
