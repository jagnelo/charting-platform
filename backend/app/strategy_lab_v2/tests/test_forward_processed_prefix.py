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
from app.strategy_lab_v2.forward_admission import ForwardLiveAdmissionState, ForwardSeenEvent
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
            start=NOW - timedelta(days=1),
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
    sequence: int,
    event_time: datetime,
    *,
    dependency_id: str = "aapl-bars",
    instrument_id: str = "US.AAPL",
    source_digest: str | None = None,
    correction_of: str | None = None,
) -> VerifiedForwardMarketPayload:
    digest = source_digest or content_digest({"source": event_id})
    canonical = CanonicalForwardEvent(
        event_id,
        sequence,
        event_time,
        event_time + timedelta(milliseconds=1),
        digest,
        correction_of=correction_of,
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


def _inputs():
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
    warmup = _payload("warmup-0", 0, NOW)
    receipt = ForwardWarmupReceipt(
        INSTANCE_ID,
        SNAPSHOT_FINGERPRINT,
        CarryInMode.FLAT,
        content_digest("warmup-result"),
        NOW + timedelta(seconds=1),
        warmup.canonical_event.event_id,
        warmup.canonical_event.sequence,
        content_digest(warmup.canonical_event),
    )
    active = resolve_forward_warmup(warming, receipt).instance
    payloads = (
        warmup,
        _payload("live-1", 1, NOW + timedelta(minutes=1)),
        _payload(
            "live-2",
            2,
            NOW + timedelta(minutes=2),
            dependency_id="spy-bars",
            instrument_id="US.SPY",
        ),
        _payload("live-3", 3, NOW + timedelta(minutes=3)),
        _payload("live-4", 4, NOW + timedelta(minutes=4)),
    )
    seen = tuple(
        ForwardSeenEvent(
            payload.canonical_event.event_id,
            content_digest(payload.canonical_event),
            payload.canonical_event.sequence,
        )
        for payload in payloads
    )
    admission = ForwardLiveAdmissionState(
        ForwardStateCheckpoint(
            active,
            processed_event_ids=frozenset(item.event_id for item in seen),
        ),
        receipt.fingerprint,
        seen,
    )
    before_event = _payload("live-5", 5, NOW + timedelta(minutes=5)).canonical_event
    return admission, receipt, before_event, payloads


class PrefixReader:
    def __init__(self, events: tuple[VerifiedForwardMarketPayload, ...]) -> None:
        self.events = events
        self.calls: list[dict[str, Any]] = []

    async def read_processed_prefix(self, **kwargs: Any):
        self.calls.append(kwargs)
        return self.events


@pytest.mark.anyio
async def test_resolves_exact_processed_prefix_with_per_dependency_bounds() -> None:
    admission, receipt, before_event, payloads = _inputs()
    manifest = _manifest()
    reader = PrefixReader((payloads[2], payloads[3], payloads[4]))
    resolver = AuthenticatedForwardProcessedPrefixResolver(reader, principal=OWNER_ID)

    prefix = await resolver(
        principal=OWNER_ID,
        admission_state=admission,
        warmup_receipt=receipt,
        manifest=manifest,
        before_event=before_event,
    )

    assert prefix.instance_id == INSTANCE_ID
    assert prefix.pre_event_checkpoint_fingerprint == admission.checkpoint.fingerprint
    assert prefix.warmup_receipt_fingerprint == receipt.fingerprint
    assert prefix.before_event_fingerprint == content_digest(before_event)
    assert prefix.dependency_event_limits == (("aapl-bars", 2), ("spy-bars", 1))
    assert tuple(item.canonical_event.event_id for item in prefix.events) == (
        "live-2",
        "live-3",
        "live-4",
    )
    assert len(reader.calls) == 1
    assert reader.calls[0]["principal"] == OWNER_ID
    assert reader.calls[0]["processed_events"] == tuple(
        sorted(
            (item for item in admission.seen_events if item.event_id != receipt.final_event_id),
            key=lambda item: (item.sequence, item.event_id),
        )
    )


@pytest.mark.anyio
async def test_rejects_prefix_event_not_in_processed_checkpoint() -> None:
    admission, receipt, before_event, payloads = _inputs()
    resolver = AuthenticatedForwardProcessedPrefixResolver(
        PrefixReader((payloads[0],)),
        principal=OWNER_ID,
    )

    with pytest.raises(ValueError, match="unprocessed event"):
        await resolver(
            principal=OWNER_ID,
            admission_state=admission,
            warmup_receipt=receipt,
            manifest=_manifest(),
            before_event=before_event,
        )


@pytest.mark.anyio
async def test_rejects_payload_fingerprint_alias_even_when_event_id_and_sequence_match() -> None:
    admission, receipt, before_event, payloads = _inputs()
    altered = _payload(
        "live-3",
        3,
        NOW + timedelta(minutes=3),
        source_digest=content_digest("forged-source"),
    )
    resolver = AuthenticatedForwardProcessedPrefixResolver(
        PrefixReader((payloads[2], altered, payloads[4])),
        principal=OWNER_ID,
    )

    with pytest.raises(ValueError, match="differs from admission evidence"):
        await resolver(
            principal=OWNER_ID,
            admission_state=admission,
            warmup_receipt=receipt,
            manifest=_manifest(),
            before_event=before_event,
        )


@pytest.mark.anyio
async def test_rejects_prefix_beyond_dependency_lookback() -> None:
    admission, receipt, before_event, payloads = _inputs()
    resolver = AuthenticatedForwardProcessedPrefixResolver(
        PrefixReader((payloads[1], payloads[2], payloads[3], payloads[4])),
        principal=OWNER_ID,
    )

    with pytest.raises(ValueError, match="exceeded a dependency lookback"):
        await resolver(
            principal=OWNER_ID,
            admission_state=admission,
            warmup_receipt=receipt,
            manifest=_manifest(),
            before_event=before_event,
        )


@pytest.mark.anyio
async def test_rejects_unprocessed_state_id_missing_its_seen_event_binding() -> None:
    admission, receipt, before_event, _payloads = _inputs()
    checkpoint = replace(
        admission.checkpoint,
        processed_event_ids=admission.checkpoint.processed_event_ids | {"missing-event"},
    )
    changed = ForwardLiveAdmissionState(
        checkpoint,
        admission.warmup_receipt_fingerprint,
        admission.seen_events,
    )
    resolver = AuthenticatedForwardProcessedPrefixResolver(PrefixReader(()), principal=OWNER_ID)

    with pytest.raises(ValueError, match="without admission evidence"):
        await resolver(
            principal=OWNER_ID,
            admission_state=changed,
            warmup_receipt=receipt,
            manifest=_manifest(),
            before_event=before_event,
        )


@pytest.mark.anyio
async def test_empty_warmup_cursor_allows_first_processed_event_sequence_zero() -> None:
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
    first = _payload("first-live", 0, NOW + timedelta(minutes=1))
    active_after_first = replace(
        active,
        last_event_id=first.canonical_event.event_id,
        last_event_sequence=first.canonical_event.sequence,
        updated_at=NOW + timedelta(minutes=1),
    )
    admission = ForwardLiveAdmissionState(
        ForwardStateCheckpoint(
            active_after_first,
            processed_event_ids=frozenset({first.canonical_event.event_id}),
        ),
        receipt.fingerprint,
        (
            ForwardSeenEvent(
                first.canonical_event.event_id,
                content_digest(first.canonical_event),
                first.canonical_event.sequence,
            ),
        ),
    )
    before_event = _payload("second-live", 1, NOW + timedelta(minutes=2)).canonical_event
    resolver = AuthenticatedForwardProcessedPrefixResolver(
        PrefixReader((first,)),
        principal=OWNER_ID,
    )

    prefix = await resolver(
        principal=OWNER_ID,
        admission_state=admission,
        warmup_receipt=receipt,
        manifest=_manifest(),
        before_event=before_event,
    )

    assert tuple(item.canonical_event.event_id for item in prefix.events) == ("first-live",)
