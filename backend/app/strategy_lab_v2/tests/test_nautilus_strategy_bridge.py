from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategy_lab_v2.contracts import PortfolioComponent, PortfolioComposition
from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
    _EVENT_TIME,
    _EVENT_TIME_NS,
    _manifest,
)
from app.strategy_lab_v2.nautilus_runtime_data import NautilusRuntimeDataError
from app.strategy_lab_v2.nautilus_strategy_bridge import (
    NautilusComponentFillLedger,
    _iter_context_trigger_indexes,
    _iter_replayed_component_context_trigger_groups,
    _iter_replayed_context_trigger_indexes,
    _iter_stream_component_context_trigger_groups,
    _iter_stream_context_trigger_indexes,
    _match_contexts_to_events,
    _suppress_warmup_intents,
    iter_component_context_trigger_groups,
)
from app.strategy_lab_v2.rebalance import RebalanceMisfirePolicy, RebalanceTrigger
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    OrderSide,
    StrategyContext,
    TargetPositionIntent,
)
from strategy_runtime import InvocationContextStreamBinding
from strategy_runtime.runner import InvocationStatus, StrategyInvocationResult

EVENT_TIME = datetime(2024, 1, 1, tzinfo=UTC)
EVENT_TIME_NS = 1_704_067_200_000_000_000


def _event(
    event_id: str,
    dependency_id: str,
    instrument_id: str,
    sequence: int,
    event_time: datetime = EVENT_TIME,
) -> MarketEvent:
    return MarketEvent(
        dependency_id,
        event_id,
        instrument_id,
        event_time,
        sequence,
        {"close": sequence},
    )


def _record(event: MarketEvent) -> dict[str, object]:
    return {
        "dependency_id": event.dependency_id,
        "event_id": event.event_id,
        "instrument_id": event.instrument_id,
        "event_type": "ohlcv",
        "event_time_ns": int(event.event_time.timestamp()) * 1_000_000_000,
        "sequence": event.sequence,
    }


def _context(
    sequence: int,
    events: dict[str, tuple[MarketEvent, ...]],
    event_time: datetime = EVENT_TIME,
) -> StrategyContext:
    return StrategyContext(
        event_time=event_time,
        event_sequence=sequence,
        random_seed=7,
        parameters={},
        market_events=events,
    )


def test_same_time_batch_context_runs_once_on_last_native_event() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    context = _context(2, {"prices-a": (first,), "prices-b": (second,)})

    matched = _match_contexts_to_events((context,), (_record(first), _record(second)))

    assert matched == {"event-2": context}


def test_legacy_one_context_per_event_batch_remains_supported() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    first_context = _context(1, {"prices-a": (first,)})
    second_context = _context(2, {"prices-a": (first,), "prices-b": (second,)})

    matched = _match_contexts_to_events(
        (first_context, second_context),
        (_record(first), _record(second)),
    )

    assert matched == {"event-1": first_context, "event-2": second_context}


def test_batched_context_must_include_all_events_at_its_timestamp() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    incomplete_context = _context(2, {"prices-a": (first,)})

    with pytest.raises(NautilusRuntimeDataError, match="every same-time native event"):
        _match_contexts_to_events(
            (incomplete_context,),
            (_record(first), _record(second)),
        )


def test_event_time_binding_uses_sdk_microsecond_precision_for_modern_dates() -> None:
    event = _event("event-1", "prices-a", "US.AAPL", 1)
    context = _context(1, {"prices-a": (event,)})

    matched = _match_contexts_to_events((context,), (_record(event),))

    assert matched == {"event-1": context}


def test_evaluation_warmup_invocations_cannot_publish_order_intents() -> None:
    order = TargetPositionIntent("EURUSD.SIM", Decimal("0.5"))
    result = StrategyInvocationResult(
        source_digest="sha256:" + "1" * 64,
        manifest_fingerprint="sha256:" + "2" * 64,
        context_fingerprint="sha256:" + "3" * 64,
        entrypoint="strategy.main:Strategy",
        status=InvocationStatus.SUCCEEDED,
        intents=(order,),
    )

    suppressed = _suppress_warmup_intents(
        result,
        event_time_ns=EVENT_TIME_NS,
        bounds=(EVENT_TIME_NS - 1, EVENT_TIME_NS + 1, EVENT_TIME_NS + 10_000),
    )
    evaluation = _suppress_warmup_intents(
        result,
        event_time_ns=EVENT_TIME_NS + 1,
        bounds=(EVENT_TIME_NS - 1, EVENT_TIME_NS + 1, EVENT_TIME_NS + 10_000),
    )

    assert suppressed.intents == ()
    assert evaluation.intents == (order,)


def test_stream_trigger_indexes_bind_batches_to_the_last_same_time_callback() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    context = _context(2, {"prices-a": (first,), "prices-b": (second,)})

    assert list(_iter_context_trigger_indexes((context,), (_record(first), _record(second)))) == [
        (1, context)
    ]


def test_component_context_streams_merge_by_event_then_portfolio_priority() -> None:
    core_first = _context(1, {})
    core_last = _context(4, {})
    satellite_first = _context(2, {})
    satellite_middle = _context(3, {})

    groups = iter_component_context_trigger_groups(
        {
            "core": iter(((1, core_first), (4, core_last))),
            "satellite": iter(((1, satellite_first), (3, satellite_middle))),
        },
        {"core": 10, "satellite": 2},
    )

    assert [
        (
            group.trigger_index,
            tuple((item.component_id, item.context.event_sequence) for item in group.contexts),
        )
        for group in groups
    ] == [
        (1, (("satellite", 2), ("core", 1))),
        (3, (("satellite", 3),)),
        (4, (("core", 4),)),
    ]


def test_component_context_stream_rejects_non_advancing_native_callbacks() -> None:
    contexts = iter(((2, _context(2, {})), (2, _context(3, {}))))

    with pytest.raises(NautilusRuntimeDataError, match="must advance one per native event"):
        list(iter_component_context_trigger_groups({"core": contexts}, {"core": 0}))


def test_component_context_streams_require_exact_priority_bindings() -> None:
    with pytest.raises(NautilusRuntimeDataError, match="priorities do not match"):
        list(iter_component_context_trigger_groups({"core": iter(())}, {}))


def _authenticated_quote_event(event_id: str, sequence: int, event_time: datetime) -> MarketEvent:
    return MarketEvent(
        "prices",
        event_id,
        "EURUSD.SIM",
        event_time,
        sequence,
        {"bid": "1.1000", "ask": "1.1002", "bid_size": "100", "ask_size": "100"},
    )


def _quote_record(event: MarketEvent) -> dict[str, object]:
    return {
        "dependency_id": event.dependency_id,
        "event_id": event.event_id,
        "instrument_id": event.instrument_id,
        "event_type": "quote",
        "event_time_ns": int(event.event_time.timestamp()) * 1_000_000_000,
        "sequence": event.sequence,
        "values": event.values,
    }


def test_stream_component_context_groups_share_verified_native_callbacks() -> None:
    from app.strategy_lab_v2.nautilus_runtime_adapter_probe import _SOURCE

    manifest = _manifest()
    first = _authenticated_quote_event("quote-1", 1, _EVENT_TIME)
    second = _authenticated_quote_event("quote-2", 2, _EVENT_TIME)
    third = _authenticated_quote_event("quote-3", 3, _EVENT_TIME + timedelta(seconds=1))
    first_context = StrategyContext(_EVENT_TIME, 2, 17, {}, {"prices": (first, second)})
    second_context = StrategyContext(
        _EVENT_TIME + timedelta(seconds=1),
        3,
        17,
        {},
        {"prices": (first, second, third)},
    )
    bindings = {
        component_id: InvocationContextStreamBinding(
            component_id, _SOURCE, manifest, "strategy.main:Strategy", 100
        )
        for component_id in ("core", "satellite")
    }
    contexts = iter(
        (
            ("core", first_context),
            ("satellite", first_context),
            ("core", second_context),
            ("satellite", second_context),
        )
    )
    native_records = tuple(map(_quote_record, (first, second, third)))
    priorities = {"core": 5, "satellite": 1}

    groups = list(
        _iter_stream_component_context_trigger_groups(
            contexts,
            native_records,
            bindings,
            priorities,
        )
    )

    assert [group.trigger_index for group in groups] == [1, 2]
    assert [tuple(item.component_id for item in group.contexts) for group in groups] == [
        ("satellite", "core"),
        ("satellite", "core"),
    ]
    replayed = list(
        _iter_replayed_component_context_trigger_groups(
            (
                ("core", first_context),
                ("satellite", first_context),
                ("core", second_context),
                ("satellite", second_context),
            ),
            priorities,
        )
    )
    assert [(group.trigger_index, group.contexts) for group in replayed] == [
        (group.trigger_index, group.contexts) for group in groups
    ]


def test_stream_component_context_groups_reject_manifest_history_mismatch() -> None:
    from app.strategy_lab_v2.nautilus_runtime_adapter_probe import _SOURCE

    event = _authenticated_quote_event("quote-1", 1, _EVENT_TIME)
    wrong_event = MarketEvent(
        "prices",
        "quote-wrong",
        "EURUSD.SIM",
        _EVENT_TIME,
        1,
        {"bid": "1.2000", "ask": "1.2002", "bid_size": "100", "ask_size": "100"},
    )
    binding = InvocationContextStreamBinding(
        "core", _SOURCE, _manifest(), "strategy.main:Strategy", 100
    )

    with pytest.raises(
        NautilusRuntimeDataError,
        match="differs from the authenticated event tape",
    ):
        list(
            _iter_stream_component_context_trigger_groups(
                (("core", StrategyContext(_EVENT_TIME, 1, 17, {}, {"prices": (wrong_event,)})),),
                (_quote_record(event),),
                {"core": binding},
                {"core": 0},
            )
        )


@pytest.mark.parametrize("retain_invocation_results", (True, False))
def test_native_bridge_invokes_component_contexts_by_portfolio_priority(
    monkeypatch,
    retain_invocation_results: bool,
) -> None:
    import sys
    from dataclasses import replace
    from io import BytesIO
    from types import ModuleType, SimpleNamespace
    from typing import Any

    from app.strategy_lab_v2.canonical import content_digest
    from app.strategy_lab_v2.contracts import StrategyVersion
    from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
    from app.strategy_lab_v2.nautilus_native_event_stream import (
        serialize_nautilus_native_event_stream,
    )
    from app.strategy_lab_v2.nautilus_portfolio_wire import (
        portfolio_composition_from_wire,
        portfolio_composition_to_wire,
    )
    from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
        _SOURCE,
        _invocation_batch,
        _payload,
    )
    from app.strategy_lab_v2.nautilus_strategy_bridge import build_native_strategy_bridge
    from app.strategy_lab_v2.sdk import (
        OrderIntent,
        OrderSide,
        OrderType,
        StrategySdkManifest,
        TimeInForce,
    )
    from strategy_runtime import (
        InvocationContextStreamSource,
        deserialize_invocation_batch,
        deserialize_invocation_batch_result,
        serialize_component_invocation_context_stream,
    )

    class _FromString:
        def __new__(cls, value: str) -> Any:
            return value

        @classmethod
        def from_str(cls, value: str) -> str:
            return value

    class _FakePortfolio:
        def __init__(self) -> None:
            self.cash = Decimal("10000")
            self.positions: dict[str, Decimal] = {}

        def net_position(self, _instrument_id: str) -> None:
            return self.positions.get(_instrument_id)

        def account(self, *, venue: str) -> Any:
            assert venue
            return _FakeAccount(self)

    class _FakeCurrency:
        code = "USD"

    class _FakeMoney:
        def __init__(self, amount: Decimal) -> None:
            self.amount = amount

        def as_decimal(self) -> Decimal:
            return self.amount

    class _FakeAccount:
        def __init__(self, portfolio: _FakePortfolio) -> None:
            self.portfolio = portfolio

        def balances_total(self) -> dict[_FakeCurrency, _FakeMoney]:
            return {_FakeCurrency(): _FakeMoney(self.portfolio.cash)}

    class _FakeOrderFactory:
        next_id = 0

        def market(self, **_arguments: object) -> Any:
            self.next_id += 1
            return SimpleNamespace(client_order_id=f"fake-order-{self.next_id}")

    class _FakeStrategyConfig:
        def __new__(cls, *_args: object) -> Any:
            return object.__new__(cls)

    class _FakeStrategy:
        def __init__(self, _config: object) -> None:
            self.portfolio = _FakePortfolio()
            self.order_factory = _FakeOrderFactory()
            self.submitted_orders: list[Any] = []

        def submit_order(self, order: Any) -> None:
            self.submitted_orders.append(order)

        def subscribe_quotes(self, _instrument_id: str) -> None:
            return None

        def subscribe_trades(self, _instrument_id: str) -> None:
            return None

        def subscribe_bars(self, _bar_type: str) -> None:
            return None

    class _FakeScalar:
        def __init__(self, *_args: object) -> None:
            return None

    model_module = ModuleType("nautilus_trader.model")
    for name in (
        "BarType",
        "Currency",
        "InstrumentId",
        "OrderSide",
        "StrategyId",
        "TimeInForce",
        "Venue",
    ):
        setattr(model_module, name, _FromString)
    for name in ("Price", "Quantity"):
        setattr(model_module, name, _FakeScalar)
    trading_module = ModuleType("nautilus_trader.trading")
    setattr(trading_module, "Strategy", _FakeStrategy)
    setattr(trading_module, "StrategyConfig", _FakeStrategyConfig)
    package_module = ModuleType("nautilus_trader")
    setattr(package_module, "model", model_module)
    setattr(package_module, "trading", trading_module)
    monkeypatch.setitem(sys.modules, "nautilus_trader", package_module)
    monkeypatch.setitem(sys.modules, "nautilus_trader.model", model_module)
    monkeypatch.setitem(sys.modules, "nautilus_trader.trading", trading_module)

    payload = _payload()
    source_alpha = _SOURCE
    source_beta = "\nclass Strategy:\n    def on_event(self, context):\n        return [1]\n"
    base_manifest = _manifest()

    def component_manifest(component_id: str, source: str) -> StrategySdkManifest:
        return StrategySdkManifest(
            StrategyVersion(
                component_id,
                "v1",
                "2.0",
                content_digest(source),
            ),
            base_manifest.data_dependencies,
        )

    manifest_alpha = component_manifest("alpha", source_alpha)
    manifest_beta = component_manifest("beta", source_beta)
    base_portfolio = portfolio_composition_from_wire(payload["portfolio"])
    portfolio = PortfolioComposition(
        portfolio_id="portfolio-multi-component-bridge-test",
        version_id="v1",
        initial_capital=base_portfolio.initial_capital,
        base_currency=base_portfolio.base_currency,
        components=(
            PortfolioComponent(
                "alpha",
                manifest_alpha.strategy.fingerprint,
                ("EURUSD.SIM",),
                Decimal("0.5"),
                priority=5,
            ),
            PortfolioComponent(
                "beta",
                manifest_beta.strategy.fingerprint,
                ("EURUSD.SIM",),
                Decimal("0.5"),
                priority=1,
            ),
        ),
        shared_risk_policy=base_portfolio.shared_risk_policy,
    )
    payload["portfolio"] = portfolio_composition_to_wire(portfolio)
    contexts = deserialize_invocation_batch(_invocation_batch())[2]
    context_stream = BytesIO()
    context_counts = serialize_component_invocation_context_stream(
        context_stream,
        components=(
            InvocationContextStreamSource(
                "alpha", source_alpha, manifest_alpha, contexts, "strategy.main:Strategy"
            ),
            InvocationContextStreamSource(
                "beta", source_beta, manifest_beta, contexts, "strategy.main:Strategy"
            ),
        ),
    )
    original_tape = payload["event_tape"]
    assert isinstance(original_tape, dict)
    source_tape_fingerprint = original_tape["source_tape_fingerprint"]
    adapter_version = original_tape["adapter_version"]
    event_records = original_tape["events"]
    assert isinstance(source_tape_fingerprint, str)
    assert isinstance(adapter_version, str)
    assert isinstance(event_records, list)
    native_event_stream = BytesIO()
    serialize_nautilus_native_event_stream(
        native_event_stream,
        event_records,
        source_tape_fingerprint=source_tape_fingerprint,
        adapter_version=adapter_version,
        expected_event_count=len(event_records),
    )
    payload["event_tape"] = {
        "source_tape_fingerprint": source_tape_fingerprint,
        "adapter_version": adapter_version,
        "event_count": len(event_records),
    }
    payload["strategy_source_digest"] = content_digest(source_alpha)
    payload["strategy_manifest_fingerprint"] = manifest_alpha.fingerprint
    payload["strategy_bindings"] = [
        {
            "component_id": component_id,
            "strategy_fingerprint": component_manifest_value.strategy.fingerprint,
            "strategy_source_digest": content_digest(source),
            "strategy_manifest_fingerprint": component_manifest_value.fingerprint,
            "entrypoint": "strategy.main:Strategy",
            "parameters_digest": content_digest({"window": 20}),
            "max_intents_per_event": 100,
        }
        for component_id, source, component_manifest_value in (
            ("alpha", source_alpha, manifest_alpha),
            ("beta", source_beta, manifest_beta),
        )
    ]
    instrument_definitions = payload["instruments"]
    assert isinstance(instrument_definitions, list)

    last_record = event_records[-1]
    assert isinstance(last_record, dict)
    live_event_time_ns = int(last_record["event_time_ns"]) + 1_000_000_000
    live_sequence = int(last_record["sequence"]) + 1
    live_event_id = "forward-live-event"
    live_record = {
        **last_record,
        "event_id": live_event_id,
        "event_time_ns": live_event_time_ns,
        "sequence": live_sequence,
    }
    live_event_time = datetime.fromtimestamp(live_event_time_ns / 1_000_000_000, UTC)
    live_market_event = MarketEvent(
        str(live_record["dependency_id"]),
        live_event_id,
        str(live_record["instrument_id"]),
        live_event_time,
        live_sequence,
        live_record["values"],
    )
    live_contexts = {
        "alpha": replace(
            contexts[0],
            event_time=live_event_time,
            event_sequence=live_sequence,
            market_events={live_market_event.dependency_id: (live_market_event,)},
        ),
        "beta": replace(
            contexts[0],
            event_time=live_event_time,
            event_sequence=live_sequence,
            market_events={live_market_event.dependency_id: (live_market_event,)},
        ),
    }
    bridge = build_native_strategy_bridge(
        payload,
        instrument_definitions,
        (),
        invocation_context_stream=BytesIO(context_stream.getvalue()),
        native_event_stream=BytesIO(native_event_stream.getvalue()),
        expected_context_count=sum(context_counts.values()),
        expected_component_context_counts=context_counts,
        allow_forward_event_staging=True,
        retain_invocation_results=retain_invocation_results,
    )
    bridge.strategy.on_start()
    prior_native_init_time_ns = -1
    for record in event_records:
        assert isinstance(record, dict)
        event_time_ns = int(record["event_time_ns"])
        prior_native_init_time_ns = max(event_time_ns + 1, prior_native_init_time_ns + 1)
        bridge.strategy.on_quote(
            SimpleNamespace(
                instrument_id=record["instrument_id"],
                ts_event=event_time_ns,
                ts_init=prior_native_init_time_ns,
                bid_price=Decimal(record["values"]["bid"]),
                ask_price=Decimal(record["values"]["ask"]),
            )
        )
    # The immutable bootstrap must be fully consumed before a live event is admitted.
    bridge.result_output()
    live_native_init_time_ns = max(live_event_time_ns + 1, prior_native_init_time_ns + 1)
    canonical_live_event = CanonicalForwardEvent(
        live_event_id,
        live_sequence,
        live_event_time,
        live_event_time,
        content_digest("verified-live-source"),
    )
    with pytest.raises(
        NautilusRuntimeDataError,
        match="differs from its canonical platform identity",
    ):
        bridge.stage_forward_event(
            {**live_record, "event_id": "altered-live-event"},
            live_contexts,
            instance_id="forward-bridge-test",
            canonical_event=canonical_live_event,
            native_init_time_ns=live_native_init_time_ns,
        )
    bridge.stage_forward_event(
        live_record,
        live_contexts,
        instance_id="forward-bridge-test",
        canonical_event=canonical_live_event,
        native_init_time_ns=live_native_init_time_ns,
    )
    bridge.strategy.on_quote(
        SimpleNamespace(
            instrument_id=live_record["instrument_id"],
            ts_event=live_event_time_ns,
            ts_init=live_native_init_time_ns,
            bid_price=Decimal(live_record["values"]["bid"]),
            ask_price=Decimal(live_record["values"]["ask"]),
        )
    )

    intent = OrderIntent(
        instrument_id="EURUSD.SIM",
        side=OrderSide.BUY,
        quantity=Decimal("1"),
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.DAY,
    )
    bridge.strategy._submit_order_resolution(
        SimpleNamespace(component_order_intents=(("alpha", (intent,)),))
    )
    native_order = bridge.strategy.submitted_orders[-1]
    bridge.strategy.portfolio.positions["EURUSD.SIM"] = Decimal("1")
    bridge.strategy.portfolio.cash = Decimal("9989.90")
    bridge.strategy.on_order_filled(
        SimpleNamespace(
            client_order_id=native_order.client_order_id,
            instrument_id="EURUSD.SIM",
            last_qty=Decimal("1"),
            last_px=Decimal("10"),
            commission=SimpleNamespace(
                currency=_FakeCurrency(), as_decimal=lambda: Decimal("0.10")
            ),
            trade_id="fake-trade-1",
            ts_event=live_event_time_ns,
        )
    )

    output = bridge.result_output()
    account_event = bridge.take_forward_account_event()
    assert account_event.instance_id == "forward-bridge-test"
    assert account_event.event_id == live_event_id
    assert account_event.cash_deltas == {"USD": Decimal("-10.10")}
    assert len(account_event.orders) == 1
    assert account_event.orders[0].event_id == live_event_id
    assert len(account_event.fills) == 1
    assert account_event.fills[0].order_id == account_event.orders[0].order_id
    assert account_event.fills[0].quantity == Decimal("1")
    assert account_event.fills[0].price == Decimal("10")
    assert account_event.fills[0].fee == Decimal("0.10")
    with pytest.raises(NautilusRuntimeDataError, match="no staged forward account event"):
        bridge.take_forward_account_event()
    if retain_invocation_results:
        results = deserialize_invocation_batch_result(output)
        assert [result.status.value for result in results] == [
            "failed",
            "succeeded",
            "failed",
            "succeeded",
        ]
    else:
        assert output is None


@pytest.mark.parametrize(
    (
        "trigger",
        "expected_status",
        "boundary_offset",
        "misfire_policy",
        "expected_execution_status",
    ),
    (
        (
            RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
            "apply_before_event",
            timedelta(0),
            RebalanceMisfirePolicy.FAIL_RUN,
            "applied_without_cached_targets",
        ),
        (
            RebalanceTrigger.SESSION_CLOSE_AFTER_EVENTS,
            "apply_after_event_group",
            timedelta(0),
            RebalanceMisfirePolicy.FAIL_RUN,
            "applied_without_cached_targets",
        ),
        (
            RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
            "fail_misfire",
            timedelta(days=1),
            RebalanceMisfirePolicy.FAIL_RUN,
            "failed_misfire",
        ),
    ),
)
def test_native_bridge_runs_rebalance_at_exact_open_or_after_same_time_group(
    monkeypatch,
    trigger: RebalanceTrigger,
    expected_status: str,
    boundary_offset: timedelta,
    misfire_policy: RebalanceMisfirePolicy,
    expected_execution_status: str,
) -> None:
    import sys
    from dataclasses import replace
    from io import BytesIO
    from types import ModuleType, SimpleNamespace
    from typing import Any

    from app.strategy_lab_v2.canonical import content_digest
    from app.strategy_lab_v2.nautilus_native_event_stream import (
        serialize_nautilus_native_event_stream,
    )
    from app.strategy_lab_v2.nautilus_portfolio_wire import (
        portfolio_composition_from_wire,
        portfolio_composition_to_wire,
    )
    from app.strategy_lab_v2.nautilus_rebalance_wire import (
        rebalance_execution_plan_to_wire,
    )
    from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
        _SOURCE,
        _invocation_batch,
        _payload,
    )
    from app.strategy_lab_v2.nautilus_strategy_bridge import build_native_strategy_bridge
    from app.strategy_lab_v2.rebalance import (
        CalendarDay,
        CalendarDayStatus,
        CalendarRebalancePolicy,
        RebalanceCadence,
        RebalanceExecutionPlan,
        ScheduledRebalance,
        SessionCalendarSnapshot,
        SessionSegment,
        TradingSession,
    )
    from strategy_runtime import deserialize_invocation_batch, serialize_invocation_context_stream

    class _FromString:
        def __new__(cls, value: str) -> Any:
            return value

        @classmethod
        def from_str(cls, value: str) -> str:
            return value

    class _FakePortfolio:
        def net_position(self, _instrument_id: str) -> None:
            return None

        def account(self, venue: str) -> Any:
            del venue
            return SimpleNamespace(
                base_currency=SimpleNamespace(code="USD"),
                balances_total=lambda: {"USD": Decimal("100000")},
            )

        def equity(self, venue: str) -> dict[str, Decimal]:
            del venue
            return {"USD": Decimal("100000")}

    class _FakeStrategyConfig:
        def __new__(cls, *_args: object) -> Any:
            return object.__new__(cls)

    class _FakeStrategy:
        def __init__(self, _config: object) -> None:
            self.portfolio = _FakePortfolio()

        def subscribe_quotes(self, _instrument_id: str) -> None:
            return None

        def subscribe_trades(self, _instrument_id: str) -> None:
            return None

        def subscribe_bars(self, _bar_type: str) -> None:
            return None

    class _FakeScalar:
        def __init__(self, *_args: object) -> None:
            return None

    model_module = ModuleType("nautilus_trader.model")
    for name in (
        "BarType",
        "Currency",
        "InstrumentId",
        "OrderSide",
        "StrategyId",
        "TimeInForce",
        "Venue",
    ):
        setattr(model_module, name, _FromString)
    for name in ("Price", "Quantity"):
        setattr(model_module, name, _FakeScalar)
    trading_module = ModuleType("nautilus_trader.trading")
    setattr(trading_module, "Strategy", _FakeStrategy)
    setattr(trading_module, "StrategyConfig", _FakeStrategyConfig)
    package_module = ModuleType("nautilus_trader")
    setattr(package_module, "model", model_module)
    setattr(package_module, "trading", trading_module)
    monkeypatch.setitem(sys.modules, "nautilus_trader", package_module)
    monkeypatch.setitem(sys.modules, "nautilus_trader.model", model_module)
    monkeypatch.setitem(sys.modules, "nautilus_trader.trading", trading_module)

    payload = _payload()
    original_portfolio = portfolio_composition_from_wire(payload["portfolio"])
    session_label = _EVENT_TIME.date()
    session_calendar = SessionCalendarSnapshot(
        calendar_id="XNYS",
        definition_version="bridge-session-test-v1",
        timezone_name="America/New_York",
        timezone_database_version="test-tzdb-v1",
        coverage_start=session_label,
        coverage_end=session_label,
        days=(
            CalendarDay(
                session_label,
                CalendarDayStatus.TRADING,
                TradingSession(
                    f"XNYS:{session_label.isoformat()}",
                    session_label,
                    (
                        SessionSegment(
                            _EVENT_TIME - timedelta(hours=4),
                            _EVENT_TIME,
                        ),
                    ),
                ),
            ),
        ),
        source_evidence_digest=content_digest("bridge-session-test-calendar"),
    )
    calendar_fingerprint = session_calendar.fingerprint
    policy = CalendarRebalancePolicy(
        calendar_id="XNYS",
        calendar_fingerprint=calendar_fingerprint,
        cadence=RebalanceCadence.EACH_SESSION,
        trigger=trigger,
        misfire_policy=misfire_policy,
    )
    boundary_time = _EVENT_TIME + boundary_offset
    occurrence_identity = {
        "policy_fingerprint": policy.fingerprint,
        "calendar_fingerprint": calendar_fingerprint,
        "session_id": f"XNYS:{boundary_time.date().isoformat()}",
        "session_label": boundary_time.date(),
        "event_time": boundary_time,
        "trigger": trigger,
        "cadence_period": f"session:{boundary_time.date().isoformat()}",
    }
    occurrence = ScheduledRebalance(
        occurrence_id=content_digest(occurrence_identity),
        policy_fingerprint=policy.fingerprint,
        calendar_fingerprint=calendar_fingerprint,
        session_id=f"XNYS:{boundary_time.date().isoformat()}",
        session_label=boundary_time.date(),
        event_time=boundary_time,
        trigger=trigger,
        cadence_period=f"session:{boundary_time.date().isoformat()}",
        misfire_policy=misfire_policy,
    )
    plan = RebalanceExecutionPlan(
        policy_fingerprint=policy.fingerprint,
        calendar_fingerprint=calendar_fingerprint,
        occurrences=(occurrence,),
    )
    portfolio = replace(original_portfolio, rebalance_policy=policy)
    payload["portfolio"] = portfolio_composition_to_wire(portfolio)
    payload["rebalance_plan"] = rebalance_execution_plan_to_wire(plan)
    payload["evaluation_window"] = {
        "fingerprint": content_digest("bridge-session-test-window"),
        "purpose": "out_of_sample",
        "warmup_start_ns": None,
        "start_ns": _EVENT_TIME_NS - 1_000,
        "end_ns": _EVENT_TIME_NS + 1_000,
    }

    _, manifest, contexts, _, _ = deserialize_invocation_batch(_invocation_batch())
    context_stream = BytesIO()
    context_count = serialize_invocation_context_stream(
        context_stream,
        source=_SOURCE,
        manifest=manifest,
        contexts=contexts,
        entrypoint="strategy.main:Strategy",
    )
    raw_tape = payload["event_tape"]
    assert isinstance(raw_tape, dict)
    event_records = raw_tape["events"]
    assert isinstance(event_records, list)
    native_event_stream = BytesIO()
    serialize_nautilus_native_event_stream(
        native_event_stream,
        event_records,
        source_tape_fingerprint=raw_tape["source_tape_fingerprint"],
        adapter_version=raw_tape["adapter_version"],
        expected_event_count=len(event_records),
    )
    payload["event_tape"] = {
        "source_tape_fingerprint": raw_tape["source_tape_fingerprint"],
        "adapter_version": raw_tape["adapter_version"],
        "event_count": len(event_records),
    }
    raw_instruments = payload["instruments"]
    assert isinstance(raw_instruments, list)
    instrument_definitions = [item for item in raw_instruments if isinstance(item, dict)]
    assert len(instrument_definitions) == len(raw_instruments)

    bridge = build_native_strategy_bridge(
        payload,
        instrument_definitions,
        (),
        invocation_context_stream=context_stream,
        native_event_stream=native_event_stream,
        expected_context_count=context_count,
        session_calendar=session_calendar,
    )
    bridge.strategy.on_start()
    prior_native_init_time_ns = -1
    for index, raw_record in enumerate(event_records):
        assert isinstance(raw_record, dict)
        event_time_ns = raw_record["event_time_ns"]
        values = raw_record["values"]
        assert isinstance(event_time_ns, int)
        assert isinstance(values, dict)
        prior_native_init_time_ns = max(event_time_ns + 1, prior_native_init_time_ns + 1)
        bridge.strategy.on_quote(
            SimpleNamespace(
                instrument_id=raw_record["instrument_id"],
                ts_event=event_time_ns,
                ts_init=prior_native_init_time_ns,
                bid_price=Decimal(values["bid"]),
                ask_price=Decimal(values["ask"]),
            )
        )
        if trigger is RebalanceTrigger.SESSION_CLOSE_AFTER_EVENTS and index == 0:
            assert bridge.rebalance_schedule_output() == []

    assert bridge.result_output()
    schedule_evidence = bridge.rebalance_schedule_output()
    session_close_observations = bridge.session_close_equity_output()
    assert len(session_close_observations) == 1
    assert session_close_observations[0].session_label == session_label
    assert session_close_observations[0].event_time_ns == _EVENT_TIME_NS
    assert session_close_observations[0].event_index == 1
    assert len(schedule_evidence) == 1
    transition = schedule_evidence[0]["transition"]
    assert isinstance(transition, dict)
    assert transition["action"] == expected_status
    assert schedule_evidence[0]["execution_status"] == expected_execution_status


def _component_fill_ledger() -> NautilusComponentFillLedger:
    strategy_fingerprint = _manifest().strategy.fingerprint
    return NautilusComponentFillLedger(
        PortfolioComposition(
            portfolio_id="portfolio-fill-ledger",
            version_id="v1",
            initial_capital=Decimal("100000"),
            base_currency="USD",
            components=(
                PortfolioComponent(
                    "core", strategy_fingerprint, ("US.AAPL",), Decimal("0.5"), priority=0
                ),
                PortfolioComponent(
                    "satellite",
                    strategy_fingerprint,
                    ("US.AAPL",),
                    Decimal("0.5"),
                    priority=1,
                ),
            ),
        )
    )


def test_component_fill_ledger_tracks_partial_fills_and_reconciles_net_positions() -> None:
    ledger = _component_fill_ledger()
    ledger.register_order(
        client_order_id="core-buy",
        component_id="core",
        instrument_id="US.AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
    )
    ledger.record_fill(
        client_order_id="core-buy",
        instrument_id="US.AAPL",
        quantity=Decimal("4"),
    )
    ledger.register_order(
        client_order_id="satellite-sell",
        component_id="satellite",
        instrument_id="US.AAPL",
        side=OrderSide.SELL,
        quantity=Decimal("4"),
    )
    ledger.record_fill(
        client_order_id="satellite-sell",
        instrument_id="US.AAPL",
        quantity=Decimal("4"),
    )

    assert ledger.quantities_by_component() == {
        "core": {"US.AAPL": Decimal("4")},
        "satellite": {"US.AAPL": Decimal("-4")},
    }
    ledger.reconcile({})
    ledger.record_fill(
        client_order_id="core-buy",
        instrument_id="US.AAPL",
        quantity=Decimal("6"),
    )
    ledger.reconcile({"US.AAPL": Decimal("6")})


@pytest.mark.parametrize(
    ("client_order_id", "instrument_id", "quantity", "message"),
    (
        ("unknown", "US.AAPL", Decimal("1"), "no component-attributed order"),
        ("core-buy", "US.MSFT", Decimal("1"), "instrument differs"),
        ("core-buy", "US.AAPL", Decimal("11"), "exceeds its attributed"),
    ),
)
def test_component_fill_ledger_rejects_unattributed_or_invalid_fills(
    client_order_id: str,
    instrument_id: str,
    quantity: Decimal,
    message: str,
) -> None:
    ledger = _component_fill_ledger()
    ledger.register_order(
        client_order_id="core-buy",
        component_id="core",
        instrument_id="US.AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
    )

    with pytest.raises(NautilusRuntimeDataError, match=message):
        ledger.record_fill(
            client_order_id=client_order_id,
            instrument_id=instrument_id,
            quantity=quantity,
        )


def test_component_fill_ledger_releases_unfilled_terminal_orders() -> None:
    ledger = _component_fill_ledger()
    ledger.register_order(
        client_order_id="core-buy",
        component_id="core",
        instrument_id="US.AAPL",
        side=OrderSide.BUY,
        quantity=Decimal("10"),
    )
    ledger.record_fill(
        client_order_id="core-buy",
        instrument_id="US.AAPL",
        quantity=Decimal("2"),
    )
    ledger.release_terminal_order("core-buy")

    assert ledger.quantities_by_component()["core"]["US.AAPL"] == Decimal("2")
    with pytest.raises(NautilusRuntimeDataError, match="no component attribution"):
        ledger.release_terminal_order("core-buy")


def test_replayed_stream_context_indexes_do_not_reopen_native_event_reader() -> None:
    first = _quote_event("quote-1", 1)
    second = _quote_event("quote-2", 2)
    third = _quote_event("quote-3", 3, first.event_time + timedelta(seconds=1))
    first_context = StrategyContext(
        event_time=first.event_time,
        event_sequence=2,
        random_seed=17,
        parameters={"window": 20},
        market_events={"prices": (first, second)},
    )
    second_context = StrategyContext(
        event_time=third.event_time,
        event_sequence=3,
        random_seed=17,
        parameters={"window": 20},
        market_events={"prices": (first, second, third)},
    )

    assert list(_iter_replayed_context_trigger_indexes((first_context, second_context))) == [
        (1, first_context),
        (2, second_context),
    ]


def test_replayed_stream_context_indexes_require_current_events() -> None:
    prior = _quote_event("quote-1", 1)
    context = StrategyContext(
        event_time=prior.event_time + timedelta(seconds=1),
        event_sequence=1,
        random_seed=17,
        parameters={"window": 20},
        market_events={"prices": (prior,)},
    )

    with pytest.raises(NautilusRuntimeDataError, match="current native event group"):
        list(_iter_replayed_context_trigger_indexes((context,)))


def test_stream_trigger_indexes_bind_per_event_contexts_to_native_order() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    first_context = _context(1, {"prices-a": (first,)})
    second_context = _context(2, {"prices-a": (first,), "prices-b": (second,)})

    assert list(
        _iter_context_trigger_indexes(
            (first_context, second_context), (_record(first), _record(second))
        )
    ) == [(0, first_context), (1, second_context)]


def test_stream_trigger_indexes_reject_incomplete_same_time_coverage() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    incomplete_context = _context(2, {"prices-a": (first,)})

    with pytest.raises(NautilusRuntimeDataError, match="every same-time native event"):
        list(
            _iter_context_trigger_indexes((incomplete_context,), (_record(first), _record(second)))
        )


def test_stream_trigger_indexes_reject_noncanonical_native_order() -> None:
    first = _event("event-1", "prices-a", "US.AAPL", 1)
    second = _event("event-2", "prices-b", "US.MSFT", 2)
    contexts = (
        _context(1, {"prices-a": (first,)}),
        _context(2, {"prices-a": (first,), "prices-b": (second,)}),
    )

    with pytest.raises(NautilusRuntimeDataError, match="canonical event order"):
        list(_iter_context_trigger_indexes(contexts, (_record(second), _record(first))))


def test_stream_trigger_indexes_consume_only_one_time_group_plus_lookahead() -> None:
    events = tuple(
        _event(
            f"event-{index}",
            f"prices-{index}",
            f"US.TEST{index}",
            index,
            EVENT_TIME + timedelta(seconds=index - 1),
        )
        for index in range(1, 4)
    )
    consumed: list[int] = []

    def contexts():
        for index, event in enumerate(events, start=1):
            consumed.append(index)
            yield _context(index, {event.dependency_id: (event,)}, event.event_time)

    triggers = _iter_context_trigger_indexes(contexts(), tuple(_record(event) for event in events))
    first_trigger_index, first_trigger_context = next(triggers)
    assert first_trigger_index == 0
    assert first_trigger_context.event_sequence == 1
    assert len(consumed) <= 2
    second_trigger_index, _second_trigger_context = next(triggers)
    assert second_trigger_index == 1
    assert len(consumed) <= 3


def _quote_event(event_id: str, sequence: int, event_time: datetime = _EVENT_TIME) -> MarketEvent:
    return MarketEvent(
        "prices",
        event_id,
        "EURUSD.SIM",
        event_time,
        sequence,
        {
            "bid": f"1.10{sequence:02d}",
            "ask": f"1.10{sequence + 2:02d}",
            "bid_size": "1000",
            "ask_size": "1000",
        },
    )


def _native_stream_record(event: MarketEvent, init_time_ns: int) -> dict[str, object]:
    return {
        "dependency_id": event.dependency_id,
        "event_id": event.event_id,
        "instrument_id": event.instrument_id,
        "event_type": "quote",
        "event_time_ns": (
            _EVENT_TIME_NS + int((event.event_time - _EVENT_TIME).total_seconds() * 1_000_000_000)
        ),
        "sequence": event.sequence,
        "values": dict(event.values),
        "native_init_time_ns": init_time_ns,
    }


def test_native_stream_context_triggers_validate_rolling_history_without_event_index() -> None:
    first = _quote_event("quote-1", 1)
    second = _quote_event("quote-2", 2)
    context = StrategyContext(
        event_time=_EVENT_TIME,
        event_sequence=2,
        random_seed=17,
        parameters={"window": 20},
        market_events={"prices": (first, second)},
    )

    triggers = list(
        _iter_stream_context_trigger_indexes(
            (context,),
            (
                _native_stream_record(first, _EVENT_TIME_NS),
                _native_stream_record(second, _EVENT_TIME_NS + 1),
            ),
            _manifest(),
        )
    )

    assert triggers == [(1, context)]


def test_native_stream_context_triggers_reject_history_drift() -> None:
    event = _quote_event("quote-1", 1)
    altered = MarketEvent(
        "prices",
        event.event_id,
        event.instrument_id,
        event.event_time,
        event.sequence,
        {**event.values, "bid": "9.99"},
    )
    context = StrategyContext(
        event_time=_EVENT_TIME,
        event_sequence=1,
        random_seed=17,
        parameters={"window": 20},
        market_events={"prices": (altered,)},
    )

    with pytest.raises(NautilusRuntimeDataError, match="differs from its authenticated"):
        list(
            _iter_stream_context_trigger_indexes(
                (context,),
                (_native_stream_record(event, _EVENT_TIME_NS),),
                _manifest(),
            )
        )
