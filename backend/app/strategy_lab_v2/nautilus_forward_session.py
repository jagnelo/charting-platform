"""Order authenticated forward events through native execution and durable ACK.

This host-owned coordinator contains no Nautilus imports. A persistent isolated
runtime processes each accepted input idempotently, returns typed native account
effects, and can reconstruct the pre-event runtime from a durable checkpoint.
The coordinator persists those effects before committing its rolling SDK context
and before allowing the Redis worker to acknowledge the event.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.contracts import ForwardInstance, ForwardState
from app.strategy_lab_v2.forward_account import ForwardAccountState, ForwardRuntimeExecutionReceipt
from app.strategy_lab_v2.forward_account_worker import (
    ForwardAccountEventBinding,
    ForwardAccountStore,
    ForwardAccountWorkerHandler,
)
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState
from app.strategy_lab_v2.forward_context import (
    ForwardStrategyContextHistory,
    ForwardStrategyContextPreparation,
    ForwardStrategyContextWindow,
)
from app.strategy_lab_v2.forward_execution_plan_resolution import ResolvedForwardExecutionPlan
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt
from app.strategy_lab_v2.forward_worker_handoff import ForwardEventWorkItem
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_forward_delivery import (
    NautilusForwardDeliveryCallbackFactory,
    NautilusForwardDeliveryInput,
)
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.sdk import PositionSnapshot, StrategySdkManifest
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision, WorkerHandleResult


@dataclass(frozen=True, slots=True)
class NautilusForwardExecutionResult:
    """Native effects tied to the exact accepted delivery and SDK context."""

    delivery_binding_fingerprint: str
    context_preparation_fingerprint: str
    pre_event_checkpoint_fingerprint: str
    runtime_session_fingerprint: str
    native_output_fingerprint: str
    account_event_binding: ForwardAccountEventBinding

    def __post_init__(self) -> None:
        for name in (
            "delivery_binding_fingerprint",
            "context_preparation_fingerprint",
            "pre_event_checkpoint_fingerprint",
            "runtime_session_fingerprint",
            "native_output_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.account_event_binding, ForwardAccountEventBinding):
            raise TypeError("account_event_binding must use ForwardAccountEventBinding")
        if self.native_output_fingerprint != self.account_event_binding.fingerprint:
            raise ValueError("native output fingerprint differs from its typed account effects")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


ForwardExecutionResolution = (
    NautilusForwardExecutionResult | Awaitable[NautilusForwardExecutionResult]
)


class NautilusForwardSessionRuntime(Protocol):
    """One isolated, persistent engine session with deterministic recovery.

    ``execute`` must be idempotent by delivery-binding fingerprint. If its
    process restarts, it reconstructs the strategy and native account by
    replaying the immutable warm-up and every durably committed forward event
    up to the supplied pre-event checkpoint. ``restore`` must leave the same
    instance at that exact checkpoint before later input is accepted.
    """

    def execute(
        self,
        delivery: NautilusForwardDeliveryInput,
        preparation: ForwardStrategyContextPreparation,
    ) -> ForwardExecutionResolution: ...

    def restore(
        self, *, instance_id: str, checkpoint_fingerprint: str
    ) -> Awaitable[None] | None: ...


@dataclass(frozen=True, slots=True)
class ResolvedForwardContextWindow:
    """A replayed component context window at one exact durable checkpoint."""

    window: ForwardStrategyContextWindow
    pre_event_checkpoint_fingerprint: str
    warmup_receipt_fingerprint: str
    positions: Mapping[str, PositionSnapshot] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.window, ForwardStrategyContextWindow):
            raise TypeError("window must use ForwardStrategyContextWindow")
        require_sha256_digest(
            self.pre_event_checkpoint_fingerprint,
            field_name="pre_event_checkpoint_fingerprint",
        )
        require_sha256_digest(
            self.warmup_receipt_fingerprint,
            field_name="warmup_receipt_fingerprint",
        )
        if not isinstance(self.positions, Mapping):
            raise TypeError("positions must be a mapping")
        positions = dict(self.positions)
        if any(not isinstance(position, PositionSnapshot) for position in positions.values()):
            raise TypeError("positions must contain PositionSnapshot values")
        if any(
            instrument_id != position.instrument_id for instrument_id, position in positions.items()
        ):
            raise ValueError("position keys must match their instrument ids")
        object.__setattr__(self, "positions", MappingProxyType(dict(sorted(positions.items()))))

    @classmethod
    def replay_verified_history(
        cls,
        history: ForwardStrategyContextHistory,
        manifest: StrategySdkManifest,
        *,
        parameters: Mapping[str, Any],
        random_seed: int,
        positions: Mapping[str, PositionSnapshot] | None = None,
    ) -> ResolvedForwardContextWindow:
        """Resolve one window from an authenticated durable event prefix."""

        if not isinstance(history, ForwardStrategyContextHistory):
            raise TypeError("history must use ForwardStrategyContextHistory")
        window = ForwardStrategyContextWindow.replay_verified_history(
            history,
            manifest,
            parameters=parameters,
            random_seed=random_seed,
            expected_pre_event_checkpoint_fingerprint=(history.pre_event_checkpoint_fingerprint),
            expected_warmup_receipt_fingerprint=history.warmup_receipt_fingerprint,
        )
        return cls(
            window,
            history.pre_event_checkpoint_fingerprint,
            history.warmup_receipt_fingerprint,
            {} if positions is None else positions,
        )


ForwardContextWindowResolution = (
    ResolvedForwardContextWindow | Awaitable[ResolvedForwardContextWindow]
)


class ForwardContextWindowResolver(Protocol):
    """Rehydrate a window from the delivery's exact warm-up/checkpoint pair."""

    def __call__(
        self, delivery: NautilusForwardDeliveryInput
    ) -> ForwardContextWindowResolution: ...


@dataclass(frozen=True, slots=True)
class ForwardStrategyContextRecipe:
    """Immutable portfolio-bound strategy inputs for one forward component."""

    portfolio_fingerprint: str
    component_id: str
    manifest: StrategySdkManifest
    parameters: Mapping[str, Any]
    random_seed: int

    def __post_init__(self) -> None:
        require_sha256_digest(self.portfolio_fingerprint, field_name="portfolio_fingerprint")
        if not isinstance(self.component_id, str) or not self.component_id.strip():
            raise ValueError("component_id must not be empty")
        if not isinstance(self.manifest, StrategySdkManifest):
            raise TypeError("manifest must use StrategySdkManifest")
        if not isinstance(self.parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        if not isinstance(self.random_seed, int) or isinstance(self.random_seed, bool):
            raise TypeError("random_seed must be an integer")
        frozen = freeze_json(dict(self.parameters))
        if not isinstance(frozen, Mapping):
            raise TypeError("parameters must freeze to a mapping")
        object.__setattr__(self, "parameters", frozen)


class ResolvedForwardExecutionPlanRecipeResolver:
    """Expose one already-authenticated plan component to the SDK context path.

    Resolve the whole execution plan once when the isolated instance session is
    prepared, then construct one resolver per component. Event processing only
    reads this immutable in-memory result; it does not repeat owner-scoped DB or
    artifact I/O for every market event.
    """

    def __init__(
        self,
        execution_plan: ResolvedForwardExecutionPlan,
        *,
        component_id: str,
        principal: Any,
    ) -> None:
        if not isinstance(execution_plan, ResolvedForwardExecutionPlan):
            raise TypeError("execution_plan must use ResolvedForwardExecutionPlan")
        if not isinstance(component_id, str) or not component_id.strip():
            raise ValueError("component_id must not be empty")
        if component_id not in execution_plan.components:
            raise ValueError("component_id is not present in the resolved forward plan")
        self._execution_plan = execution_plan
        self._component_id = component_id
        self._principal = principal

    def __call__(
        self, *, principal: Any, instance: ForwardInstance
    ) -> ForwardStrategyContextRecipe:
        if principal != self._principal:
            raise ValueError("forward execution recipe belongs to another principal")
        if not isinstance(instance, ForwardInstance):
            raise TypeError("instance must use ForwardInstance")
        if instance != self._execution_plan.instance:
            raise ValueError("forward execution recipe belongs to another instance revision")
        component = self._execution_plan.components[self._component_id]
        return ForwardStrategyContextRecipe(
            portfolio_fingerprint=self._execution_plan.portfolio.fingerprint,
            component_id=self._component_id,
            manifest=component.resolved_package.manifest,
            parameters=component.binding.parameters,
            random_seed=component.binding.random_seed,
        )


class ForwardContextAdmissionStore(Protocol):
    """Load authenticated forward admission at one immutable checkpoint."""

    async def load_state_at_checkpoint(
        self,
        *,
        principal: Any,
        instance_id: str,
        checkpoint_fingerprint: str,
    ) -> ForwardLiveAdmissionState | None: ...

    async def load_warmup_receipt(
        self, *, principal: Any, instance_id: str
    ) -> ForwardWarmupReceipt | None: ...


class ForwardContextAccountHistoryStore(Protocol):
    """Replay native account positions at the same admission checkpoint."""

    async def load_at_checkpoint(
        self, *, principal: Any, admission_state: ForwardLiveAdmissionState
    ) -> ForwardAccountState | None: ...


class ForwardContextRecipeResolver(Protocol):
    """Resolve a component recipe from the immutable instance portfolio."""

    def __call__(
        self, *, principal: Any, instance: ForwardInstance
    ) -> ForwardStrategyContextRecipe | Awaitable[ForwardStrategyContextRecipe]: ...


class ForwardVerifiedHistoryResolver(Protocol):
    """Load bounded verified history from frozen warm-up and canonical event storage.

    Implementations read the platform-owned immutable snapshot and canonical
    forward event sources. They must not fetch data from a provider or accept
    history beyond the supplied pre-event admission checkpoint.
    """

    def __call__(
        self,
        *,
        principal: Any,
        instance: ForwardInstance,
        admission_state: ForwardLiveAdmissionState,
        warmup_receipt: ForwardWarmupReceipt,
        manifest: StrategySdkManifest,
        before_event: CanonicalForwardEvent,
    ) -> ForwardStrategyContextHistory | Awaitable[ForwardStrategyContextHistory]: ...


class AuthenticatedForwardContextWindowResolver:
    """Compose checkpointed account state and source-verified SDK history.

    The injected recipe/history resolvers are platform-owned artifact/data
    readers; this coordinator binds their results to the authenticated
    portfolio, warm-up receipt, and exact pre-event checkpoint before replay.
    """

    def __init__(
        self,
        admission_store: ForwardContextAdmissionStore,
        account_store: ForwardContextAccountHistoryStore,
        recipe_resolver: ForwardContextRecipeResolver,
        history_resolver: ForwardVerifiedHistoryResolver,
        *,
        principal: Any,
    ) -> None:
        if not callable(getattr(admission_store, "load_state_at_checkpoint", None)):
            raise TypeError("admission_store must load checkpoint-specific forward state")
        if not callable(getattr(admission_store, "load_warmup_receipt", None)):
            raise TypeError("admission_store must load the immutable warm-up receipt")
        if not callable(getattr(account_store, "load_at_checkpoint", None)):
            raise TypeError("account_store must load account history at a checkpoint")
        if not callable(recipe_resolver):
            raise TypeError("recipe_resolver must be callable")
        if not callable(history_resolver):
            raise TypeError("history_resolver must be callable")
        self._admission_store = admission_store
        self._account_store = account_store
        self._recipe_resolver = recipe_resolver
        self._history_resolver = history_resolver
        self._principal = principal

    async def __call__(
        self, delivery: NautilusForwardDeliveryInput
    ) -> ResolvedForwardContextWindow:
        if not isinstance(delivery, NautilusForwardDeliveryInput):
            raise TypeError("delivery must use NautilusForwardDeliveryInput")
        binding = delivery.delivery_binding
        if binding.admission_decision != "enqueue":
            raise ValueError("only accepted forward deliveries can resolve context")

        admission = await self._admission_store.load_state_at_checkpoint(
            principal=self._principal,
            instance_id=binding.instance_id,
            checkpoint_fingerprint=binding.pre_event_checkpoint_fingerprint,
        )
        if admission is None:
            raise ValueError("authenticated pre-event admission checkpoint is unavailable")
        if not isinstance(admission, ForwardLiveAdmissionState):
            raise TypeError("admission store returned an invalid checkpoint state")
        checkpoint = admission.checkpoint
        instance = checkpoint.instance
        if instance.instance_id != binding.instance_id:
            raise ValueError("pre-event checkpoint belongs to another forward instance")
        if checkpoint.fingerprint != binding.pre_event_checkpoint_fingerprint:
            raise ValueError("admission store returned a different pre-event checkpoint")
        if instance.state is not ForwardState.ACTIVE:
            raise ValueError("pre-event forward instance is not active")
        if admission.warmup_receipt_fingerprint != binding.warmup_receipt_fingerprint:
            raise ValueError("pre-event checkpoint belongs to a different warm-up receipt")
        receipt = await self._admission_store.load_warmup_receipt(
            principal=self._principal,
            instance_id=binding.instance_id,
        )
        if not isinstance(receipt, ForwardWarmupReceipt):
            raise ValueError("forward warm-up receipt is unavailable")
        if (
            receipt.fingerprint != binding.warmup_receipt_fingerprint
            or receipt.instance_id != instance.instance_id
            or receipt.warmup_snapshot_fingerprint != instance.warmup_snapshot_fingerprint
        ):
            raise ValueError("persisted warm-up receipt differs from the authenticated instance")

        current_event = delivery.tape.envelopes[0].canonical_event
        current_event_fingerprint = content_digest(current_event)
        if current_event_fingerprint != binding.event_fingerprint:
            raise ValueError("forward delivery event differs from its authenticated binding")
        seen_by_id = {item.event_id: item for item in admission.seen_events}
        if current_event.event_id in seen_by_id:
            raise ValueError("pre-event checkpoint already contains the delivered event")

        recipe_resolution = self._recipe_resolver(principal=self._principal, instance=instance)
        recipe = (
            await recipe_resolution if inspect.isawaitable(recipe_resolution) else recipe_resolution
        )
        if not isinstance(recipe, ForwardStrategyContextRecipe):
            raise TypeError("strategy recipe resolver returned an invalid recipe")
        if recipe.portfolio_fingerprint != instance.portfolio_fingerprint:
            raise ValueError("strategy recipe does not belong to the forward instance portfolio")

        history_resolution = self._history_resolver(
            principal=self._principal,
            instance=instance,
            admission_state=admission,
            warmup_receipt=receipt,
            manifest=recipe.manifest,
            before_event=current_event,
        )
        history = (
            await history_resolution
            if inspect.isawaitable(history_resolution)
            else history_resolution
        )
        if not isinstance(history, ForwardStrategyContextHistory):
            raise TypeError("verified history resolver returned an invalid history")
        if history.instance_id != instance.instance_id:
            raise ValueError("verified history belongs to another forward instance")
        if history.pre_event_checkpoint_fingerprint != checkpoint.fingerprint:
            raise ValueError("verified history does not match the authenticated checkpoint")
        if history.warmup_receipt_fingerprint != admission.warmup_receipt_fingerprint:
            raise ValueError("verified history does not match the active warm-up receipt")
        if history.manifest_fingerprint != recipe.manifest.fingerprint:
            raise ValueError("verified history does not match the resolved strategy manifest")
        if history.before_event_fingerprint != current_event_fingerprint:
            raise ValueError("verified history is not bound to the current event")
        if history.warmup_snapshot_fingerprint != instance.warmup_snapshot_fingerprint:
            raise ValueError("verified history does not identify the instance warm-up snapshot")
        if history.processed_prefix_fingerprint is None:
            raise ValueError("verified history is not bound to a processed-prefix receipt")
        if receipt.final_event_id is None:
            if history.warmup_tape_fingerprint is not None or history.warmup_event_ids:
                raise ValueError("empty warm-up receipt cannot include frozen history")
        elif history.warmup_tape_fingerprint is None:
            raise ValueError("verified history is missing its frozen warm-up tape identity")
        _validate_history_prefix(history, admission, receipt, current_event)

        account_resolution = await self._account_store.load_at_checkpoint(
            principal=self._principal,
            admission_state=admission,
        )
        if account_resolution is None:
            raise ValueError("native account history is unavailable at the pre-event checkpoint")
        if not isinstance(account_resolution, ForwardAccountState):
            raise TypeError("account history store returned an invalid state")
        if account_resolution.instance_id != instance.instance_id:
            raise ValueError("account history belongs to another forward instance")
        positions = {item.instrument_id: item for item in account_resolution.positions}

        return ResolvedForwardContextWindow.replay_verified_history(
            history,
            recipe.manifest,
            parameters=recipe.parameters,
            random_seed=recipe.random_seed,
            positions=positions,
        )


def _validate_history_prefix(
    history: ForwardStrategyContextHistory,
    admission: ForwardLiveAdmissionState,
    receipt: ForwardWarmupReceipt,
    current_event: CanonicalForwardEvent,
) -> None:
    """Bind live history to the processed prefix and warm-up snapshot boundary."""

    seen_by_id = {item.event_id: item for item in admission.seen_events}
    processed_ids = admission.checkpoint.processed_event_ids
    current_key = (current_event.event_time, current_event.sequence)
    for payload in history.events:
        canonical = payload.canonical_event
        seen = seen_by_id.get(canonical.event_id)
        is_frozen_warmup_event = canonical.event_id in history.warmup_event_ids
        if is_frozen_warmup_event:
            # The immutable warm-up artifact contains historical rows that are
            # intentionally not copied into the live admission event journal.
            if receipt.final_event_id is None or canonical.sequence > receipt.final_event_sequence:
                raise ValueError("warm-up history extends beyond its receipt cursor")
            if seen is not None and (
                seen.event_fingerprint != content_digest(canonical)
                or seen.sequence != canonical.sequence
            ):
                raise ValueError("warm-up history differs from checkpoint admission evidence")
        elif canonical.event_id not in processed_ids or seen is None:
            raise ValueError("context history contains an event outside the processed prefix")
        elif (
            seen.event_fingerprint != content_digest(canonical)
            or seen.sequence != canonical.sequence
        ):
            raise ValueError("context history event differs from checkpoint admission evidence")
        if (
            canonical.event_id == receipt.final_event_id
            and content_digest(canonical) != receipt.final_event_fingerprint
        ):
            raise ValueError("context history differs from the final warm-up event identity")
        if (canonical.event_time, canonical.sequence) >= current_key:
            raise ValueError("context history includes the current or a future event")


class NautilusForwardSessionEventHandler:
    """Execute, durably settle, then expose one Redis event for completion."""

    def __init__(
        self,
        delivery_factory: NautilusForwardDeliveryCallbackFactory,
        context_window_resolver: ForwardContextWindowResolver,
        runtime: NautilusForwardSessionRuntime,
        account_store: ForwardAccountStore,
        *,
        principal: object,
    ) -> None:
        if not callable(delivery_factory):
            raise TypeError("delivery_factory must be callable")
        if not callable(context_window_resolver):
            raise TypeError("context_window_resolver must be callable")
        if not callable(getattr(runtime, "execute", None)) or not callable(
            getattr(runtime, "restore", None)
        ):
            raise TypeError("runtime must expose execute and restore methods")
        if not callable(getattr(account_store, "apply", None)):
            raise TypeError("account_store must expose an apply method")
        self._delivery_factory = delivery_factory
        self._context_window_resolver = context_window_resolver
        self._runtime = runtime
        self._account_store = account_store
        self._principal = principal

    async def __call__(
        self, entry: RedisStreamEntry, work_item: ForwardEventWorkItem
    ) -> WorkerHandleResult:
        if not isinstance(entry, RedisStreamEntry):
            raise TypeError("entry must be a RedisStreamEntry")
        if not isinstance(work_item, ForwardEventWorkItem):
            raise TypeError("work_item must be a ForwardEventWorkItem")
        admission = work_item.dispatch.admission_decision
        if admission == "correction_enqueue":
            return _reject(entry, "corrected events require the counterfactual replay path")
        if admission == "buffered":
            return _retry(entry, "buffered event is not yet admitted to the native forward session")
        if admission != "enqueue":
            return _reject(entry, "forward event has no accepted native admission")
        try:
            delivery_resolution = self._delivery_factory(entry, work_item)
            delivery = (
                await delivery_resolution
                if inspect.isawaitable(delivery_resolution)
                else delivery_resolution
            )
        except Exception as error:
            return _retry(entry, f"forward delivery preparation failed: {type(error).__name__}")
        if not isinstance(delivery, NautilusForwardDeliveryInput):
            return _reject(entry, "forward delivery factory returned an invalid input")

        try:
            # Rehydrate exactly the pre-event history carried by this
            # authenticated delivery, rather than blindly loading latest state.
            window_resolution = self._context_window_resolver(delivery)
            resolved_window = (
                await window_resolution
                if inspect.isawaitable(window_resolution)
                else window_resolution
            )
        except Exception as error:
            return _retry(entry, f"forward context window lookup failed: {type(error).__name__}")
        if not isinstance(resolved_window, ResolvedForwardContextWindow):
            return _reject(entry, "forward context resolver returned an invalid resolution")
        if (
            resolved_window.pre_event_checkpoint_fingerprint
            != delivery.delivery_binding.pre_event_checkpoint_fingerprint
            or resolved_window.warmup_receipt_fingerprint
            != delivery.delivery_binding.warmup_receipt_fingerprint
        ):
            return _retry(
                entry, "forward context window is not at the authenticated pre-event state"
            )
        window = resolved_window.window
        try:
            preparation = window.prepare_delivery(delivery, positions=resolved_window.positions)
        except (TypeError, ValueError) as error:
            return _reject(
                entry, f"forward strategy context rejected input: {type(error).__name__}"
            )

        try:
            execution_resolution = self._runtime.execute(delivery, preparation)
            execution = (
                await execution_resolution
                if inspect.isawaitable(execution_resolution)
                else execution_resolution
            )
        except Exception as error:
            recovered = await self._restore_pre_event(window, preparation)
            if recovered:
                return _retry(entry, f"native forward execution failed: {type(error).__name__}")
            return _retry(entry, "native forward execution and checkpoint recovery failed")
        if not isinstance(execution, NautilusForwardExecutionResult):
            recovered = await self._restore_pre_event(window, preparation)
            if recovered:
                return _reject(entry, "native forward runtime returned an invalid result")
            return _retry(entry, "native forward result invalid and checkpoint recovery failed")
        try:
            _validate_execution(delivery, preparation, execution)
        except (TypeError, ValueError):
            recovered = await self._restore_pre_event(window, preparation)
            if recovered:
                return _reject(entry, "native forward result does not match its accepted input")
            return _retry(entry, "native forward result mismatch and checkpoint recovery failed")

        canonical = delivery.tape.envelopes[0].canonical_event
        durable_receipt = ForwardRuntimeExecutionReceipt(
            instance_id=delivery.delivery_binding.instance_id,
            event_id=canonical.event_id,
            event_fingerprint=content_digest(canonical),
            delivery_binding_fingerprint=delivery.delivery_binding.fingerprint,
            context_preparation_fingerprint=preparation.fingerprint,
            pre_event_checkpoint_fingerprint=(
                delivery.delivery_binding.pre_event_checkpoint_fingerprint
            ),
            runtime_session_fingerprint=execution.runtime_session_fingerprint,
            native_output_fingerprint=execution.native_output_fingerprint,
        )
        output_binding = execution.account_event_binding
        durable_binding = ForwardAccountEventBinding(
            output_binding.canonical_event,
            output_binding.account_event,
            durable_receipt,
        )
        account_handler = ForwardAccountWorkerHandler(
            self._account_store,
            principal=self._principal,
            event_resolver=lambda _entry, _item: durable_binding,
        )
        try:
            settlement = await account_handler(entry, work_item)
        except Exception as error:
            recovered = await self._restore_pre_event(window, preparation)
            if recovered:
                return _retry(entry, f"native forward settlement failed: {type(error).__name__}")
            return _retry(entry, "native forward settlement and checkpoint recovery failed")
        if settlement.decision is not WorkerHandleDecision.COMPLETE:
            recovered = await self._restore_pre_event(window, preparation)
            if not recovered:
                return _retry(entry, "forward event not settled and checkpoint recovery failed")
            return settlement

        try:
            window.commit(preparation)
        except (TypeError, ValueError):
            # The account output is already durable. Leave this event pending
            # for idempotent replay rather than acknowledging an uncommitted
            # context window.
            return _retry(entry, "durable forward output awaits context-window commit")
        assert settlement.receipt_digest is not None
        return WorkerHandleResult(
            entry.fingerprint,
            WorkerHandleDecision.COMPLETE,
            content_digest(
                {
                    "kind": "nautilus-forward-session-settlement",
                    "entry_fingerprint": entry.fingerprint,
                    "work_item_fingerprint": work_item.fingerprint,
                    "delivery_fingerprint": delivery.delivery_binding.fingerprint,
                    "context_preparation_fingerprint": preparation.fingerprint,
                    "runtime_session_fingerprint": execution.runtime_session_fingerprint,
                    "native_output_fingerprint": execution.native_output_fingerprint,
                    "execution_receipt_fingerprint": durable_receipt.fingerprint,
                    "account_settlement_receipt": settlement.receipt_digest,
                }
            ),
        )

    async def _restore_pre_event(
        self,
        window: ForwardStrategyContextWindow,
        preparation: ForwardStrategyContextPreparation,
    ) -> bool:
        checkpoint_fingerprint = preparation.pre_event_checkpoint_fingerprint
        if checkpoint_fingerprint is None:
            return False
        try:
            result = self._runtime.restore(
                instance_id=preparation.instance_id,
                checkpoint_fingerprint=checkpoint_fingerprint,
            )
            if inspect.isawaitable(result):
                await result
            window.discard(preparation)
        except Exception:
            return False
        return True


def _validate_execution(
    delivery: NautilusForwardDeliveryInput,
    preparation: ForwardStrategyContextPreparation,
    execution: NautilusForwardExecutionResult,
) -> None:
    binding = delivery.delivery_binding
    account_binding = execution.account_event_binding
    account_event = account_binding.account_event
    canonical = delivery.tape.envelopes[0].canonical_event
    if execution.delivery_binding_fingerprint != binding.fingerprint:
        raise ValueError("native execution references a different accepted delivery")
    if execution.context_preparation_fingerprint != preparation.fingerprint:
        raise ValueError("native execution references a different SDK context")
    if execution.pre_event_checkpoint_fingerprint != binding.pre_event_checkpoint_fingerprint:
        raise ValueError("native execution references a different pre-event checkpoint")
    if account_binding.canonical_event != canonical:
        raise ValueError("native account effects reference a different canonical event")
    if account_event.instance_id != binding.instance_id:
        raise ValueError("native account effects reference a different forward instance")


def _retry(entry: RedisStreamEntry, reason: str) -> WorkerHandleResult:
    return WorkerHandleResult(
        entry.fingerprint,
        WorkerHandleDecision.RETRY,
        rejection_reason=reason,
    )


def _reject(entry: RedisStreamEntry, reason: str) -> WorkerHandleResult:
    return WorkerHandleResult(
        entry.fingerprint,
        WorkerHandleDecision.REJECT,
        rejection_reason=reason,
    )


__all__ = [
    "AuthenticatedForwardContextWindowResolver",
    "ForwardContextAccountHistoryStore",
    "ForwardContextAdmissionStore",
    "ForwardContextRecipeResolver",
    "ForwardContextWindowResolver",
    "ForwardStrategyContextRecipe",
    "ForwardVerifiedHistoryResolver",
    "NautilusForwardExecutionResult",
    "NautilusForwardSessionEventHandler",
    "NautilusForwardSessionRuntime",
    "ResolvedForwardContextWindow",
    "ResolvedForwardExecutionPlanRecipeResolver",
]
