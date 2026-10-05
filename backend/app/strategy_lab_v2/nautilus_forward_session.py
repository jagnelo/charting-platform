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
from dataclasses import dataclass
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.forward_account_worker import (
    ForwardAccountEventBinding,
    ForwardAccountStore,
    ForwardAccountWorkerHandler,
)
from app.strategy_lab_v2.forward_context import (
    ForwardStrategyContextHistory,
    ForwardStrategyContextPreparation,
    ForwardStrategyContextWindow,
)
from app.strategy_lab_v2.forward_worker_handoff import ForwardEventWorkItem
from app.strategy_lab_v2.nautilus_forward_delivery import (
    NautilusForwardDeliveryCallbackFactory,
    NautilusForwardDeliveryInput,
)
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.sdk import StrategySdkManifest
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

    @classmethod
    def replay_verified_history(
        cls,
        history: ForwardStrategyContextHistory,
        manifest: StrategySdkManifest,
        *,
        parameters: Mapping[str, Any],
        random_seed: int,
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
        )


ForwardContextWindowResolution = (
    ResolvedForwardContextWindow | Awaitable[ResolvedForwardContextWindow]
)


class ForwardContextWindowResolver(Protocol):
    """Rehydrate a window from the delivery's exact warm-up/checkpoint pair."""

    def __call__(
        self, delivery: NautilusForwardDeliveryInput
    ) -> ForwardContextWindowResolution: ...


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
            preparation = window.prepare_delivery(delivery)
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

        account_handler = ForwardAccountWorkerHandler(
            self._account_store,
            principal=self._principal,
            event_resolver=lambda _entry, _item: execution.account_event_binding,
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
    "ForwardContextWindowResolver",
    "NautilusForwardExecutionResult",
    "NautilusForwardSessionEventHandler",
    "NautilusForwardSessionRuntime",
    "ResolvedForwardContextWindow",
]
