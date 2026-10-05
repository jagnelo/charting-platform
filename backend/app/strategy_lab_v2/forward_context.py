"""Build bounded, declared-input SDK contexts for forward event processing.

Forward contexts are assembled from source-verified frozen history plus the
newly admitted canonical event. The window deliberately contains no provider,
database, wall-clock, or Nautilus dependency; one instance is held per strategy
component by the isolated forward runtime.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest
from app.strategy_lab_v2.nautilus_event_adapter import NautilusForwardDeliveryBinding
from app.strategy_lab_v2.nautilus_forward_delivery import (
    NautilusForwardDeliveryInput,
    VerifiedForwardMarketPayload,
)
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    PositionSnapshot,
    StrategyContext,
    StrategySdkManifest,
    build_strategy_context,
)


@dataclass(frozen=True, slots=True)
class ForwardStrategyContextPreparation:
    """One context staged against a specific committed history window."""

    instance_id: str
    payload_fingerprint: str
    base_window_fingerprint: str
    next_window_fingerprint: str
    context: StrategyContext
    delivery_binding_fingerprint: str | None = None
    dispatch_fingerprint: str | None = None
    pre_event_checkpoint_fingerprint: str | None = None
    warmup_receipt_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, str) or not self.instance_id.strip():
            raise ValueError("instance_id must not be empty")
        for name in (
            "payload_fingerprint",
            "base_window_fingerprint",
            "next_window_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        binding_fields = (
            self.delivery_binding_fingerprint,
            self.dispatch_fingerprint,
            self.pre_event_checkpoint_fingerprint,
            self.warmup_receipt_fingerprint,
        )
        if any(value is not None for value in binding_fields):
            if any(value is None for value in binding_fields):
                raise ValueError("forward context dispatch binding fields must be complete")
            for name in (
                "delivery_binding_fingerprint",
                "dispatch_fingerprint",
                "pre_event_checkpoint_fingerprint",
                "warmup_receipt_fingerprint",
            ):
                require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.context, StrategyContext):
            raise TypeError("context must use StrategyContext")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ForwardPortfolioContextPreparation:
    """All component contexts staged for one event in a shared portfolio."""

    instance_id: str
    payload_fingerprint: str
    delivery_binding_fingerprint: str
    dispatch_fingerprint: str
    pre_event_checkpoint_fingerprint: str
    warmup_receipt_fingerprint: str
    component_preparations: Mapping[str, ForwardStrategyContextPreparation]

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, str) or not self.instance_id.strip():
            raise ValueError("instance_id must not be empty")
        for name in (
            "payload_fingerprint",
            "delivery_binding_fingerprint",
            "dispatch_fingerprint",
            "pre_event_checkpoint_fingerprint",
            "warmup_receipt_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.component_preparations, Mapping):
            raise TypeError("component_preparations must be a mapping")
        preparations = dict(self.component_preparations)
        if any(
            not isinstance(component_id, str) or not component_id.strip()
            for component_id in preparations
        ):
            raise ValueError("component preparation ids must be non-empty strings")
        for preparation in preparations.values():
            if not isinstance(preparation, ForwardStrategyContextPreparation):
                raise TypeError("portfolio contexts must contain strategy preparations")
            if (
                preparation.instance_id != self.instance_id
                or preparation.payload_fingerprint != self.payload_fingerprint
                or preparation.delivery_binding_fingerprint != self.delivery_binding_fingerprint
                or preparation.dispatch_fingerprint != self.dispatch_fingerprint
                or preparation.pre_event_checkpoint_fingerprint
                != self.pre_event_checkpoint_fingerprint
                or preparation.warmup_receipt_fingerprint != self.warmup_receipt_fingerprint
            ):
                raise ValueError("component context is not bound to the shared portfolio event")
        object.__setattr__(
            self,
            "component_preparations",
            MappingProxyType(dict(sorted(preparations.items()))),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ForwardStrategyContextHistory:
    """Bounded verified event window loaded at one durable pre-event checkpoint.

    The persistence resolver supplies only the last ``lookback + current``
    inputs for each dependency; strategy-local state and native account state
    are reconstructed separately by replaying their durable execution tape.
    """

    instance_id: str
    manifest_fingerprint: str
    pre_event_checkpoint_fingerprint: str
    warmup_receipt_fingerprint: str
    events: tuple[VerifiedForwardMarketPayload, ...]
    before_event_fingerprint: str | None = None
    warmup_snapshot_fingerprint: str | None = None
    warmup_tape_fingerprint: str | None = None
    warmup_source_artifact_digests: tuple[str, ...] = ()
    warmup_event_ids: frozenset[str] = frozenset()
    processed_prefix_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, str) or not self.instance_id.strip():
            raise ValueError("instance_id must not be empty")
        for name in (
            "manifest_fingerprint",
            "pre_event_checkpoint_fingerprint",
            "warmup_receipt_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        for name in (
            "before_event_fingerprint",
            "warmup_snapshot_fingerprint",
            "warmup_tape_fingerprint",
            "processed_prefix_fingerprint",
        ):
            value = getattr(self, name)
            if value is not None:
                require_sha256_digest(value, field_name=name)
        source_digests = tuple(self.warmup_source_artifact_digests)
        for digest in source_digests:
            require_sha256_digest(digest, field_name="warmup_source_artifact_digest")
        if source_digests != tuple(sorted(set(source_digests))):
            raise ValueError("warm-up source artifact digests must be unique and ordered")
        if self.warmup_tape_fingerprint is None and source_digests:
            raise ValueError("warm-up source artifacts require a tape fingerprint")
        warmup_event_ids = frozenset(self.warmup_event_ids)
        if any(
            not isinstance(event_id, str) or not event_id.strip() for event_id in warmup_event_ids
        ):
            raise ValueError("warm-up event ids must be non-empty strings")
        events = tuple(self.events)
        if any(not isinstance(item, VerifiedForwardMarketPayload) for item in events):
            raise TypeError("events must contain verified forward market payloads")
        event_ids = [item.canonical_event.event_id for item in events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("forward context history event ids must be unique")
        event_keys = [
            (item.canonical_event.event_time, item.canonical_event.sequence) for item in events
        ]
        if any(current <= previous for previous, current in zip(event_keys, event_keys[1:])):
            raise ValueError("forward context history must advance strictly by time and sequence")
        if not warmup_event_ids.issubset({item.canonical_event.event_id for item in events}):
            raise ValueError("warm-up event ids must be present in the context history")
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "warmup_source_artifact_digests", source_digests)
        object.__setattr__(self, "warmup_event_ids", warmup_event_ids)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ForwardStrategyContextWindow:
    """Maintain a deterministic rolling SDK history for one component."""

    def __init__(
        self,
        instance_id: str,
        manifest: StrategySdkManifest,
        *,
        parameters: Mapping[str, Any],
        random_seed: int,
    ) -> None:
        if not isinstance(instance_id, str) or not instance_id.strip():
            raise ValueError("instance_id must not be empty")
        if not isinstance(manifest, StrategySdkManifest):
            raise TypeError("manifest must use StrategySdkManifest")
        if not isinstance(parameters, Mapping):
            raise TypeError("parameters must be a mapping")
        if not isinstance(random_seed, int) or isinstance(random_seed, bool):
            raise TypeError("random_seed must be an integer")
        self._instance_id = instance_id
        self._manifest = manifest
        # Freeze and fingerprint the parameters at session construction. The
        # SDK context constructor makes the immutable public copy per event.
        frozen_parameters = freeze_json(parameters)
        if not isinstance(frozen_parameters, Mapping):
            raise TypeError("parameters must freeze to a mapping")
        self._parameters = frozen_parameters
        self._parameters_digest = content_digest(self._parameters)
        self._random_seed = random_seed
        self._dependencies = {item.dependency_id: item for item in manifest.data_dependencies}
        self._events: dict[str, deque[MarketEvent]] = {
            dependency_id: deque(maxlen=dependency.lookback_periods + 1)
            for dependency_id, dependency in self._dependencies.items()
        }
        self._pending: (
            tuple[
                ForwardStrategyContextPreparation,
                dict[str, deque[MarketEvent]],
                tuple[datetime, int],
            ]
            | None
        ) = None
        self._last_committed: ForwardStrategyContextPreparation | None = None
        self._last_event_key: tuple[datetime, int] | None = None

    @property
    def last_event_key(self) -> tuple[datetime, int] | None:
        return self._last_event_key

    @property
    def dependency_ids(self) -> frozenset[str]:
        """Declared input dependencies available to this component window."""

        return frozenset(self._dependencies)

    @property
    def window_fingerprint(self) -> str:
        """Fingerprint only the retained context window, not strategy state."""

        return content_digest(
            {
                "instance_id": self._instance_id,
                "manifest_fingerprint": self._manifest.fingerprint,
                "parameters_digest": self._parameters_digest,
                "random_seed": self._random_seed,
                "last_event_key": self._last_event_key,
                "events": {
                    dependency_id: tuple(events)
                    for dependency_id, events in sorted(self._events.items())
                },
            }
        )

    def prepare(
        self,
        payload: VerifiedForwardMarketPayload,
        *,
        instance_id: str,
        positions: Mapping[str, PositionSnapshot] | None = None,
        delivery_binding: NautilusForwardDeliveryBinding | None = None,
    ) -> ForwardStrategyContextPreparation:
        """Stage one no-lookahead context without advancing committed history.

        The caller commits only after the corresponding native outputs and
        account receipt are durable. Repeating the same pending input is
        idempotent; a different input cannot overtake an unsettled event.
        """

        if not isinstance(payload, VerifiedForwardMarketPayload):
            raise TypeError("payload must use VerifiedForwardMarketPayload")
        if instance_id != self._instance_id:
            raise ValueError("forward event belongs to a different instance")
        canonical = payload.canonical_event
        event = payload.market_event
        payload_fingerprint = payload.fingerprint
        if delivery_binding is not None:
            if not isinstance(delivery_binding, NautilusForwardDeliveryBinding):
                raise TypeError("delivery_binding must use NautilusForwardDeliveryBinding")
            if delivery_binding.admission_decision != "enqueue":
                raise ValueError("forward contexts require an accepted enqueue binding")
            if delivery_binding.instance_id != self._instance_id:
                raise ValueError("forward delivery belongs to a different context instance")
            if delivery_binding.event_fingerprint != content_digest(canonical):
                raise ValueError("forward delivery does not bind the resolved canonical event")
        if self._pending is not None:
            pending, _candidate_events, _event_key = self._pending
            if pending.payload_fingerprint == payload_fingerprint and _same_delivery_binding(
                pending, delivery_binding
            ):
                return pending
            raise ValueError("a forward context event is already awaiting settlement")
        if (
            self._last_committed is not None
            and self._last_committed.payload_fingerprint == payload_fingerprint
            and _same_delivery_binding(self._last_committed, delivery_binding)
        ):
            return self._last_committed
        dependency = self._dependencies.get(event.dependency_id)
        if dependency is None:
            raise ValueError("forward event dependency is not declared by the strategy")
        requirement = dependency.requirement
        if event.instrument_id != requirement.instrument_id:
            raise ValueError("forward event instrument differs from its declared dependency")
        if not requirement.start <= event.event_time < requirement.end:
            raise ValueError("forward event is outside its declared dependency interval")
        if set(event.values) != set(dependency.fields):
            raise ValueError("forward event fields differ from its declared dependency")

        event_key = (canonical.event_time, canonical.sequence)
        if self._last_event_key is not None and event_key <= self._last_event_key:
            raise ValueError("forward context events must advance strictly by time and sequence")

        candidate_events = {
            dependency_id: deque(
                events,
                maxlen=self._dependencies[dependency_id].lookback_periods + 1,
            )
            for dependency_id, events in self._events.items()
        }
        candidate_events[event.dependency_id].append(event)
        market_events = {
            dependency_id: tuple(
                prior for prior in events if (prior.event_time, prior.sequence) <= event_key
            )
            for dependency_id, events in candidate_events.items()
        }
        context = build_strategy_context(
            self._manifest,
            event_time=canonical.event_time,
            event_sequence=canonical.sequence,
            random_seed=self._random_seed,
            parameters=self._parameters,
            market_events=market_events,
            positions=positions,
        )
        # Guard against accidental mutation through an unconventional input
        # mapping; callers and every later context share the original params.
        if content_digest(context.parameters) != self._parameters_digest:
            raise ValueError("forward strategy parameters changed during context construction")
        preparation = ForwardStrategyContextPreparation(
            instance_id=self._instance_id,
            payload_fingerprint=payload_fingerprint,
            base_window_fingerprint=self.window_fingerprint,
            next_window_fingerprint=content_digest(
                {
                    "instance_id": self._instance_id,
                    "manifest_fingerprint": self._manifest.fingerprint,
                    "parameters_digest": self._parameters_digest,
                    "random_seed": self._random_seed,
                    "last_event_key": event_key,
                    "events": {
                        dependency_id: tuple(events)
                        for dependency_id, events in sorted(candidate_events.items())
                    },
                }
            ),
            context=context,
            delivery_binding_fingerprint=(
                None if delivery_binding is None else delivery_binding.fingerprint
            ),
            dispatch_fingerprint=(
                None if delivery_binding is None else delivery_binding.dispatch_record_fingerprint
            ),
            pre_event_checkpoint_fingerprint=(
                None
                if delivery_binding is None
                else delivery_binding.pre_event_checkpoint_fingerprint
            ),
            warmup_receipt_fingerprint=(
                None if delivery_binding is None else delivery_binding.warmup_receipt_fingerprint
            ),
        )
        self._pending = preparation, candidate_events, event_key
        return preparation

    def prepare_delivery(
        self,
        delivery: NautilusForwardDeliveryInput,
        *,
        positions: Mapping[str, PositionSnapshot] | None = None,
    ) -> ForwardStrategyContextPreparation:
        """Build a context directly from one authenticated Redis/DB delivery."""

        if not isinstance(delivery, NautilusForwardDeliveryInput):
            raise TypeError("delivery must use NautilusForwardDeliveryInput")
        binding = delivery.delivery_binding
        if binding.instance_id != self._instance_id:
            raise ValueError("forward delivery belongs to a different context instance")
        return self.prepare(
            delivery.verified_market_payload,
            instance_id=binding.instance_id,
            positions=positions,
            delivery_binding=binding,
        )

    def commit(self, preparation: ForwardStrategyContextPreparation) -> str:
        """Advance retained history after the event's durable settlement."""

        if not isinstance(preparation, ForwardStrategyContextPreparation):
            raise TypeError("preparation must use ForwardStrategyContextPreparation")
        if preparation.instance_id != self._instance_id:
            raise ValueError("forward context preparation belongs to a different instance")
        if self._last_committed is not None and preparation == self._last_committed:
            if self.window_fingerprint != preparation.next_window_fingerprint:
                raise ValueError("forward context preparation is no longer the latest commit")
            return self.window_fingerprint
        if self._pending is None or preparation != self._pending[0]:
            raise ValueError("forward context preparation is not the pending event")
        if preparation.base_window_fingerprint != self.window_fingerprint:
            raise ValueError("forward context preparation was built from a stale history window")
        _pending, candidate_events, event_key = self._pending
        next_fingerprint = content_digest(
            {
                "instance_id": self._instance_id,
                "manifest_fingerprint": self._manifest.fingerprint,
                "parameters_digest": self._parameters_digest,
                "random_seed": self._random_seed,
                "last_event_key": event_key,
                "events": {
                    dependency_id: tuple(events)
                    for dependency_id, events in sorted(candidate_events.items())
                },
            }
        )
        if next_fingerprint != preparation.next_window_fingerprint:
            raise ValueError("prepared forward context history changed before commit")
        self._events = candidate_events
        self._last_event_key = event_key
        self._last_committed = preparation
        self._pending = None
        return self.window_fingerprint

    def discard(self, preparation: ForwardStrategyContextPreparation) -> None:
        """Clear an unsettled preparation after the runtime has been reset."""

        if not isinstance(preparation, ForwardStrategyContextPreparation):
            raise TypeError("preparation must use ForwardStrategyContextPreparation")
        if self._last_committed is not None and preparation == self._last_committed:
            if self.window_fingerprint != preparation.next_window_fingerprint:
                raise ValueError("committed preparation is no longer the latest history window")
            return
        if self._pending is None or preparation != self._pending[0]:
            raise ValueError("forward context preparation is not the pending event")
        self._pending = None

    def append(
        self,
        payload: VerifiedForwardMarketPayload,
        *,
        instance_id: str,
        positions: Mapping[str, PositionSnapshot] | None = None,
    ) -> StrategyContext:
        """Convenience for deterministic warm-up replay, which commits in order."""

        preparation = self.prepare(payload, instance_id=instance_id, positions=positions)
        self.commit(preparation)
        return preparation.context

    @classmethod
    def replay_verified_history(
        cls,
        history: ForwardStrategyContextHistory,
        manifest: StrategySdkManifest,
        *,
        parameters: Mapping[str, Any],
        random_seed: int,
        expected_pre_event_checkpoint_fingerprint: str,
        expected_warmup_receipt_fingerprint: str,
    ) -> ForwardStrategyContextWindow:
        """Rebuild bounded SDK history from the exact durable event prefix."""

        if not isinstance(history, ForwardStrategyContextHistory):
            raise TypeError("history must use ForwardStrategyContextHistory")
        if not isinstance(manifest, StrategySdkManifest):
            raise TypeError("manifest must use StrategySdkManifest")
        require_sha256_digest(
            expected_pre_event_checkpoint_fingerprint,
            field_name="expected_pre_event_checkpoint_fingerprint",
        )
        require_sha256_digest(
            expected_warmup_receipt_fingerprint,
            field_name="expected_warmup_receipt_fingerprint",
        )
        if history.manifest_fingerprint != manifest.fingerprint:
            raise ValueError("forward context history belongs to a different strategy manifest")
        if history.pre_event_checkpoint_fingerprint != expected_pre_event_checkpoint_fingerprint:
            raise ValueError("forward context history is not at the requested pre-event checkpoint")
        if history.warmup_receipt_fingerprint != expected_warmup_receipt_fingerprint:
            raise ValueError("forward context history belongs to a different warm-up receipt")

        window = cls(
            history.instance_id,
            manifest,
            parameters=parameters,
            random_seed=random_seed,
        )
        counts: dict[str, int] = {}
        for payload in history.events:
            dependency = window._dependencies.get(payload.market_event.dependency_id)
            if dependency is None:
                raise ValueError("forward context history contains an undeclared dependency")
            counts[dependency.dependency_id] = counts.get(dependency.dependency_id, 0) + 1
            if counts[dependency.dependency_id] > dependency.lookback_periods + 1:
                raise ValueError("forward context history exceeds a dependency lookback window")
            window.append(payload, instance_id=history.instance_id)
        return window


def _same_delivery_binding(
    preparation: ForwardStrategyContextPreparation,
    binding: NautilusForwardDeliveryBinding | None,
) -> bool:
    if binding is None:
        return preparation.delivery_binding_fingerprint is None
    return (
        preparation.delivery_binding_fingerprint == binding.fingerprint
        and preparation.dispatch_fingerprint == binding.dispatch_record_fingerprint
        and preparation.pre_event_checkpoint_fingerprint == binding.pre_event_checkpoint_fingerprint
        and preparation.warmup_receipt_fingerprint == binding.warmup_receipt_fingerprint
    )


__all__ = [
    "ForwardPortfolioContextPreparation",
    "ForwardStrategyContextHistory",
    "ForwardStrategyContextPreparation",
    "ForwardStrategyContextWindow",
]
