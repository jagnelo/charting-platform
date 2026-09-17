"""Deterministic strategy replay over a frozen, snapshot-bound event tape.

This module is the engine-neutral bridge between immutable market-data inputs
and the stateful strategy runtime.  It constructs one context per same-time
event batch with each dependency's declared trailing lookback, then invokes one
strategy instance in chronological order.  It never fetches data, applies
orders, models fills, or mutates account state; an engine adapter remains the
owner of those concerns.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import DataSnapshot
from app.strategy_lab_v2.event_tape import FrozenEventTape, bind_event_tape
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    PositionSnapshot,
    StrategyContext,
    StrategySdkManifest,
    build_strategy_context,
)
from strategy_runtime.runner import (
    InvocationStatus,
    StrategyInvocationResult,
    StrategyInvocationSession,
)


class ReplayStatus(StrEnum):
    """Terminal status for a bounded strategy replay."""

    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"


def build_event_tape_contexts(
    tape: FrozenEventTape,
    manifest: StrategySdkManifest,
    *,
    random_seed: int,
    parameters: Mapping[str, Any],
    positions_by_batch: Mapping[int, Mapping[str, PositionSnapshot]] | None = None,
) -> tuple[StrategyContext, ...]:
    """Build one immutable SDK context for every timestamp batch in ``tape``.

    Histories are advanced only at a batch boundary and are truncated to each
    dependency's ``lookback_periods + 1`` most recent events.  Thus all events
    sharing a timestamp are visible together, while a strategy cannot observe
    a future event or an unbounded input history.  Optional position snapshots
    are supplied by the host/engine using the batch sequence; missing entries
    intentionally mean an empty position map.
    """

    if not isinstance(tape, FrozenEventTape):
        raise TypeError("tape must be a FrozenEventTape")
    if not isinstance(manifest, StrategySdkManifest):
        raise TypeError("manifest must be a StrategySdkManifest")
    if not isinstance(random_seed, int) or isinstance(random_seed, bool):
        raise TypeError("random_seed must be an integer")
    if not isinstance(parameters, Mapping):
        raise TypeError("parameters must be a mapping")
    if positions_by_batch is not None and not isinstance(positions_by_batch, Mapping):
        raise TypeError("positions_by_batch must be a mapping or None")
    if not tape.events:
        raise ValueError("event tape cannot replay an empty event set")

    batches = tape.batches()
    known_sequences = {batch.batch_sequence for batch in batches}
    if positions_by_batch is not None:
        for batch_sequence, positions in positions_by_batch.items():
            if (
                not isinstance(batch_sequence, int)
                or isinstance(batch_sequence, bool)
                or batch_sequence not in known_sequences
            ):
                raise ValueError("positions_by_batch contains an unknown batch sequence")
            if not isinstance(positions, Mapping):
                raise TypeError("positions_by_batch values must be mappings")
            if any(
                not isinstance(instrument_id, str) or not instrument_id.strip()
                for instrument_id in positions
            ):
                raise ValueError("position map keys must be non-empty strings")
            if any(not isinstance(position, PositionSnapshot) for position in positions.values()):
                raise TypeError("positions_by_batch values must contain PositionSnapshot records")

    declared = {item.dependency_id: item for item in manifest.data_dependencies}
    if {event.dependency_id for event in tape.events} != set(declared):
        raise ValueError("event tape dependencies do not match the SDK manifest")

    histories: dict[str, list[MarketEvent]] = {dependency_id: [] for dependency_id in declared}
    contexts: list[StrategyContext] = []
    for batch in batches:
        for event in batch.events:
            histories[event.dependency_id].append(event)

        market_events = {
            dependency_id: tuple(
                history[-(declared[dependency_id].lookback_periods + 1) :]
            )
            for dependency_id, history in histories.items()
        }
        positions = (
            positions_by_batch.get(batch.batch_sequence, {})
            if positions_by_batch is not None
            else {}
        )
        event_sequence = max(event.sequence for event in batch.events)
        contexts.append(
            build_strategy_context(
                manifest,
                event_time=batch.event_time,
                event_sequence=event_sequence,
                random_seed=random_seed,
                parameters=parameters,
                market_events=market_events,
                positions=positions,
            )
        )
    return tuple(contexts)


@dataclass(frozen=True, slots=True)
class StrategyReplayResult:
    """Content-addressed outcome of a frozen-tape strategy replay."""

    tape_fingerprint: str
    binding_fingerprint: str
    manifest_fingerprint: str
    source_digest: str
    entrypoint: str
    random_seed: int
    parameters_digest: str
    batch_count: int
    processed_batches: int
    status: ReplayStatus
    invocations: tuple[StrategyInvocationResult, ...]
    stopped_batch_sequence: int | None = None

    def __post_init__(self) -> None:
        for name in (
            "tape_fingerprint",
            "binding_fingerprint",
            "manifest_fingerprint",
            "source_digest",
            "parameters_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.entrypoint, str) or not self.entrypoint.strip():
            raise ValueError("entrypoint must not be empty")
        if not isinstance(self.random_seed, int) or isinstance(self.random_seed, bool):
            raise TypeError("random_seed must be an integer")
        for name in ("batch_count", "processed_batches"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.processed_batches > self.batch_count:
            raise ValueError("processed_batches cannot exceed batch_count")
        if not isinstance(self.status, ReplayStatus):
            raise TypeError("status must be a ReplayStatus")
        invocations = tuple(self.invocations)
        if len(invocations) != self.processed_batches:
            raise ValueError("processed_batches must equal the invocation count")
        if not invocations:
            raise ValueError("replay results require at least one invocation")
        if any(not isinstance(item, StrategyInvocationResult) for item in invocations):
            raise TypeError("invocations must contain StrategyInvocationResult values")
        if any(
            item.source_digest != self.source_digest or item.entrypoint != self.entrypoint
            for item in invocations
        ):
            raise ValueError("invocations must reference the replay source and entrypoint")
        if self.stopped_batch_sequence is not None and (
            not isinstance(self.stopped_batch_sequence, int)
            or isinstance(self.stopped_batch_sequence, bool)
            or not 0 <= self.stopped_batch_sequence < self.batch_count
        ):
            raise ValueError("stopped_batch_sequence must identify a replay batch")

        last = invocations[-1]
        if self.status is ReplayStatus.SUCCEEDED:
            if self.processed_batches != self.batch_count or self.stopped_batch_sequence is not None:
                raise ValueError("successful replays must process every batch")
            if any(item.status is not InvocationStatus.SUCCEEDED for item in invocations):
                raise ValueError("successful replays cannot contain rejected or failed invocations")
        if self.status is ReplayStatus.REJECTED and last.status is not InvocationStatus.REJECTED:
            raise ValueError("rejected replays must stop at a rejected invocation")
        if self.status is ReplayStatus.FAILED and last.status is not InvocationStatus.FAILED:
            raise ValueError("failed replays must stop at a failed invocation")
        if self.status is not ReplayStatus.SUCCEEDED and self.stopped_batch_sequence is None:
            raise ValueError("non-successful replays require a stopped batch sequence")
        if self.status is not ReplayStatus.SUCCEEDED:
            assert self.stopped_batch_sequence is not None
            if self.processed_batches != self.stopped_batch_sequence + 1:
                raise ValueError("non-successful replays must stop at their last processed batch")
        object.__setattr__(self, "invocations", invocations)

    @property
    def accepted(self) -> bool:
        return self.status is ReplayStatus.SUCCEEDED

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def replay_event_tape(
    source: str,
    *,
    tape: FrozenEventTape,
    snapshot: DataSnapshot,
    manifest: StrategySdkManifest,
    random_seed: int,
    parameters: Mapping[str, Any],
    entrypoint: str,
    positions_by_batch: Mapping[int, Mapping[str, PositionSnapshot]] | None = None,
    max_intents_per_event: int = 100,
) -> StrategyReplayResult:
    """Bind and replay one frozen tape through one stateful strategy session.

    Binding is repeated at this execution boundary so a caller cannot pass a
    tape merely because it has a plausible snapshot digest.  Invocation stops
    at the first typed rejection or failure; no later context is exposed after
    a terminal runtime outcome.
    """

    if not isinstance(source, str):
        raise TypeError("source must be a string")
    if not isinstance(tape, FrozenEventTape):
        raise TypeError("tape must be a FrozenEventTape")
    if not isinstance(snapshot, DataSnapshot):
        raise TypeError("snapshot must be a DataSnapshot")
    if not isinstance(manifest, StrategySdkManifest):
        raise TypeError("manifest must be a StrategySdkManifest")
    binding = bind_event_tape(tape, snapshot, manifest)
    contexts = build_event_tape_contexts(
        tape,
        manifest,
        random_seed=random_seed,
        parameters=parameters,
        positions_by_batch=positions_by_batch,
    )
    session = StrategyInvocationSession(
        source,
        manifest=manifest,
        entrypoint=entrypoint,
        max_intents_per_event=max_intents_per_event,
    )
    invocations: list[StrategyInvocationResult] = []
    stopped_batch_sequence: int | None = None
    for batch_sequence, context in enumerate(contexts):
        result = session.invoke(context)
        invocations.append(result)
        if result.status is not InvocationStatus.SUCCEEDED:
            stopped_batch_sequence = batch_sequence
            break

    last = invocations[-1]
    status = (
        ReplayStatus.SUCCEEDED
        if len(invocations) == len(contexts)
        and all(item.status is InvocationStatus.SUCCEEDED for item in invocations)
        else ReplayStatus(last.status.value)
    )
    return StrategyReplayResult(
        tape_fingerprint=tape.fingerprint,
        binding_fingerprint=binding.fingerprint,
        manifest_fingerprint=manifest.fingerprint,
        source_digest=content_digest(source),
        entrypoint=entrypoint,
        random_seed=random_seed,
        parameters_digest=content_digest(parameters),
        batch_count=len(contexts),
        processed_batches=len(invocations),
        status=status,
        invocations=tuple(invocations),
        stopped_batch_sequence=stopped_batch_sequence,
    )


__all__ = [
    "ReplayStatus",
    "StrategyReplayResult",
    "build_event_tape_contexts",
    "replay_event_tape",
]
