from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    EventGranularity,
    ProductClass,
    StrategyVersion,
)
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.forward_context import ForwardStrategyContextWindow
from app.strategy_lab_v2.forward_worker_handoff import (
    ForwardEventDispatchPayload,
    ForwardEventWorkItem,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_forward_delivery import (
    NautilusForwardDeliveryInput,
    VerifiedForwardMarketPayload,
    create_nautilus_forward_delivery_callback_factory,
)
from app.strategy_lab_v2.postgres_forward_dispatch import ForwardEventDispatchRecord
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.sdk import MarketEvent, StrategyDataDependency, StrategySdkManifest

EVENT_TIME = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
STRATEGY_SOURCE = "class Strategy:\n    def on_event(self, context):\n        return []\n"


def _canonical_event(*, source_digest: str | None = None) -> CanonicalForwardEvent:
    return CanonicalForwardEvent(
        event_id="bar-live-1",
        sequence=12,
        event_time=EVENT_TIME,
        arrived_at=EVENT_TIME + timedelta(seconds=1),
        source_digest=source_digest or content_digest({"source": "bar-live-1"}),
    )


def _market_event(canonical: CanonicalForwardEvent) -> MarketEvent:
    return MarketEvent(
        dependency_id="daily-bars",
        event_id=canonical.event_id,
        instrument_id="US.AAPL",
        event_time=canonical.event_time,
        sequence=canonical.sequence,
        values={"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1200},
    )


def _redis_work_item(
    canonical: CanonicalForwardEvent,
    *,
    admission_decision: str = "enqueue",
    replay_plan_fingerprint: str | None = None,
) -> tuple[RedisStreamEntry, ForwardEventWorkItem]:
    event_fingerprint = content_digest(canonical)
    payload_digest = content_digest(
        {
            "event_fingerprint": event_fingerprint,
            "replay_plan_fingerprint": replay_plan_fingerprint,
        }
    )
    request = DispatchRequest(
        idempotency_key="forward-event-1",
        attempt_id="forward-instance-1",
        payload_digest=payload_digest,
        queue_name="strategy-lab:v2:forward-events",
        created_at=EVENT_TIME + timedelta(seconds=2),
    )
    dispatch = ForwardEventDispatchRecord(
        owner_id="owner-1",
        instance_id="forward-instance-1",
        event_fingerprint=event_fingerprint,
        request=request,
        replay_plan_fingerprint=replay_plan_fingerprint,
        pre_event_checkpoint_fingerprint=content_digest("checkpoint-before-event"),
        warmup_receipt_fingerprint=content_digest("warmup-receipt"),
        admission_decision=admission_decision,
    )
    entry = RedisStreamEntry(
        stream_key=request.queue_name,
        stream_id="1704205800000-0",
        message_id=request.fingerprint,
        attempt_id=request.attempt_id,
        payload_digest=request.payload_digest,
        request_fingerprint=request.fingerprint,
    )
    work_item = ForwardEventWorkItem(
        dispatch,
        ForwardEventDispatchPayload(event_fingerprint, replay_plan_fingerprint),
    )
    return entry, work_item


class _StaticPayloadResolver:
    def __init__(self, payload: VerifiedForwardMarketPayload) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    def __call__(self, *, instance_id: str, event_fingerprint: str) -> VerifiedForwardMarketPayload:
        self.calls.append((instance_id, event_fingerprint))
        return self.payload


@pytest.mark.asyncio
async def test_callback_factory_authenticates_dispatch_and_builds_one_event_tape() -> None:
    canonical = _canonical_event()
    payload = VerifiedForwardMarketPayload(
        canonical,
        _market_event(canonical),
        canonical.source_digest,
    )
    resolver = _StaticPayloadResolver(payload)
    factory = create_nautilus_forward_delivery_callback_factory(
        resolver,
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    entry, work_item = _redis_work_item(canonical)

    result = await factory(entry, work_item)

    assert isinstance(result, NautilusForwardDeliveryInput)
    assert result.verified_market_payload == payload
    assert resolver.calls == [("forward-instance-1", content_digest(canonical))]
    assert result.delivery_binding.event_fingerprint == content_digest(canonical)
    assert result.delivery_binding.redis_entry_fingerprint == entry.fingerprint
    assert result.tape.instance_id == "forward-instance-1"
    assert len(result.tape.envelopes) == 1
    assert result.tape.envelopes[0].canonical_event == canonical
    assert result.tape.envelopes[0].record.event_type == "ohlcv"
    assert result.tape.envelopes[0].record.values["close"] == 101
    assert result.market_event == payload.market_event
    assert result.verified_source_digest == canonical.source_digest
    assert result.fingerprint == content_digest(result)


@pytest.mark.asyncio
async def test_context_preparation_preserves_the_authenticated_checkpoint_binding() -> None:
    canonical = _canonical_event()
    payload = VerifiedForwardMarketPayload(
        canonical,
        _market_event(canonical),
        canonical.source_digest,
    )
    factory = create_nautilus_forward_delivery_callback_factory(
        _StaticPayloadResolver(payload),
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    entry, work_item = _redis_work_item(canonical)
    delivery = await factory(entry, work_item)
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=EVENT_TIME - timedelta(days=1),
        end=EVENT_TIME + timedelta(days=1),
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="XNYS.regular",
        feed="consolidated",
        execution_model="bar-close",
        account_model="cash",
        corporate_action_semantics="split-adjusted-v1",
    )
    manifest = StrategySdkManifest(
        StrategyVersion("strategy-1", "version-1", "2.0", content_digest(STRATEGY_SOURCE)),
        (
            StrategyDataDependency(
                "daily-bars",
                requirement,
                ("open", "high", "low", "close", "volume"),
                lookback_periods=2,
            ),
        ),
    )
    window = ForwardStrategyContextWindow(
        "forward-instance-1", manifest, parameters={}, random_seed=19
    )
    initial_fingerprint = window.window_fingerprint

    preparation = window.prepare_delivery(delivery)

    assert preparation.payload_fingerprint == payload.fingerprint
    assert preparation.delivery_binding_fingerprint == delivery.delivery_binding.fingerprint
    assert preparation.dispatch_fingerprint == delivery.delivery_binding.dispatch_record_fingerprint
    assert (
        preparation.pre_event_checkpoint_fingerprint
        == delivery.delivery_binding.pre_event_checkpoint_fingerprint
    )
    assert (
        preparation.warmup_receipt_fingerprint
        == delivery.delivery_binding.warmup_receipt_fingerprint
    )
    assert preparation.context.market_events["daily-bars"] == (payload.market_event,)
    assert window.window_fingerprint == initial_fingerprint


@pytest.mark.asyncio
async def test_callback_factory_rejects_a_resolved_event_for_another_dispatch() -> None:
    canonical = _canonical_event()
    changed = _canonical_event(source_digest=content_digest("different-source"))
    resolver = _StaticPayloadResolver(
        VerifiedForwardMarketPayload(changed, _market_event(changed), changed.source_digest)
    )
    factory = create_nautilus_forward_delivery_callback_factory(
        resolver,
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    entry, work_item = _redis_work_item(canonical)

    with pytest.raises(ValueError, match="does not match the accepted dispatch"):
        await factory(entry, work_item)


@pytest.mark.asyncio
@pytest.mark.parametrize("decision", ["buffered", "correction_enqueue"])
async def test_callback_factory_never_routes_buffered_or_corrected_events_live(
    decision: str,
) -> None:
    canonical = _canonical_event()
    resolver = _StaticPayloadResolver(
        VerifiedForwardMarketPayload(canonical, _market_event(canonical), canonical.source_digest)
    )
    factory = create_nautilus_forward_delivery_callback_factory(
        resolver,
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    replay_fingerprint = (
        content_digest("correction-plan") if decision == "correction_enqueue" else None
    )
    entry, work_item = _redis_work_item(
        canonical,
        admission_decision=decision,
        replay_plan_fingerprint=replay_fingerprint,
    )

    with pytest.raises(ValueError, match="only accepted non-correction dispatches"):
        await factory(entry, work_item)

    assert resolver.calls == []


@pytest.mark.asyncio
async def test_callback_factory_rejects_missing_dependency_type_before_runtime_handoff() -> None:
    canonical = _canonical_event()
    resolver = _StaticPayloadResolver(
        VerifiedForwardMarketPayload(canonical, _market_event(canonical), canonical.source_digest)
    )
    factory = create_nautilus_forward_delivery_callback_factory(
        resolver,
        event_type_by_dependency={"other-bars": "ohlcv"},
    )
    entry, work_item = _redis_work_item(canonical)

    with pytest.raises(ValueError, match="no declared Nautilus event type"):
        await factory(entry, work_item)
