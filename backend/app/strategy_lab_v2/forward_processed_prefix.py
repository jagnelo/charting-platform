"""Resolve a bounded canonical live-event prefix at an exact checkpoint."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState, ForwardSeenEvent
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_forward_delivery import VerifiedForwardMarketPayload
from app.strategy_lab_v2.sdk import StrategySdkManifest


@dataclass(frozen=True, slots=True)
class ForwardProcessedEventPrefix:
    """Source-verified live suffix bound to one checkpoint and warm-up receipt."""

    instance_id: str
    pre_event_checkpoint_fingerprint: str
    warmup_receipt_fingerprint: str
    manifest_fingerprint: str
    before_event_fingerprint: str
    dependency_event_limits: tuple[tuple[str, int], ...]
    events: tuple[VerifiedForwardMarketPayload, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.instance_id, str) or not self.instance_id.strip():
            raise ValueError("instance_id must not be empty")
        for name in (
            "pre_event_checkpoint_fingerprint",
            "warmup_receipt_fingerprint",
            "manifest_fingerprint",
            "before_event_fingerprint",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        limits = tuple(self.dependency_event_limits)
        if not limits or limits != tuple(sorted(limits)):
            raise ValueError("dependency event limits must be non-empty and ordered")
        if len({dependency_id for dependency_id, _limit in limits}) != len(limits):
            raise ValueError("dependency event limits must have unique dependency ids")
        if any(
            not isinstance(dependency_id, str)
            or not dependency_id.strip()
            or not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            for dependency_id, limit in limits
        ):
            raise ValueError("dependency event limits must be positive keyed values")
        events = tuple(self.events)
        if any(not isinstance(item, VerifiedForwardMarketPayload) for item in events):
            raise TypeError("events must contain VerifiedForwardMarketPayload values")
        event_ids = [item.canonical_event.event_id for item in events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError("processed prefix event ids must be unique")
        event_keys = [
            (item.canonical_event.event_time, item.canonical_event.sequence) for item in events
        ]
        if any(current <= previous for previous, current in zip(event_keys, event_keys[1:])):
            raise ValueError("processed prefix must advance strictly by canonical event order")
        limits_by_dependency = dict(limits)
        counts: dict[str, int] = {}
        for item in events:
            dependency_id = item.market_event.dependency_id
            if dependency_id not in limits_by_dependency:
                raise ValueError("processed prefix contains an undeclared dependency")
            counts[dependency_id] = counts.get(dependency_id, 0) + 1
            if counts[dependency_id] > limits_by_dependency[dependency_id]:
                raise ValueError("processed prefix exceeds a dependency lookback")
        object.__setattr__(self, "dependency_event_limits", limits)
        object.__setattr__(self, "events", events)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class CanonicalForwardProcessedPrefixReader(Protocol):
    """Read the latest bounded payload suffix from local canonical event storage.

    Implementations are principal-scoped and query only the explicitly supplied
    processed event bindings at the exact admission checkpoint. They do not
    fetch providers or substitute a mutable current-data source.
    """

    def read_processed_prefix(
        self,
        *,
        principal: Any,
        admission_state: ForwardLiveAdmissionState,
        warmup_receipt: ForwardWarmupReceipt,
        manifest: StrategySdkManifest,
        processed_events: Sequence[ForwardSeenEvent],
        before_event: CanonicalForwardEvent,
    ) -> (
        Sequence[VerifiedForwardMarketPayload] | Awaitable[Sequence[VerifiedForwardMarketPayload]]
    ): ...


class AuthenticatedForwardProcessedPrefixResolver:
    """Authenticate and validate a store's bounded processed-event read."""

    def __init__(
        self,
        reader: CanonicalForwardProcessedPrefixReader,
        *,
        principal: Any,
    ) -> None:
        if not callable(getattr(reader, "read_processed_prefix", None)):
            raise TypeError("reader must expose read_processed_prefix")
        self._reader = reader
        self._principal = principal

    async def __call__(
        self,
        *,
        principal: Any,
        admission_state: ForwardLiveAdmissionState,
        warmup_receipt: ForwardWarmupReceipt,
        manifest: StrategySdkManifest,
        before_event: CanonicalForwardEvent,
    ) -> ForwardProcessedEventPrefix:
        if principal != self._principal:
            raise ValueError("processed history belongs to another principal")
        if not isinstance(admission_state, ForwardLiveAdmissionState):
            raise TypeError("admission_state must use ForwardLiveAdmissionState")
        if not isinstance(warmup_receipt, ForwardWarmupReceipt):
            raise TypeError("warmup_receipt must use ForwardWarmupReceipt")
        if not isinstance(manifest, StrategySdkManifest):
            raise TypeError("manifest must use StrategySdkManifest")
        if not isinstance(before_event, CanonicalForwardEvent):
            raise TypeError("before_event must use CanonicalForwardEvent")

        checkpoint = admission_state.checkpoint
        instance = checkpoint.instance
        if admission_state.warmup_receipt_fingerprint != warmup_receipt.fingerprint:
            raise ValueError("admission checkpoint belongs to a different warm-up receipt")
        if warmup_receipt.instance_id != instance.instance_id:
            raise ValueError("warm-up receipt belongs to another forward instance")
        if warmup_receipt.warmup_snapshot_fingerprint != instance.warmup_snapshot_fingerprint:
            raise ValueError("warm-up receipt belongs to another frozen snapshot")

        seen_by_id = {item.event_id: item for item in admission_state.seen_events}
        processed_ids = checkpoint.processed_event_ids
        if not processed_ids.issubset(seen_by_id):
            raise ValueError("processed checkpoint contains an event without admission evidence")
        if before_event.event_id in seen_by_id:
            raise ValueError("current event is already present in the pre-event checkpoint")

        warmup_binding: ForwardSeenEvent | None = None
        if warmup_receipt.final_event_id is not None:
            warmup_binding = seen_by_id.get(warmup_receipt.final_event_id)
            if (
                warmup_binding is None
                or warmup_receipt.final_event_id not in processed_ids
                or warmup_binding.sequence != warmup_receipt.final_event_sequence
                or warmup_binding.event_fingerprint != warmup_receipt.final_event_fingerprint
            ):
                raise ValueError("warm-up cursor differs from processed admission evidence")
        elif warmup_receipt.final_event_sequence != 0:
            raise ValueError("empty warm-up cursor has a non-zero sequence")
        warmup_sequence = (
            -1 if warmup_receipt.final_event_id is None else warmup_receipt.final_event_sequence
        )

        processed_suffix = tuple(
            sorted(
                (
                    seen_by_id[event_id]
                    for event_id in processed_ids
                    if warmup_binding is None or event_id != warmup_binding.event_id
                ),
                key=lambda item: (item.sequence, item.event_id),
            )
        )
        if any(item.sequence <= warmup_sequence for item in processed_suffix):
            raise ValueError("processed live event does not follow the warm-up cursor")
        suffix_sequences = [item.sequence for item in processed_suffix]
        if len(suffix_sequences) != len(set(suffix_sequences)):
            raise ValueError("processed live event sequences must be unique")
        if any(item.sequence >= before_event.sequence for item in processed_suffix):
            raise ValueError("processed checkpoint contains the current or a future sequence")

        resolution: (
            Sequence[VerifiedForwardMarketPayload]
            | Awaitable[Sequence[VerifiedForwardMarketPayload]]
        )
        if processed_suffix:
            resolution = self._reader.read_processed_prefix(
                principal=self._principal,
                admission_state=admission_state,
                warmup_receipt=warmup_receipt,
                manifest=manifest,
                processed_events=processed_suffix,
                before_event=before_event,
            )
            resolved = await resolution if inspect.isawaitable(resolution) else resolution
        else:
            resolved = ()

        if not isinstance(resolved, Sequence) or isinstance(resolved, str | bytes):
            raise TypeError("processed-prefix reader must return a sequence")
        expected_by_id = {item.event_id: item for item in processed_suffix}
        dependencies = {item.dependency_id: item for item in manifest.data_dependencies}
        limits = {
            dependency_id: dependency.lookback_periods + 1
            for dependency_id, dependency in dependencies.items()
        }
        counts: dict[str, int] = {}
        current_key = (before_event.event_time, before_event.sequence)
        previous_key: tuple[datetime, int] | None = None
        observed_ids: set[str] = set()
        for payload in resolved:
            if not isinstance(payload, VerifiedForwardMarketPayload):
                raise TypeError("processed-prefix reader returned an invalid payload")
            canonical = payload.canonical_event
            market = payload.market_event
            seen = expected_by_id.get(canonical.event_id)
            if seen is None:
                raise ValueError("processed-prefix reader returned an unprocessed event")
            if canonical.event_id in observed_ids:
                raise ValueError("processed-prefix reader returned a duplicate event")
            observed_ids.add(canonical.event_id)
            if (
                content_digest(canonical) != seen.event_fingerprint
                or canonical.sequence != seen.sequence
            ):
                raise ValueError("processed-prefix payload differs from admission evidence")
            if canonical.correction_of is not None:
                raise ValueError("correction events cannot enter the forward context prefix")
            event_key = (canonical.event_time, canonical.sequence)
            if event_key >= current_key:
                raise ValueError("processed-prefix reader returned the current or a future event")
            if previous_key is not None and event_key <= previous_key:
                raise ValueError("processed-prefix payloads are not in canonical event order")
            previous_key = event_key

            dependency = dependencies.get(market.dependency_id)
            if dependency is None:
                raise ValueError("processed-prefix reader returned an undeclared dependency")
            requirement = dependency.requirement
            if market.instrument_id != requirement.instrument_id:
                raise ValueError("processed-prefix instrument differs from its declaration")
            if not requirement.start <= market.event_time < requirement.end:
                raise ValueError("processed-prefix event is outside its declared interval")
            if set(market.values) != set(dependency.fields):
                raise ValueError("processed-prefix fields differ from their declaration")
            counts[market.dependency_id] = counts.get(market.dependency_id, 0) + 1
            if counts[market.dependency_id] > limits[market.dependency_id]:
                raise ValueError("processed-prefix reader exceeded a dependency lookback")

        return ForwardProcessedEventPrefix(
            instance_id=instance.instance_id,
            pre_event_checkpoint_fingerprint=checkpoint.fingerprint,
            warmup_receipt_fingerprint=warmup_receipt.fingerprint,
            manifest_fingerprint=manifest.fingerprint,
            before_event_fingerprint=content_digest(before_event),
            dependency_event_limits=tuple(sorted(limits.items())),
            events=tuple(resolved),
        )


__all__ = [
    "AuthenticatedForwardProcessedPrefixResolver",
    "CanonicalForwardProcessedPrefixReader",
    "ForwardProcessedEventPrefix",
]
