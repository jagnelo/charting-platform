"""Compose authenticated frozen warm-up and processed live context history."""

from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Awaitable, Sequence
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ForwardInstance
from app.strategy_lab_v2.event_tape_artifacts import FrozenEventTapeWindowResolution
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState
from app.strategy_lab_v2.forward_context import ForwardStrategyContextHistory
from app.strategy_lab_v2.forward_processed_prefix import ForwardProcessedEventPrefix
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_forward_delivery import VerifiedForwardMarketPayload
from app.strategy_lab_v2.sdk import StrategySdkManifest


class FrozenForwardEventWindowResolver(Protocol):
    """Resolve an owner's verified, bounded event tape for the frozen snapshot."""

    def resolve_bounded_window(
        self,
        snapshot_fingerprint: str,
        manifest: StrategySdkManifest,
        *,
        through_event_id: str,
    ) -> FrozenEventTapeWindowResolution | Awaitable[FrozenEventTapeWindowResolution]: ...


class FrozenForwardPayloadReader(Protocol):
    """Bind selected tape rows to source-verified canonical event identities.

    The tape's sequence is dependency-local. Implementations must resolve the
    corresponding canonical event and global sequence from local platform
    history; they must never copy or synthesize that sequence from the tape.
    """

    def read_frozen_payloads(
        self,
        *,
        principal: Any,
        instance_id: str,
        warmup_receipt: ForwardWarmupReceipt,
        manifest: StrategySdkManifest,
        window: FrozenEventTapeWindowResolution,
    ) -> (
        Sequence[VerifiedForwardMarketPayload] | Awaitable[Sequence[VerifiedForwardMarketPayload]]
    ): ...


class ForwardProcessedPrefixResolver(Protocol):
    """Resolve one exact owner-authenticated processed prefix before a new event."""

    def __call__(
        self,
        *,
        principal: Any,
        admission_state: ForwardLiveAdmissionState,
        warmup_receipt: ForwardWarmupReceipt,
        manifest: StrategySdkManifest,
        before_event: CanonicalForwardEvent,
    ) -> ForwardProcessedEventPrefix | Awaitable[ForwardProcessedEventPrefix]: ...


class AuthenticatedForwardContextHistoryResolver:
    """Join source-verified snapshot rows and the processed live suffix.

    Both inputs are reduced to each strategy dependency's declared
    ``lookback + current`` bound after canonical identity has been resolved.
    Frozen tape sequence numbers are never compared with canonical live
    sequence numbers; only the payload reader's verified global identities
    participate in the join and ordering.
    """

    def __init__(
        self,
        snapshot_window_resolver: FrozenForwardEventWindowResolver,
        frozen_payload_reader: FrozenForwardPayloadReader,
        processed_prefix_resolver: ForwardProcessedPrefixResolver,
        *,
        principal: Any,
    ) -> None:
        if not callable(getattr(snapshot_window_resolver, "resolve_bounded_window", None)):
            raise TypeError("snapshot_window_resolver must resolve bounded frozen windows")
        if not callable(getattr(frozen_payload_reader, "read_frozen_payloads", None)):
            raise TypeError("frozen_payload_reader must resolve source-verified payloads")
        if not callable(processed_prefix_resolver):
            raise TypeError("processed_prefix_resolver must be callable")
        self._snapshot_window_resolver = snapshot_window_resolver
        self._frozen_payload_reader = frozen_payload_reader
        self._processed_prefix_resolver = processed_prefix_resolver
        self._principal = principal

    async def __call__(
        self,
        *,
        principal: Any,
        instance: ForwardInstance,
        admission_state: ForwardLiveAdmissionState,
        warmup_receipt: ForwardWarmupReceipt,
        manifest: StrategySdkManifest,
        before_event: CanonicalForwardEvent,
    ) -> ForwardStrategyContextHistory:
        if principal != self._principal:
            raise ValueError("forward context history belongs to another principal")
        if not isinstance(instance, ForwardInstance):
            raise TypeError("instance must use ForwardInstance")
        if not isinstance(admission_state, ForwardLiveAdmissionState):
            raise TypeError("admission_state must use ForwardLiveAdmissionState")
        if not isinstance(warmup_receipt, ForwardWarmupReceipt):
            raise TypeError("warmup_receipt must use ForwardWarmupReceipt")
        if not isinstance(manifest, StrategySdkManifest):
            raise TypeError("manifest must use StrategySdkManifest")
        if not isinstance(before_event, CanonicalForwardEvent):
            raise TypeError("before_event must use CanonicalForwardEvent")

        checkpoint = admission_state.checkpoint
        if checkpoint.instance != instance:
            raise ValueError("admission checkpoint belongs to another forward instance revision")
        if warmup_receipt.instance_id != instance.instance_id:
            raise ValueError("warm-up receipt belongs to another forward instance")
        if warmup_receipt.warmup_snapshot_fingerprint != instance.warmup_snapshot_fingerprint:
            raise ValueError("warm-up receipt belongs to another frozen snapshot")
        if admission_state.warmup_receipt_fingerprint != warmup_receipt.fingerprint:
            raise ValueError("admission checkpoint belongs to another warm-up receipt")

        frozen_payloads: tuple[VerifiedForwardMarketPayload, ...] = ()
        warmup_tape_fingerprint: str | None = None
        warmup_source_artifact_digests: tuple[str, ...] = ()
        if warmup_receipt.final_event_id is not None:
            resolution = self._snapshot_window_resolver.resolve_bounded_window(
                instance.warmup_snapshot_fingerprint,
                manifest,
                through_event_id=warmup_receipt.final_event_id,
            )
            window = await resolution if inspect.isawaitable(resolution) else resolution
            if not isinstance(window, FrozenEventTapeWindowResolution):
                raise TypeError("snapshot resolver returned an invalid frozen event window")
            if (
                window.snapshot_fingerprint != instance.warmup_snapshot_fingerprint
                or window.manifest_fingerprint != manifest.fingerprint
                or window.through_event_id != warmup_receipt.final_event_id
            ):
                raise ValueError("frozen event window differs from the requested warm-up boundary")
            payload_resolution = self._frozen_payload_reader.read_frozen_payloads(
                principal=self._principal,
                instance_id=instance.instance_id,
                warmup_receipt=warmup_receipt,
                manifest=manifest,
                window=window,
            )
            payloads = (
                await payload_resolution
                if inspect.isawaitable(payload_resolution)
                else payload_resolution
            )
            frozen_payloads = _verify_frozen_payloads(
                window,
                payloads,
                warmup_receipt=warmup_receipt,
                manifest=manifest,
                before_event=before_event,
            )
            warmup_tape_fingerprint = window.tape_fingerprint
            warmup_source_artifact_digests = window.source_artifact_digests

        prefix_resolution = self._processed_prefix_resolver(
            principal=self._principal,
            admission_state=admission_state,
            warmup_receipt=warmup_receipt,
            manifest=manifest,
            before_event=before_event,
        )
        prefix = (
            await prefix_resolution if inspect.isawaitable(prefix_resolution) else prefix_resolution
        )
        if not isinstance(prefix, ForwardProcessedEventPrefix):
            raise TypeError("processed-prefix resolver returned an invalid prefix")
        expected_limits = tuple(
            sorted(
                (
                    dependency.dependency_id,
                    dependency.lookback_periods + 1,
                )
                for dependency in manifest.data_dependencies
            )
        )
        if (
            prefix.instance_id != instance.instance_id
            or prefix.pre_event_checkpoint_fingerprint != checkpoint.fingerprint
            or prefix.warmup_receipt_fingerprint != warmup_receipt.fingerprint
            or prefix.manifest_fingerprint != manifest.fingerprint
            or prefix.before_event_fingerprint != content_digest(before_event)
            or prefix.dependency_event_limits != expected_limits
        ):
            raise ValueError("processed prefix is not bound to the requested history checkpoint")

        events_by_dependency: dict[str, list[VerifiedForwardMarketPayload]] = defaultdict(list)
        observed_ids: set[str] = set()
        observed_sequences: set[int] = set()
        current_key = (before_event.event_time, before_event.sequence)
        for payload in (*frozen_payloads, *prefix.events):
            if payload.canonical_event.event_id in observed_ids:
                raise ValueError("frozen and processed history contain a duplicate event id")
            observed_ids.add(payload.canonical_event.event_id)
            if payload.canonical_event.sequence in observed_sequences:
                raise ValueError("canonical history event sequences must be unique")
            observed_sequences.add(payload.canonical_event.sequence)
            _validate_declared_payload(payload, manifest)
            canonical = payload.canonical_event
            if (canonical.event_time, canonical.sequence) >= current_key:
                raise ValueError("forward history includes the current or a future event")
            if canonical.correction_of is not None:
                raise ValueError("correction events cannot enter the forward context history")
            events_by_dependency[payload.market_event.dependency_id].append(payload)

        retained: list[VerifiedForwardMarketPayload] = []
        for dependency in manifest.data_dependencies:
            dependency_events = sorted(
                events_by_dependency.get(dependency.dependency_id, ()),
                key=lambda item: (item.canonical_event.event_time, item.canonical_event.sequence),
            )
            retained.extend(dependency_events[-(dependency.lookback_periods + 1) :])
        retained.sort(
            key=lambda item: (item.canonical_event.event_time, item.canonical_event.sequence)
        )
        frozen_event_ids = {item.canonical_event.event_id for item in frozen_payloads}

        return ForwardStrategyContextHistory(
            instance_id=instance.instance_id,
            manifest_fingerprint=manifest.fingerprint,
            pre_event_checkpoint_fingerprint=checkpoint.fingerprint,
            warmup_receipt_fingerprint=warmup_receipt.fingerprint,
            events=tuple(retained),
            before_event_fingerprint=content_digest(before_event),
            warmup_snapshot_fingerprint=instance.warmup_snapshot_fingerprint,
            warmup_tape_fingerprint=warmup_tape_fingerprint,
            warmup_source_artifact_digests=warmup_source_artifact_digests,
            warmup_event_ids=frozenset(
                item.canonical_event.event_id
                for item in retained
                if item.canonical_event.event_id in frozen_event_ids
            ),
            processed_prefix_fingerprint=prefix.fingerprint,
        )


def _verify_frozen_payloads(
    window: FrozenEventTapeWindowResolution,
    payloads: Sequence[VerifiedForwardMarketPayload],
    *,
    warmup_receipt: ForwardWarmupReceipt,
    manifest: StrategySdkManifest,
    before_event: CanonicalForwardEvent,
) -> tuple[VerifiedForwardMarketPayload, ...]:
    if not isinstance(payloads, Sequence) or isinstance(payloads, str | bytes):
        raise TypeError("frozen payload reader must return a sequence")
    payloads = tuple(payloads)
    if any(not isinstance(item, VerifiedForwardMarketPayload) for item in payloads):
        raise TypeError("frozen payload reader returned an invalid payload")
    by_id = {item.canonical_event.event_id: item for item in payloads}
    if len(by_id) != len(payloads):
        raise ValueError("frozen payload reader returned duplicate event ids")
    tape_events = {item.event_id: item for item in window.events}
    if set(by_id) != set(tape_events):
        raise ValueError("frozen payload reader did not resolve the exact bounded tape window")
    if warmup_receipt.final_event_id not in by_id:
        raise ValueError("frozen tape window does not contain its exact warm-up cursor")

    final = by_id[warmup_receipt.final_event_id]
    if (
        content_digest(final.canonical_event) != warmup_receipt.final_event_fingerprint
        or final.canonical_event.sequence != warmup_receipt.final_event_sequence
    ):
        raise ValueError("frozen canonical identity differs from the warm-up receipt")
    if (final.canonical_event.event_time, final.canonical_event.sequence) >= (
        before_event.event_time,
        before_event.sequence,
    ):
        raise ValueError("current event does not follow the frozen warm-up cursor")

    sequences: set[int] = set()
    for event_id, payload in by_id.items():
        tape_event = tape_events[event_id]
        market = payload.market_event
        if (
            market.dependency_id != tape_event.dependency_id
            or market.event_id != tape_event.event_id
            or market.instrument_id != tape_event.instrument_id
            or market.event_time != tape_event.event_time
            or market.values != tape_event.values
        ):
            raise ValueError("frozen canonical payload differs from its exact snapshot tape row")
        if payload.canonical_event.sequence > warmup_receipt.final_event_sequence:
            raise ValueError("frozen canonical payload is after the warm-up cursor")
        if payload.canonical_event.sequence in sequences:
            raise ValueError("frozen canonical event sequences must be unique")
        sequences.add(payload.canonical_event.sequence)
        _validate_declared_payload(payload, manifest)
    if any(
        item.canonical_event.sequence >= warmup_receipt.final_event_sequence
        for item in payloads
        if item.canonical_event.event_id != warmup_receipt.final_event_id
    ):
        raise ValueError("frozen canonical history does not precede the warm-up cursor")
    return tuple(
        sorted(
            payloads,
            key=lambda item: (item.canonical_event.event_time, item.canonical_event.sequence),
        )
    )


def _validate_declared_payload(
    payload: VerifiedForwardMarketPayload,
    manifest: StrategySdkManifest,
) -> None:
    market = payload.market_event
    dependency = next(
        (item for item in manifest.data_dependencies if item.dependency_id == market.dependency_id),
        None,
    )
    if dependency is None:
        raise ValueError("forward history contains an undeclared dependency")
    requirement = dependency.requirement
    if market.instrument_id != requirement.instrument_id:
        raise ValueError("forward history instrument differs from its declaration")
    if not requirement.start <= market.event_time < requirement.end:
        raise ValueError("forward history event is outside its declared interval")
    if set(market.values) != set(dependency.fields):
        raise ValueError("forward history fields differ from their declaration")


__all__ = [
    "AuthenticatedForwardContextHistoryResolver",
    "FrozenForwardEventWindowResolver",
    "FrozenForwardPayloadReader",
    "ForwardProcessedPrefixResolver",
]
