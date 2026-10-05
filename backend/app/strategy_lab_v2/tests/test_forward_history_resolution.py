from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    CarryInMode,
    EventGranularity,
    ForwardInstance,
    ForwardState,
    ProductClass,
    StrategyVersion,
)
from app.strategy_lab_v2.event_tape_artifacts import FrozenEventTapeWindowResolution
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState, ForwardSeenEvent
from app.strategy_lab_v2.forward_history_resolution import (
    AuthenticatedForwardContextHistoryResolver,
)
from app.strategy_lab_v2.forward_processed_prefix import (
    AuthenticatedForwardProcessedPrefixResolver,
)
from app.strategy_lab_v2.forward_state import ForwardStateCheckpoint
from app.strategy_lab_v2.forward_warmup import ForwardWarmupReceipt, resolve_forward_warmup
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_forward_delivery import VerifiedForwardMarketPayload
from app.strategy_lab_v2.sdk import MarketEvent, StrategyDataDependency, StrategySdkManifest

NOW = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
OWNER_ID = "owner-1"
INSTANCE_ID = "forward-1"
SNAPSHOT_FINGERPRINT = content_digest("snapshot")


def _manifest() -> StrategySdkManifest:
    def dependency(dependency_id: str, instrument_id: str, lookback: int):
        requirement = CapabilityRequirement(
            instrument_id=instrument_id,
            product_class=ProductClass.EQUITY,
            event_granularity=EventGranularity.BAR,
            event_type="ohlcv",
            timeframe="1d",
            start=NOW - timedelta(days=5),
            end=NOW + timedelta(days=10),
            adjustment=AdjustmentMode.SPLIT_ADJUSTED,
            session="regular",
            feed="consolidated",
            execution_model="bar-close",
            account_model="cash",
            corporate_action_semantics="split-adjusted-v1",
        )
        return StrategyDataDependency(dependency_id, requirement, ("close",), lookback)

    return StrategySdkManifest(
        StrategyVersion("strategy-1", "version-1", "2.0", content_digest("source")),
        (
            dependency("aapl-bars", "US.AAPL", 1),
            dependency("spy-bars", "US.SPY", 0),
        ),
    )


def _payload(
    event_id: str,
    dependency_id: str,
    instrument_id: str,
    sequence: int,
    event_time: datetime,
) -> VerifiedForwardMarketPayload:
    digest = content_digest({"source": event_id})
    canonical = CanonicalForwardEvent(
        event_id,
        sequence,
        event_time,
        event_time + timedelta(milliseconds=1),
        digest,
    )
    market = MarketEvent(
        dependency_id,
        event_id,
        instrument_id,
        event_time,
        sequence,
        {"close": Decimal(sequence)},
    )
    return VerifiedForwardMarketPayload(canonical, market, digest)


def _tape_event(
    event_id: str,
    dependency_id: str,
    instrument_id: str,
    local_sequence: int,
    global_sequence: int,
    event_time: datetime,
) -> MarketEvent:
    return MarketEvent(
        dependency_id,
        event_id,
        instrument_id,
        event_time,
        local_sequence,
        {"close": Decimal(global_sequence)},
    )


class SnapshotWindowResolver:
    def __init__(self, window: FrozenEventTapeWindowResolution | None = None) -> None:
        self.window = window
        self.calls: list[dict[str, Any]] = []

    async def resolve_bounded_window(self, *args: Any, **kwargs: Any):
        self.calls.append({"args": args, **kwargs})
        if self.window is None:
            raise AssertionError("an empty warm-up must not read a frozen snapshot window")
        return self.window


class FrozenPayloadReader:
    def __init__(self, payloads: tuple[VerifiedForwardMarketPayload, ...]) -> None:
        self.payloads = payloads
        self.calls: list[dict[str, Any]] = []

    def read_frozen_payloads(self, **kwargs: Any):
        self.calls.append(kwargs)
        return self.payloads


class ProcessedPrefixReader:
    def __init__(self, payloads: tuple[VerifiedForwardMarketPayload, ...]) -> None:
        self.payloads = payloads
        self.calls: list[dict[str, Any]] = []

    def read_processed_prefix(self, **kwargs: Any):
        self.calls.append(kwargs)
        return self.payloads


@pytest.mark.anyio
async def test_composes_frozen_and_live_history_by_canonical_order_and_combined_lookback() -> None:
    manifest = _manifest()
    warmup_a0 = _payload("warm-a0", "aapl-bars", "US.AAPL", 40, NOW)
    warmup_a1 = _payload("warm-a1", "aapl-bars", "US.AAPL", 41, NOW + timedelta(minutes=1))
    warmup_b0 = _payload("warm-b0", "spy-bars", "US.SPY", 42, NOW + timedelta(minutes=2))
    live_a0 = _payload("live-a0", "aapl-bars", "US.AAPL", 43, NOW + timedelta(minutes=3))
    current = _payload("current", "aapl-bars", "US.AAPL", 44, NOW + timedelta(minutes=4))
    tape_events = (
        _tape_event("warm-a0", "aapl-bars", "US.AAPL", 0, 40, NOW),
        _tape_event("warm-a1", "aapl-bars", "US.AAPL", 1, 41, NOW + timedelta(minutes=1)),
        _tape_event("warm-b0", "spy-bars", "US.SPY", 0, 42, NOW + timedelta(minutes=2)),
    )
    window = FrozenEventTapeWindowResolution(
        SNAPSHOT_FINGERPRINT,
        manifest.fingerprint,
        content_digest("frozen-tape"),
        (content_digest("source-artifact"),),
        (("aapl-bars", 2), ("spy-bars", 1)),
        tape_events,
        "warm-b0",
    )
    warming = ForwardInstance(
        INSTANCE_ID,
        content_digest("portfolio"),
        SNAPSHOT_FINGERPRINT,
        CarryInMode.FLAT,
        ForwardState.WARMING_UP,
        None,
        0,
        0,
        NOW - timedelta(minutes=1),
        NOW - timedelta(minutes=1),
    )
    receipt = ForwardWarmupReceipt(
        INSTANCE_ID,
        SNAPSHOT_FINGERPRINT,
        CarryInMode.FLAT,
        content_digest("warmup-result"),
        NOW + timedelta(minutes=2, seconds=1),
        warmup_b0.canonical_event.event_id,
        warmup_b0.canonical_event.sequence,
        content_digest(warmup_b0.canonical_event),
    )
    active = resolve_forward_warmup(warming, receipt).instance
    active = replace(
        active,
        last_event_id=live_a0.canonical_event.event_id,
        last_event_sequence=live_a0.canonical_event.sequence,
        updated_at=live_a0.canonical_event.arrived_at,
    )
    admission = ForwardLiveAdmissionState(
        ForwardStateCheckpoint(
            active,
            processed_event_ids=frozenset({"warm-b0", "live-a0"}),
        ),
        receipt.fingerprint,
        (
            ForwardSeenEvent("warm-b0", content_digest(warmup_b0.canonical_event), 42),
            ForwardSeenEvent("live-a0", content_digest(live_a0.canonical_event), 43),
        ),
    )
    snapshot_resolver = SnapshotWindowResolver(window)
    frozen_reader = FrozenPayloadReader((warmup_a0, warmup_a1, warmup_b0))
    prefix_reader = ProcessedPrefixReader((live_a0,))
    prefix_resolver = AuthenticatedForwardProcessedPrefixResolver(
        prefix_reader,
        principal=OWNER_ID,
    )
    resolver = AuthenticatedForwardContextHistoryResolver(
        snapshot_resolver,
        frozen_reader,
        prefix_resolver,
        principal=OWNER_ID,
    )

    history = await resolver(
        principal=OWNER_ID,
        instance=active,
        admission_state=admission,
        warmup_receipt=receipt,
        manifest=manifest,
        before_event=current.canonical_event,
    )

    assert tuple(item.canonical_event.event_id for item in history.events) == (
        "warm-a1",
        "warm-b0",
        "live-a0",
    )
    assert tuple(item.canonical_event.sequence for item in history.events) == (41, 42, 43)
    assert history.before_event_fingerprint == content_digest(current.canonical_event)
    assert history.warmup_tape_fingerprint == window.tape_fingerprint
    assert history.warmup_source_artifact_digests == window.source_artifact_digests
    assert history.processed_prefix_fingerprint is not None
    assert snapshot_resolver.calls[0]["through_event_id"] == "warm-b0"
    assert frozen_reader.calls[0]["window"] == window
    assert prefix_reader.calls[0]["before_event"] == current.canonical_event


@pytest.mark.anyio
async def test_rejects_frozen_payload_reader_that_omits_a_bounded_tape_row() -> None:
    manifest = _manifest()
    warmup_a = _payload("warm-a", "aapl-bars", "US.AAPL", 40, NOW)
    warmup_b = _payload("warm-b", "spy-bars", "US.SPY", 41, NOW + timedelta(minutes=1))
    window = FrozenEventTapeWindowResolution(
        SNAPSHOT_FINGERPRINT,
        manifest.fingerprint,
        content_digest("frozen-tape"),
        (),
        (("aapl-bars", 2), ("spy-bars", 1)),
        (
            _tape_event("warm-a", "aapl-bars", "US.AAPL", 0, 40, NOW),
            _tape_event("warm-b", "spy-bars", "US.SPY", 0, 41, NOW + timedelta(minutes=1)),
        ),
        "warm-b",
    )
    warming = ForwardInstance(
        INSTANCE_ID,
        content_digest("portfolio"),
        SNAPSHOT_FINGERPRINT,
        CarryInMode.FLAT,
        ForwardState.WARMING_UP,
        None,
        0,
        0,
        NOW - timedelta(minutes=1),
        NOW - timedelta(minutes=1),
    )
    receipt = ForwardWarmupReceipt(
        INSTANCE_ID,
        SNAPSHOT_FINGERPRINT,
        CarryInMode.FLAT,
        content_digest("warmup-result"),
        NOW + timedelta(minutes=1, seconds=1),
        "warm-b",
        41,
        content_digest(warmup_b.canonical_event),
    )
    active = resolve_forward_warmup(warming, receipt).instance
    admission = ForwardLiveAdmissionState.from_warmup(active, receipt)
    resolver = AuthenticatedForwardContextHistoryResolver(
        SnapshotWindowResolver(window),
        FrozenPayloadReader((warmup_a,)),
        AuthenticatedForwardProcessedPrefixResolver(ProcessedPrefixReader(()), principal=OWNER_ID),
        principal=OWNER_ID,
    )
    current = _payload("current", "aapl-bars", "US.AAPL", 42, NOW + timedelta(minutes=2))

    with pytest.raises(ValueError, match="exact bounded tape window"):
        await resolver(
            principal=OWNER_ID,
            instance=active,
            admission_state=admission,
            warmup_receipt=receipt,
            manifest=manifest,
            before_event=current.canonical_event,
        )


@pytest.mark.anyio
async def test_empty_warmup_skips_snapshot_and_composes_empty_history() -> None:
    manifest = _manifest()
    warming = ForwardInstance(
        INSTANCE_ID,
        content_digest("portfolio"),
        SNAPSHOT_FINGERPRINT,
        CarryInMode.FLAT,
        ForwardState.WARMING_UP,
        None,
        0,
        0,
        NOW - timedelta(minutes=1),
        NOW - timedelta(minutes=1),
    )
    receipt = ForwardWarmupReceipt(
        INSTANCE_ID,
        SNAPSHOT_FINGERPRINT,
        CarryInMode.FLAT,
        content_digest("empty-warmup-result"),
        NOW,
    )
    active = resolve_forward_warmup(warming, receipt).instance
    admission = ForwardLiveAdmissionState.from_warmup(active, receipt)
    snapshot_resolver = SnapshotWindowResolver()
    frozen_reader = FrozenPayloadReader(())
    resolver = AuthenticatedForwardContextHistoryResolver(
        snapshot_resolver,
        frozen_reader,
        AuthenticatedForwardProcessedPrefixResolver(ProcessedPrefixReader(()), principal=OWNER_ID),
        principal=OWNER_ID,
    )
    current = _payload("first-live", "aapl-bars", "US.AAPL", 0, NOW + timedelta(minutes=1))

    history = await resolver(
        principal=OWNER_ID,
        instance=active,
        admission_state=admission,
        warmup_receipt=receipt,
        manifest=manifest,
        before_event=current.canonical_event,
    )

    assert history.events == ()
    assert snapshot_resolver.calls == []
    assert frozen_reader.calls == []
    assert history.before_event_fingerprint == content_digest(current.canonical_event)
