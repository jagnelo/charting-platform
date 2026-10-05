from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

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
from app.strategy_lab_v2.forward_account import ForwardAccountEvent, initial_forward_account_state
from app.strategy_lab_v2.forward_account_worker import ForwardAccountEventBinding
from app.strategy_lab_v2.forward_context import ForwardStrategyContextWindow
from app.strategy_lab_v2.forward_worker_handoff import (
    ForwardEventDispatchPayload,
    ForwardEventWorkItem,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_forward_delivery import (
    VerifiedForwardMarketPayload,
    create_nautilus_forward_delivery_callback_factory,
)
from app.strategy_lab_v2.nautilus_forward_session import (
    NautilusForwardExecutionResult,
    NautilusForwardSessionEventHandler,
    ResolvedForwardContextWindow,
)
from app.strategy_lab_v2.postgres_forward_account import (
    ForwardAccountStateDecision,
    ForwardAccountStateResolution,
)
from app.strategy_lab_v2.postgres_forward_dispatch import ForwardEventDispatchRecord
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.sdk import MarketEvent, StrategyDataDependency, StrategySdkManifest
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision

NOW = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
STRATEGY_SOURCE = "class Strategy:\n    def on_event(self, context):\n        return []\n"
INSTANCE_ID = "forward-1"
OWNER_ID = "owner-1"


def _canonical() -> CanonicalForwardEvent:
    source_digest = content_digest("bar-source")
    return CanonicalForwardEvent(
        "bar-1",
        1,
        NOW,
        NOW + timedelta(seconds=1),
        source_digest,
    )


def _payload(canonical: CanonicalForwardEvent) -> VerifiedForwardMarketPayload:
    return VerifiedForwardMarketPayload(
        canonical,
        MarketEvent(
            "daily-bars",
            canonical.event_id,
            "US.AAPL",
            canonical.event_time,
            canonical.sequence,
            {"open": 100, "high": 102, "low": 99, "close": 101, "volume": 1200},
        ),
        canonical.source_digest,
    )


def _dispatch(
    canonical: CanonicalForwardEvent,
) -> tuple[RedisStreamEntry, ForwardEventWorkItem]:
    event_fingerprint = content_digest(canonical)
    request = DispatchRequest(
        "event-key-1",
        INSTANCE_ID,
        content_digest({"event_fingerprint": event_fingerprint, "replay_plan_fingerprint": None}),
        "strategy-lab:v2:forward-events",
        NOW + timedelta(seconds=2),
    )
    record = ForwardEventDispatchRecord(
        OWNER_ID,
        INSTANCE_ID,
        event_fingerprint,
        request,
        pre_event_checkpoint_fingerprint=content_digest("account-before-event"),
        warmup_receipt_fingerprint=content_digest("warmup"),
        admission_decision="enqueue",
    )
    entry = RedisStreamEntry(
        request.queue_name,
        "1704205800000-0",
        request.fingerprint,
        request.attempt_id,
        request.payload_digest,
        request.fingerprint,
    )
    return entry, ForwardEventWorkItem(record, ForwardEventDispatchPayload(event_fingerprint))


def _manifest() -> StrategySdkManifest:
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=NOW - timedelta(days=1),
        end=NOW + timedelta(days=1),
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="XNYS.regular",
        feed="consolidated",
        execution_model="bar-close",
        account_model="cash",
        corporate_action_semantics="split-adjusted-v1",
    )
    return StrategySdkManifest(
        StrategyVersion("strategy-1", "version-1", "2.0", content_digest(STRATEGY_SOURCE)),
        (
            StrategyDataDependency(
                "daily-bars",
                requirement,
                ("open", "high", "low", "close", "volume"),
                1,
            ),
        ),
    )


class PayloadResolver:
    def __init__(self, payload: VerifiedForwardMarketPayload) -> None:
        self.payload = payload

    def __call__(self, *, instance_id: str, event_fingerprint: str):
        assert instance_id == INSTANCE_ID
        assert event_fingerprint == content_digest(self.payload.canonical_event)
        return self.payload


class AccountStore:
    def __init__(
        self,
        resolution: ForwardAccountStateResolution,
        order: list[str],
    ) -> None:
        self.resolution = resolution
        self.order = order
        self.events: list[ForwardAccountEvent] = []

    async def apply(self, *, principal: Any, event: ForwardAccountEvent):
        assert principal == OWNER_ID
        self.order.append("persist")
        self.events.append(event)
        return self.resolution


class Runtime:
    def __init__(self, order: list[str], *, mismatch_context: bool = False) -> None:
        self.order = order
        self.mismatch_context = mismatch_context
        self.restore_calls: list[tuple[str, str]] = []
        self.fail_execution = False

    def execute(self, delivery, preparation) -> NautilusForwardExecutionResult:
        self.order.append("execute")
        if self.fail_execution:
            raise RuntimeError("simulated native runtime failure")
        canonical = delivery.tape.envelopes[0].canonical_event
        event = ForwardAccountEvent(
            INSTANCE_ID,
            canonical.event_id,
            content_digest(canonical),
            canonical.sequence,
            canonical.event_time,
        )
        event_binding = ForwardAccountEventBinding(canonical, event)
        return NautilusForwardExecutionResult(
            delivery.delivery_binding.fingerprint,
            content_digest("wrong-context") if self.mismatch_context else preparation.fingerprint,
            delivery.delivery_binding.pre_event_checkpoint_fingerprint,
            content_digest("runtime-session"),
            event_binding.fingerprint,
            event_binding,
        )

    async def restore(self, *, instance_id: str, checkpoint_fingerprint: str) -> None:
        self.order.append("restore")
        self.restore_calls.append((instance_id, checkpoint_fingerprint))


def _window() -> ForwardStrategyContextWindow:
    return ForwardStrategyContextWindow(
        INSTANCE_ID,
        _manifest(),
        parameters={},
        random_seed=7,
    )


def _handler(
    canonical: CanonicalForwardEvent,
    window: ForwardStrategyContextWindow,
    runtime: Runtime,
    store: AccountStore,
) -> NautilusForwardSessionEventHandler:
    delivery_factory = create_nautilus_forward_delivery_callback_factory(
        PayloadResolver(_payload(canonical)),
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    return NautilusForwardSessionEventHandler(
        delivery_factory,
        lambda delivery: ResolvedForwardContextWindow(
            window,
            delivery.delivery_binding.pre_event_checkpoint_fingerprint,
            delivery.delivery_binding.warmup_receipt_fingerprint,
        ),
        runtime,
        store,
        principal=OWNER_ID,
    )


@pytest.mark.asyncio
async def test_forward_session_persists_native_effects_before_context_commit_and_complete() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    state = initial_forward_account_state(INSTANCE_ID, base_currency="USD")
    order: list[str] = []
    window = _window()
    runtime = Runtime(order)
    store = AccountStore(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            state,
            content_digest(canonical),
        ),
        order,
    )

    result = await _handler(canonical, window, runtime, store)(entry, work_item)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert result.receipt_digest is not None
    assert order == ["execute", "persist"]
    assert len(store.events) == 1
    assert window.last_event_key == (canonical.event_time, canonical.sequence)
    assert runtime.restore_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("checkpoint_fingerprint", "warmup_fingerprint"),
    [
        (content_digest("wrong-checkpoint"), content_digest("warmup")),
        (content_digest("account-before-event"), content_digest("wrong-warmup")),
    ],
)
async def test_unmatched_context_checkpoint_never_reaches_native_runtime(
    checkpoint_fingerprint: str,
    warmup_fingerprint: str,
) -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    order: list[str] = []
    window = _window()
    runtime = Runtime(order)
    store = AccountStore(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            initial_forward_account_state(INSTANCE_ID, base_currency="USD"),
            content_digest(canonical),
        ),
        order,
    )
    delivery_factory = create_nautilus_forward_delivery_callback_factory(
        PayloadResolver(_payload(canonical)),
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    handler = NautilusForwardSessionEventHandler(
        delivery_factory,
        lambda _delivery: ResolvedForwardContextWindow(
            window,
            checkpoint_fingerprint,
            warmup_fingerprint,
        ),
        runtime,
        store,
        principal=OWNER_ID,
    )

    result = await handler(entry, work_item)

    assert result.decision is WorkerHandleDecision.RETRY
    assert (
        result.rejection_reason
        == "forward context window is not at the authenticated pre-event state"
    )
    assert order == []
    assert runtime.restore_calls == []
    assert store.events == []


@pytest.mark.asyncio
async def test_retryable_account_state_restores_runtime_and_discards_context() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    order: list[str] = []
    window = _window()
    runtime = Runtime(order)
    store = AccountStore(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.OUT_OF_ORDER,
            None,
            content_digest(canonical),
            "account checkpoint has a sequence gap",
        ),
        order,
    )

    result = await _handler(canonical, window, runtime, store)(entry, work_item)

    assert result.decision is WorkerHandleDecision.RETRY
    assert order == ["execute", "persist", "restore"]
    assert runtime.restore_calls == [
        (INSTANCE_ID, work_item.dispatch.pre_event_checkpoint_fingerprint)
    ]
    assert window.last_event_key is None
    assert not store.events == []


@pytest.mark.asyncio
async def test_runtime_failure_restores_checkpoint_without_persisting_account_effects() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    order: list[str] = []
    window = _window()
    runtime = Runtime(order)
    runtime.fail_execution = True
    store = AccountStore(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            initial_forward_account_state(INSTANCE_ID, base_currency="USD"),
            content_digest(canonical),
        ),
        order,
    )

    result = await _handler(canonical, window, runtime, store)(entry, work_item)

    assert result.decision is WorkerHandleDecision.RETRY
    assert order == ["execute", "restore"]
    assert runtime.restore_calls == [
        (INSTANCE_ID, work_item.dispatch.pre_event_checkpoint_fingerprint)
    ]
    assert window.last_event_key is None
    assert store.events == []


@pytest.mark.asyncio
async def test_execution_receipt_mismatch_is_rejected_after_runtime_recovery() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    order: list[str] = []
    window = _window()
    runtime = Runtime(order, mismatch_context=True)
    store = AccountStore(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            initial_forward_account_state(INSTANCE_ID, base_currency="USD"),
            content_digest(canonical),
        ),
        order,
    )

    result = await _handler(canonical, window, runtime, store)(entry, work_item)

    assert result.decision is WorkerHandleDecision.REJECT
    assert order == ["execute", "restore"]
    assert runtime.restore_calls == [
        (INSTANCE_ID, work_item.dispatch.pre_event_checkpoint_fingerprint)
    ]
    assert window.last_event_key is None
    assert store.events == []


@pytest.mark.asyncio
async def test_buffered_and_corrected_events_never_enter_the_live_native_session() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    order: list[str] = []
    runtime = Runtime(order)
    store = AccountStore(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            initial_forward_account_state(INSTANCE_ID, base_currency="USD"),
            content_digest(canonical),
        ),
        order,
    )
    handler = _handler(canonical, _window(), runtime, store)

    buffered = replace(
        work_item,
        dispatch=replace(work_item.dispatch, admission_decision="buffered"),
    )
    buffered_result = await handler(entry, buffered)
    replay_plan_fingerprint = content_digest("counterfactual-replay")
    correction = replace(
        work_item,
        dispatch=replace(
            work_item.dispatch,
            admission_decision="correction_enqueue",
            replay_plan_fingerprint=replay_plan_fingerprint,
        ),
        payload=replace(
            work_item.payload,
            replay_plan_fingerprint=replay_plan_fingerprint,
        ),
    )
    correction_result = await handler(entry, correction)

    assert buffered_result.decision is WorkerHandleDecision.RETRY
    assert correction_result.decision is WorkerHandleDecision.REJECT
    assert order == []
    assert store.events == []
