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
    EventGranularity,
    ProductClass,
    StrategyVersion,
)
from app.strategy_lab_v2.dispatch import DispatchRequest
from app.strategy_lab_v2.forward_account import (
    ForwardAccountEvent,
    ForwardAccountHistoryEntry,
    ForwardRuntimeExecutionReceipt,
    apply_forward_account_event,
    initial_forward_account_state,
)
from app.strategy_lab_v2.forward_account_worker import ForwardAccountEventBinding
from app.strategy_lab_v2.forward_context import (
    ForwardPortfolioContextPreparation,
    ForwardStrategyContextWindow,
)
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
    AuthenticatedForwardPortfolioContextWindowResolver,
    NautilusForwardExecutionResult,
    NautilusForwardSessionEventHandler,
    NautilusForwardSessionRuntime,
    PersistentNautilusForwardSessionRuntime,
    ResolvedForwardContextWindow,
    ResolvedForwardPortfolioContextWindows,
)
from app.strategy_lab_v2.postgres_forward_account import (
    ForwardAccountStateDecision,
    ForwardAccountStateResolution,
)
from app.strategy_lab_v2.postgres_forward_dispatch import ForwardEventDispatchRecord
from app.strategy_lab_v2.redis_transport import RedisStreamEntry
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    PositionSnapshot,
    StrategyDataDependency,
    StrategySdkManifest,
)
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
    *,
    pre_event_checkpoint_fingerprint: str | None = None,
) -> tuple[RedisStreamEntry, ForwardEventWorkItem]:
    event_fingerprint = content_digest(canonical)
    request = DispatchRequest(
        f"event-key-{canonical.sequence}",
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
        pre_event_checkpoint_fingerprint=(
            content_digest("account-before-event")
            if pre_event_checkpoint_fingerprint is None
            else pre_event_checkpoint_fingerprint
        ),
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


def _manifest(dependency_id: str = "daily-bars") -> StrategySdkManifest:
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
                dependency_id,
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
        self.receipts: list[ForwardRuntimeExecutionReceipt] = []
        self.existing_settlements: dict[str, ForwardAccountHistoryEntry] = {}

    async def load_event_settlement(
        self,
        *,
        principal: Any,
        instance_id: str,
        event_id: str,
    ) -> ForwardAccountHistoryEntry | None:
        assert principal == OWNER_ID
        return self.existing_settlements.get(f"{instance_id}:{event_id}")

    async def apply(
        self,
        *,
        principal: Any,
        event: ForwardAccountEvent,
        execution_receipt: ForwardRuntimeExecutionReceipt | None = None,
    ):
        assert principal == OWNER_ID
        self.order.append("persist")
        self.events.append(event)
        if self.resolution.decision not in {
            ForwardAccountStateDecision.APPLIED,
            ForwardAccountStateDecision.REPLAY_EXISTING,
        }:
            return self.resolution
        if self.resolution.state is None:
            return self.resolution
        if execution_receipt is not None:
            self.receipts.append(execution_receipt)
        applied = apply_forward_account_event(
            self.resolution.state,
            event,
            execution_receipt=execution_receipt,
        )
        if applied.state is None:
            return self.resolution
        self.resolution = ForwardAccountStateResolution(
            ForwardAccountStateDecision(applied.decision.value),
            applied.state,
            event.event_fingerprint,
            execution_receipt_fingerprint=(
                execution_receipt.fingerprint if execution_receipt is not None else None
            ),
        )
        return self.resolution


class Runtime:
    def __init__(self, order: list[str], *, mismatch_context: bool = False) -> None:
        self.order = order
        self.mismatch_context = mismatch_context
        self.restore_calls: list[tuple[str, str]] = []
        self.preparations: list[Any] = []
        self.fail_execution = False

    def execute(self, delivery, preparation) -> NautilusForwardExecutionResult:
        self.order.append("execute")
        self.preparations.append(preparation)
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


class PersistentProcess(Runtime):
    def __init__(self, instance_id: str, checkpoint_fingerprint: str, order: list[str]) -> None:
        super().__init__(order)
        self.instance_id = instance_id
        self.base_checkpoint_fingerprint = checkpoint_fingerprint
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1
        self.order.append("close")


class PersistentProcessFactory:
    def __init__(self, order: list[str]) -> None:
        self.order = order
        self.processes: list[PersistentProcess] = []
        self.start_calls: list[tuple[str, str]] = []
        self.fail_execution = False

    async def start(self, *, instance_id: str, checkpoint_fingerprint: str) -> PersistentProcess:
        self.start_calls.append((instance_id, checkpoint_fingerprint))
        process = PersistentProcess(instance_id, checkpoint_fingerprint, self.order)
        process.fail_execution = self.fail_execution
        self.processes.append(process)
        return process


def _window(
    manifest: StrategySdkManifest | None = None,
) -> ForwardStrategyContextWindow:
    return ForwardStrategyContextWindow(
        INSTANCE_ID,
        _manifest() if manifest is None else manifest,
        parameters={},
        random_seed=7,
    )


def _handler(
    canonical: CanonicalForwardEvent,
    window: ForwardStrategyContextWindow,
    runtime: NautilusForwardSessionRuntime,
    store: AccountStore,
    *,
    positions: dict[str, PositionSnapshot] | None = None,
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
            {} if positions is None else positions,
        ),
        runtime,
        store,
        principal=OWNER_ID,
    )


def _portfolio_handler(
    canonical: CanonicalForwardEvent,
    windows: dict[str, ForwardStrategyContextWindow],
    runtime: NautilusForwardSessionRuntime,
    store: AccountStore,
    *,
    positions: dict[str, PositionSnapshot] | None = None,
) -> NautilusForwardSessionEventHandler:
    delivery_factory = create_nautilus_forward_delivery_callback_factory(
        PayloadResolver(_payload(canonical)),
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )

    def resolve(delivery) -> ResolvedForwardPortfolioContextWindows:
        shared_positions = {} if positions is None else positions
        components = {
            component_id: ResolvedForwardContextWindow(
                window,
                delivery.delivery_binding.pre_event_checkpoint_fingerprint,
                delivery.delivery_binding.warmup_receipt_fingerprint,
                shared_positions,
            )
            for component_id, window in windows.items()
        }
        return ResolvedForwardPortfolioContextWindows(
            components,
            delivery.delivery_binding.pre_event_checkpoint_fingerprint,
            delivery.delivery_binding.warmup_receipt_fingerprint,
            shared_positions,
        )

    return NautilusForwardSessionEventHandler(
        delivery_factory,
        resolve,
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
    assert len(store.receipts) == 1
    assert store.receipts[0].event_fingerprint == content_digest(canonical)
    assert store.receipts[0].pre_event_checkpoint_fingerprint == content_digest(
        "account-before-event"
    )
    assert window.last_event_key == (canonical.event_time, canonical.sequence)
    assert runtime.restore_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ("valid", "wrong_binding", "missing_receipt"))
async def test_forward_redelivery_uses_durable_receipt_without_native_execution(
    scenario: str,
) -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    delivery_factory = create_nautilus_forward_delivery_callback_factory(
        PayloadResolver(_payload(canonical)),
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    delivery = await delivery_factory(entry, work_item)
    event = ForwardAccountEvent(
        INSTANCE_ID,
        canonical.event_id,
        content_digest(canonical),
        canonical.sequence,
        canonical.event_time,
    )
    initial = initial_forward_account_state(INSTANCE_ID, base_currency="USD")
    execution_receipt = ForwardRuntimeExecutionReceipt(
        INSTANCE_ID,
        canonical.event_id,
        content_digest(canonical),
        delivery.delivery_binding.fingerprint,
        content_digest("prior-context-preparation"),
        delivery.delivery_binding.pre_event_checkpoint_fingerprint,
        content_digest("persisted-runtime-session"),
        content_digest("persisted-native-output"),
    )
    settled = apply_forward_account_event(
        initial,
        event,
        execution_receipt=execution_receipt,
    )
    assert settled.state is not None
    stored_receipt: ForwardRuntimeExecutionReceipt | None = execution_receipt
    if scenario == "wrong_binding":
        stored_receipt = replace(
            execution_receipt,
            delivery_binding_fingerprint=content_digest("different-delivery"),
        )
    elif scenario == "missing_receipt":
        stored_receipt = None
    history = ForwardAccountHistoryEntry(
        1,
        initial.fingerprint,
        settled.state.fingerprint,
        event=event,
        execution_receipt=stored_receipt,
    )
    order: list[str] = []
    store = AccountStore(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.REPLAY_EXISTING,
            settled.state,
            event.event_fingerprint,
            execution_receipt_fingerprint=execution_receipt.fingerprint,
        ),
        order,
    )
    store.existing_settlements[f"{INSTANCE_ID}:{canonical.event_id}"] = history
    window = _window()
    runtime = Runtime(order)

    result = await _handler(canonical, window, runtime, store)(entry, work_item)

    expected = WorkerHandleDecision.COMPLETE if scenario == "valid" else WorkerHandleDecision.REJECT
    assert result.decision is expected
    if scenario == "valid":
        assert result.receipt_digest is not None
        assert order == ["persist"]
        assert store.receipts == [execution_receipt]
    else:
        assert result.receipt_digest is None
        assert order == []
        assert store.receipts == []
    assert len(runtime.preparations) == 0
    assert window.last_event_key is None


@pytest.mark.asyncio
async def test_persistent_native_runtime_reuses_one_process_and_deduplicates_latest_delivery() -> (
    None
):
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    delivery_factory = create_nautilus_forward_delivery_callback_factory(
        PayloadResolver(_payload(canonical)),
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    delivery = await delivery_factory(entry, work_item)
    window = _window()
    preparation = window.prepare_delivery(delivery)
    order: list[str] = []
    factory = PersistentProcessFactory(order)
    runtime = PersistentNautilusForwardSessionRuntime(factory)

    first = await runtime.execute(delivery, preparation)
    replay = await runtime.execute(delivery, preparation)

    next_canonical = replace(
        canonical,
        event_id="bar-2",
        sequence=2,
        event_time=canonical.event_time + timedelta(seconds=1),
        arrived_at=canonical.arrived_at + timedelta(seconds=1),
    )
    next_checkpoint = content_digest("account-after-first-event")
    next_entry, next_work_item = _dispatch(
        next_canonical,
        pre_event_checkpoint_fingerprint=next_checkpoint,
    )
    next_delivery_factory = create_nautilus_forward_delivery_callback_factory(
        PayloadResolver(_payload(next_canonical)),
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    next_delivery = await next_delivery_factory(next_entry, next_work_item)
    window.commit(preparation)
    next_preparation = window.prepare_delivery(next_delivery)
    await runtime.execute(next_delivery, next_preparation)

    assert first == replay
    assert factory.start_calls == [
        (INSTANCE_ID, work_item.dispatch.pre_event_checkpoint_fingerprint),
        (INSTANCE_ID, next_checkpoint),
    ]
    assert len(factory.processes[0].preparations) == 1
    assert len(factory.processes[1].preparations) == 1
    assert factory.processes[0].close_calls == 1
    assert order == ["execute", "close", "execute"]

    await runtime.close(instance_id=INSTANCE_ID)

    assert factory.processes[1].close_calls == 1
    assert order == ["execute", "close", "execute", "close"]


@pytest.mark.asyncio
async def test_persistent_native_runtime_restore_clears_only_volatile_idempotency_cache() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    delivery_factory = create_nautilus_forward_delivery_callback_factory(
        PayloadResolver(_payload(canonical)),
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    delivery = await delivery_factory(entry, work_item)
    preparation = _window().prepare_delivery(delivery)
    order: list[str] = []
    factory = PersistentProcessFactory(order)
    runtime = PersistentNautilusForwardSessionRuntime(factory)

    first = await runtime.execute(delivery, preparation)
    checkpoint_fingerprint = work_item.dispatch.pre_event_checkpoint_fingerprint
    assert checkpoint_fingerprint is not None
    await runtime.restore(
        instance_id=INSTANCE_ID,
        checkpoint_fingerprint=checkpoint_fingerprint,
    )
    replayed = await runtime.execute(delivery, preparation)

    process = factory.processes[-1]
    assert replayed == first
    assert factory.start_calls == [
        (INSTANCE_ID, work_item.dispatch.pre_event_checkpoint_fingerprint),
        (INSTANCE_ID, work_item.dispatch.pre_event_checkpoint_fingerprint),
    ]
    assert factory.processes[0].close_calls == 1
    assert len(process.preparations) == 1
    assert order == ["execute", "close", "execute"]
    await runtime.close_all()


@pytest.mark.asyncio
async def test_portfolio_components_share_one_native_event_and_commit_together() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    order: list[str] = []
    windows = {"alpha": _window(), "beta": _window()}
    process_factory = PersistentProcessFactory(order)
    runtime = PersistentNautilusForwardSessionRuntime(process_factory)
    store = AccountStore(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            initial_forward_account_state(INSTANCE_ID, base_currency="USD"),
            content_digest(canonical),
        ),
        order,
    )

    result = await _portfolio_handler(canonical, windows, runtime, store)(entry, work_item)

    assert result.decision is WorkerHandleDecision.COMPLETE
    assert order == ["execute", "persist"]
    assert len(store.events) == 1
    assert process_factory.start_calls == [
        (INSTANCE_ID, work_item.dispatch.pre_event_checkpoint_fingerprint)
    ]
    process = process_factory.processes[0]
    assert len(process.preparations) == 1
    preparation = process.preparations[0]
    assert isinstance(preparation, ForwardPortfolioContextPreparation)
    assert set(preparation.component_preparations) == {"alpha", "beta"}
    assert windows["alpha"].last_event_key == (canonical.event_time, canonical.sequence)
    assert windows["beta"].last_event_key == (canonical.event_time, canonical.sequence)
    await runtime.close_all()


@pytest.mark.asyncio
async def test_portfolio_event_advances_only_components_declaring_its_dependency() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    order: list[str] = []
    windows = {"matching": _window(), "unrelated": _window(_manifest("minute-bars"))}
    runtime = Runtime(order)
    store = AccountStore(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            initial_forward_account_state(INSTANCE_ID, base_currency="USD"),
            content_digest(canonical),
        ),
        order,
    )

    result = await _portfolio_handler(canonical, windows, runtime, store)(entry, work_item)

    assert result.decision is WorkerHandleDecision.COMPLETE
    preparation = runtime.preparations[0]
    assert isinstance(preparation, ForwardPortfolioContextPreparation)
    assert set(preparation.component_preparations) == {"matching"}
    assert windows["matching"].last_event_key == (canonical.event_time, canonical.sequence)
    assert windows["unrelated"].last_event_key is None


@pytest.mark.asyncio
async def test_portfolio_runtime_failure_restores_once_and_discards_every_component() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    order: list[str] = []
    windows = {"alpha": _window(), "beta": _window()}
    process_factory = PersistentProcessFactory(order)
    process_factory.fail_execution = True
    runtime = PersistentNautilusForwardSessionRuntime(process_factory)
    store = AccountStore(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            initial_forward_account_state(INSTANCE_ID, base_currency="USD"),
            content_digest(canonical),
        ),
        order,
    )

    result = await _portfolio_handler(canonical, windows, runtime, store)(entry, work_item)

    assert result.decision is WorkerHandleDecision.RETRY
    assert order == ["execute", "close"]
    assert len(process_factory.processes) == 2
    assert process_factory.processes[0].close_calls == 1
    assert process_factory.start_calls == [
        (INSTANCE_ID, work_item.dispatch.pre_event_checkpoint_fingerprint),
        (INSTANCE_ID, work_item.dispatch.pre_event_checkpoint_fingerprint),
    ]
    assert all(window.last_event_key is None for window in windows.values())
    assert store.events == []
    await runtime.close_all()


def test_resolved_portfolio_context_rejects_component_account_divergence() -> None:
    checkpoint = content_digest("checkpoint")
    warmup = content_digest("warmup")
    position = PositionSnapshot("US.AAPL", Decimal("3"), Decimal("99"), None)
    first = ResolvedForwardContextWindow(_window(), checkpoint, warmup, {"US.AAPL": position})
    second = ResolvedForwardContextWindow(_window(), checkpoint, warmup)

    with pytest.raises(ValueError, match="same checkpoint and account"):
        ResolvedForwardPortfolioContextWindows(
            {"alpha": first, "beta": second},
            checkpoint,
            warmup,
            {"US.AAPL": position},
        )


@pytest.mark.asyncio
async def test_authenticated_portfolio_resolver_aligns_components_to_one_checkpoint() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    delivery_factory = create_nautilus_forward_delivery_callback_factory(
        PayloadResolver(_payload(canonical)),
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    delivery = await delivery_factory(entry, work_item)
    positions = {"US.AAPL": PositionSnapshot("US.AAPL", Decimal("2"), Decimal("100"), None)}

    async def resolve_beta(_delivery):
        return ResolvedForwardContextWindow(
            _window(),
            delivery.delivery_binding.pre_event_checkpoint_fingerprint,
            delivery.delivery_binding.warmup_receipt_fingerprint,
            positions,
        )

    resolver = AuthenticatedForwardPortfolioContextWindowResolver(
        {
            "beta": resolve_beta,
            "alpha": lambda _delivery: ResolvedForwardContextWindow(
                _window(),
                delivery.delivery_binding.pre_event_checkpoint_fingerprint,
                delivery.delivery_binding.warmup_receipt_fingerprint,
                positions,
            ),
        }
    )

    result = await resolver(delivery)

    assert tuple(result.component_windows) == ("alpha", "beta")
    assert result.pre_event_checkpoint_fingerprint == (
        delivery.delivery_binding.pre_event_checkpoint_fingerprint
    )
    assert dict(result.positions) == positions


@pytest.mark.asyncio
async def test_authenticated_portfolio_resolver_rejects_checkpoint_divergence() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    delivery_factory = create_nautilus_forward_delivery_callback_factory(
        PayloadResolver(_payload(canonical)),
        event_type_by_dependency={"daily-bars": "ohlcv"},
    )
    delivery = await delivery_factory(entry, work_item)
    resolver = AuthenticatedForwardPortfolioContextWindowResolver(
        {
            "alpha": lambda _delivery: ResolvedForwardContextWindow(
                _window(),
                delivery.delivery_binding.pre_event_checkpoint_fingerprint,
                delivery.delivery_binding.warmup_receipt_fingerprint,
            ),
            "beta": lambda _delivery: ResolvedForwardContextWindow(
                _window(),
                content_digest("wrong-checkpoint"),
                delivery.delivery_binding.warmup_receipt_fingerprint,
            ),
        }
    )

    with pytest.raises(ValueError, match="different checkpoint/account state"):
        await resolver(delivery)


@pytest.mark.asyncio
async def test_forward_session_passes_persisted_positions_into_the_staged_sdk_context() -> None:
    canonical = _canonical()
    entry, work_item = _dispatch(canonical)
    order: list[str] = []
    runtime = Runtime(order)
    positions = {"US.AAPL": PositionSnapshot("US.AAPL", Decimal("3"), Decimal("99"), None)}
    store = AccountStore(
        ForwardAccountStateResolution(
            ForwardAccountStateDecision.APPLIED,
            initial_forward_account_state(INSTANCE_ID, base_currency="USD"),
            content_digest(canonical),
        ),
        order,
    )

    result = await _handler(
        canonical,
        _window(),
        runtime,
        store,
        positions=positions,
    )(entry, work_item)

    assert result.decision is WorkerHandleDecision.COMPLETE
    context_positions = runtime.preparations[0].context.positions
    assert context_positions == positions
    assert context_positions is not positions
    with pytest.raises(TypeError):
        context_positions["US.AAPL"] = PositionSnapshot(
            "US.AAPL", Decimal("4"), Decimal("99"), None
        )


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
