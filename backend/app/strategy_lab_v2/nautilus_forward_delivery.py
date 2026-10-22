"""Bind durable forward dispatch identities to Nautilus-native inputs."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Protocol

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_corrections import CounterfactualReplayPlan
from app.strategy_lab_v2.forward_worker_handoff import ForwardEventWorkItem
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusForwardDeliveryBinding,
    NautilusForwardEventEnvelope,
    materialize_nautilus_forward_event,
    materialize_nautilus_forward_tape,
)
from app.strategy_lab_v2.nautilus_forward_input import (
    NautilusForwardDeliveryInput,
    VerifiedForwardMarketPayload,
)
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.sdk import MarketEvent

ForwardMarketPayloadResolution = (
    VerifiedForwardMarketPayload | Awaitable[VerifiedForwardMarketPayload]
)


class VerifiedForwardMarketPayloadResolver(Protocol):
    """Resolve canonical content only after verifying its local source bytes."""

    def __call__(
        self, *, instance_id: str, event_fingerprint: str
    ) -> ForwardMarketPayloadResolution: ...


class NautilusForwardDeliveryCallbackFactory:
    """Authenticate one Redis delivery and build its exact one-event native input."""

    def __init__(
        self,
        payload_resolver: VerifiedForwardMarketPayloadResolver,
        *,
        event_type_by_dependency: Mapping[str, str],
    ) -> None:
        if not callable(payload_resolver):
            raise TypeError("payload_resolver must be callable")
        if not isinstance(event_type_by_dependency, Mapping) or not event_type_by_dependency:
            raise TypeError("event_type_by_dependency must be a non-empty mapping")
        event_types: dict[str, str] = {}
        for dependency_id, event_type in event_type_by_dependency.items():
            if not isinstance(dependency_id, str) or not dependency_id.strip():
                raise ValueError("event type dependency ids must be non-empty strings")
            if not isinstance(event_type, str) or not event_type.strip():
                raise ValueError("event types must be non-empty strings")
            event_types[dependency_id] = event_type
        self._payload_resolver = payload_resolver
        self._event_type_by_dependency = event_types

    async def __call__(
        self,
        entry: RedisStreamEntry,
        work_item: ForwardEventWorkItem,
    ) -> NautilusForwardDeliveryInput:
        binding = materialize_nautilus_forward_delivery_binding(entry, work_item)
        if binding.admission_decision != "enqueue":
            raise ValueError("only accepted non-correction dispatches enter the live callback")
        resolved = self._payload_resolver(
            instance_id=binding.instance_id,
            event_fingerprint=binding.event_fingerprint,
        )
        payload = await resolved if inspect.isawaitable(resolved) else resolved
        if not isinstance(payload, VerifiedForwardMarketPayload):
            raise TypeError("forward market payload resolver returned an invalid payload")
        if content_digest(payload.canonical_event) != binding.event_fingerprint:
            raise ValueError("resolved canonical event does not match the accepted dispatch")
        event_type = self._event_type_by_dependency.get(payload.market_event.dependency_id)
        if event_type is None:
            raise ValueError("resolved event dependency has no declared Nautilus event type")
        tape = materialize_nautilus_forward_tape(
            binding.instance_id,
            (payload.canonical_event,),
            (payload.market_event,),
            event_type_by_dependency={payload.market_event.dependency_id: event_type},
            delivery_bindings=(binding,),
        )
        return NautilusForwardDeliveryInput(
            binding,
            tape,
            payload.market_event,
            payload.verified_source_digest,
        )


def create_nautilus_forward_delivery_callback_factory(
    payload_resolver: VerifiedForwardMarketPayloadResolver,
    *,
    event_type_by_dependency: Mapping[str, str],
) -> NautilusForwardDeliveryCallbackFactory:
    """Compose the host-owned event resolver with authenticated delivery checks."""

    return NautilusForwardDeliveryCallbackFactory(
        payload_resolver,
        event_type_by_dependency=event_type_by_dependency,
    )


@dataclass(frozen=True, slots=True)
class NautilusForwardCorrectionReplayInput:
    """A correction event bound only to its immutable counterfactual replay."""

    delivery_binding: NautilusForwardDeliveryBinding
    replay_plan: CounterfactualReplayPlan
    canonical_event: CanonicalForwardEvent
    event: NautilusForwardEventEnvelope

    def __post_init__(self) -> None:
        if not isinstance(self.delivery_binding, NautilusForwardDeliveryBinding):
            raise TypeError("delivery_binding must be a NautilusForwardDeliveryBinding")
        if not isinstance(self.replay_plan, CounterfactualReplayPlan):
            raise TypeError("replay_plan must be a CounterfactualReplayPlan")
        if not isinstance(self.canonical_event, CanonicalForwardEvent):
            raise TypeError("canonical_event must be a CanonicalForwardEvent")
        if not isinstance(self.event, NautilusForwardEventEnvelope):
            raise TypeError("event must be a NautilusForwardEventEnvelope")
        binding = self.delivery_binding
        plan = self.replay_plan
        canonical = self.canonical_event
        if binding.admission_decision != "correction_enqueue":
            raise ValueError("counterfactual replay input requires a correction dispatch")
        if binding.replay_plan_fingerprint != plan.fingerprint:
            raise ValueError("correction dispatch does not match the replay plan")
        if binding.instance_id != plan.instance_id:
            raise ValueError("correction replay instance does not match the dispatch")
        if binding.event_fingerprint != content_digest(canonical):
            raise ValueError("correction event does not match the dispatch fingerprint")
        if binding.pre_event_checkpoint_fingerprint != plan.base_checkpoint_fingerprint:
            raise ValueError("correction replay does not match its admission checkpoint")
        if binding.warmup_receipt_fingerprint != plan.warmup_receipt_fingerprint:
            raise ValueError("correction replay does not match its warm-up receipt")
        if canonical.event_id != plan.correction_event_id:
            raise ValueError("correction event identity does not match the replay plan")
        if canonical.correction_of != plan.original_event_id:
            raise ValueError("correction target does not match the replay plan")
        if self.event.canonical_event != canonical:
            raise ValueError("correction wire event does not match canonical metadata")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def materialize_nautilus_forward_delivery_binding(
    entry: RedisStreamEntry,
    work_item: ForwardEventWorkItem,
) -> NautilusForwardDeliveryBinding:
    """Authenticate Redis, PostgreSQL, warm-up, and pre-event checkpoint identity.

    Legacy dispatch rows do not carry the new admission evidence and therefore
    remain inspectable but cannot be upgraded into native forward inputs.
    Buffered and correction dispatches retain their explicit decisions; the
    ordinary live tape rejects them and routes them to their own handling path.
    """

    if not isinstance(entry, RedisStreamEntry):
        raise TypeError("entry must be a RedisStreamEntry")
    if not isinstance(work_item, ForwardEventWorkItem):
        raise TypeError("work_item must be a ForwardEventWorkItem")
    record = work_item.dispatch
    request = record.request
    if entry.request_fingerprint != request.fingerprint:
        raise ValueError("Redis request identity does not match the forward dispatch")
    if entry.message_id != request.fingerprint:
        raise ValueError("Redis message identity does not match the forward dispatch")
    if entry.attempt_id != record.instance_id or request.attempt_id != record.instance_id:
        raise ValueError("Redis attempt identity does not match the forward instance")
    if entry.payload_digest != request.payload_digest:
        raise ValueError("Redis payload identity does not match the forward dispatch")
    if work_item.payload.event_fingerprint != record.event_fingerprint:
        raise ValueError("forward event payload does not match the dispatch event")
    if work_item.payload.replay_plan_fingerprint != record.replay_plan_fingerprint:
        raise ValueError("forward replay payload does not match the dispatch replay plan")
    expected_payload_digest = content_digest(
        {
            "event_fingerprint": work_item.payload.event_fingerprint,
            "replay_plan_fingerprint": work_item.payload.replay_plan_fingerprint,
        }
    )
    if expected_payload_digest != request.payload_digest:
        raise ValueError("forward event payload fingerprint does not match the dispatch")
    if (
        record.pre_event_checkpoint_fingerprint is None
        or record.warmup_receipt_fingerprint is None
        or record.admission_decision is None
    ):
        raise ValueError("forward dispatch lacks persisted admission checkpoint evidence")

    return NautilusForwardDeliveryBinding(
        instance_id=record.instance_id,
        event_fingerprint=record.event_fingerprint,
        redis_stream_id=entry.stream_id,
        redis_entry_fingerprint=entry.fingerprint,
        dispatch_record_fingerprint=record.fingerprint,
        request_fingerprint=request.fingerprint,
        pre_event_checkpoint_fingerprint=record.pre_event_checkpoint_fingerprint,
        warmup_receipt_fingerprint=record.warmup_receipt_fingerprint,
        admission_decision=record.admission_decision,
        replay_plan_fingerprint=record.replay_plan_fingerprint,
    )


def materialize_nautilus_forward_correction_replay(
    entry: RedisStreamEntry,
    work_item: ForwardEventWorkItem,
    replay_plan: CounterfactualReplayPlan,
    canonical_event: CanonicalForwardEvent,
    market_event: MarketEvent,
    *,
    event_type: str,
) -> NautilusForwardCorrectionReplayInput:
    """Bind a corrected market event to its separate replay, never the live tape."""

    binding = materialize_nautilus_forward_delivery_binding(entry, work_item)
    envelope = materialize_nautilus_forward_event(
        canonical_event,
        market_event,
        event_type=event_type,
    )
    return NautilusForwardCorrectionReplayInput(
        binding,
        replay_plan,
        canonical_event,
        envelope,
    )


__all__ = [
    "NautilusForwardDeliveryCallbackFactory",
    "NautilusForwardDeliveryInput",
    "NautilusForwardCorrectionReplayInput",
    "VerifiedForwardMarketPayload",
    "VerifiedForwardMarketPayloadResolver",
    "create_nautilus_forward_delivery_callback_factory",
    "materialize_nautilus_forward_correction_replay",
    "materialize_nautilus_forward_delivery_binding",
]
