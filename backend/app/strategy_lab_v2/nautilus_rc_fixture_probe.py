# mypy: disable-error-code="attr-defined,import-not-found"

"""Deterministic, image-local Nautilus v2 RC compatibility fixtures.

This entrypoint intentionally uses only synthetic in-memory ticks and the
Nautilus testkit's built-in instruments. It proves that the pinned image can
run real engine accounting/order paths without claiming stable authority or
forward-event parity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from contextlib import nullcontext
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import Any

from nautilus_trader.backtest import (  # type: ignore[attr-defined]
    BacktestEngine,
    BacktestEngineConfig,
)
from nautilus_trader.common import LoggerConfig  # type: ignore[attr-defined]
from nautilus_trader.execution import (  # type: ignore[attr-defined]
    FixedFeeModel,
    OneTickSlippageFillModel,
)
from nautilus_trader.model import (
    AccountType,
    BarAggregation,
    BarSpecification,
    BarType,
    Currency,
    Money,
    OmsType,
    OrderSide,
    Price,
    PriceType,
    Quantity,
    QuoteTick,
    StrategyId,
    TimeInForce,
    Venue,
)

# type: ignore[attr-defined]
from nautilus_trader.testkit.providers import (
    TestInstrumentProvider,  # type: ignore[import-not-found]
)
from nautilus_trader.trading import Strategy, StrategyConfig  # type: ignore[attr-defined]

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.forward_context import ForwardStrategyContextWindow
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusEventRecord,
    NautilusForwardDeliveryBinding,
    materialize_nautilus_forward_tape,
    verify_nautilus_forward_event_tape_parity,
)
from app.strategy_lab_v2.nautilus_forward_bootstrap import (
    NautilusForwardBootstrapComponent,
    NautilusForwardBootstrapEvent,
    NautilusForwardRuntimeBootstrap,
)
from app.strategy_lab_v2.nautilus_forward_input import NautilusForwardDeliveryInput
from app.strategy_lab_v2.nautilus_forward_native_runtime import (
    build_native_forward_session_factory,
)
from app.strategy_lab_v2.nautilus_native_event_stream import (
    serialize_nautilus_native_event_stream,
)
from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
    _invocation_batch as _forward_invocation_batch,
)
from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
    _payload as _forward_payload,
)
from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
    run_native_component_cycle_pnl_probe,
    run_native_signed_fee_reconciliation_probe,
    run_order_risk_probe,
    run_rebalance_schedule_probe,
    run_target_allocation_probe,
)
from app.strategy_lab_v2.nautilus_runtime_data import materialize_native_event
from app.strategy_lab_v2.nautilus_runtime_protocol import (
    NAUTILUS_COMPONENT_CONTEXT_STREAM_MEDIA_TYPE,
    NAUTILUS_COMPONENT_CONTEXT_STREAM_SCHEMA,
    NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE,
    NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA,
)
from app.strategy_lab_v2.sdk import MarketEvent
from strategy_runtime import (
    InvocationContextStreamSource,
    deserialize_invocation_batch,
    serialize_component_invocation_context_stream,
)

_FORWARD_EVENT_TIME = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)


class _FixtureConfig(StrategyConfig):
    def __new__(cls, instrument_ids):
        config = StrategyConfig.__new__(cls, StrategyId("S-001"))
        config.instrument_ids = tuple(instrument_ids)
        return config


class _BuyOnceStrategy(Strategy):
    def on_start(self) -> None:
        self._submitted: set[Any] = set()
        for instrument_id in self.config.instrument_ids:
            self.subscribe_quotes(instrument_id)

    def on_quote(self, quote) -> None:
        if quote.instrument_id in self._submitted:
            return
        order = self.order_factory.market(
            instrument_id=quote.instrument_id,
            order_side=OrderSide.BUY,
            quantity=Quantity(1000, 0),
            time_in_force=TimeInForce.IOC,
        )
        self.submit_order(order)
        self._submitted.add(quote.instrument_id)


def _quotes(instrument_id, *, offset: int = 0) -> list[QuoteTick]:
    return [
        QuoteTick(
            instrument_id,
            Price(1.1, 5),
            Price(1.1002, 5),
            Quantity(100000, 0),
            Quantity(100000, 0),
            offset + 1,
            offset + 1,
        ),
        QuoteTick(
            instrument_id,
            Price(1.1001, 5),
            Price(1.1003, 5),
            Quantity(100000, 0),
            Quantity(100000, 0),
            offset + 2,
            offset + 2,
        ),
    ]


def _run(instruments: tuple[Any, ...]) -> dict[str, Any]:
    engine = BacktestEngine(
        BacktestEngineConfig(logging=LoggerConfig(bypass_logging=True), bypass_logging=True)
    )
    usd = Currency.from_str("USD")
    try:
        engine.add_venue(
            Venue("SIM"),
            OmsType.NETTING,
            AccountType.CASH,
            [Money(100000, usd)],
            fill_model=OneTickSlippageFillModel(),
            fee_model=FixedFeeModel(Money(2, usd)),
        )
        for instrument in instruments:
            engine.add_instrument(instrument)
        engine.add_strategy(
            _BuyOnceStrategy(_FixtureConfig(tuple(instrument.id for instrument in instruments)))
        )
        data: list[QuoteTick] = []
        for index, instrument in enumerate(instruments):
            data.extend(_quotes(instrument.id, offset=index * 10))
        engine.add_data(data)
        engine.run()
        result = engine.get_result()
        summary = result.summary
        fill_rows = engine.generate_fills_report().to_dict(orient="records")
        order_rows = engine.generate_orders_report().to_dict(orient="records")
        first_quote = _quotes(instruments[0].id)[0]
        filled_quantity = sum((Decimal(str(row["last_qty"])) for row in fill_rows), Decimal(0))
        commission_total = sum(
            (Decimal(str(row["commission"]).split()[0]) for row in fill_rows), Decimal(0)
        )
        return {
            "iterations": result.iterations,
            "total_events": result.total_events,
            "total_orders": result.total_orders,
            "total_positions": result.total_positions,
            "account_total": str(summary["account.SIM.balance.USD.total"]),
            "orders_total": summary["orders.total"],
            "positions_total": summary["positions.total"],
            "instrument_count": len(instruments),
            "native_reports": {
                "orders_report_rows": len(order_rows),
                "total_fills": len(fill_rows),
                "fills_report_rows": len(fill_rows),
                "filled_quantity": str(filled_quantity),
                "fill_quantities": [str(row["last_qty"]) for row in fill_rows],
                "fill_instrument_ids": sorted(str(row["instrument_id"]) for row in fill_rows),
                "execution_prices": [str(row["last_px"]) for row in fill_rows],
                "commissions": [str(row["commission"]) for row in fill_rows],
                "commission_total": str(commission_total),
                "expected_commission_per_fill": "2.00",
                "fee_currency": "USD",
                "expected_quantity_per_instrument": "1000",
                "expected_quantity_total": str(1000 * len(instruments)),
                "initial_account_total": "100000.00",
                "best_ask": str(first_quote.ask_price),
                "price_increment": str(instruments[0].price_increment),
            },
        }
    finally:
        engine.dispose()


def _run_forward_streaming(instrument: Any) -> dict[str, Any]:
    """Exercise one persistent engine/strategy across newly supplied batches."""

    engine = BacktestEngine(
        BacktestEngineConfig(logging=LoggerConfig(bypass_logging=True), bypass_logging=True)
    )
    usd = Currency.from_str("USD")
    strategy = _BuyOnceStrategy(_FixtureConfig((instrument.id,)))
    try:
        engine.add_venue(
            Venue("SIM"),
            OmsType.NETTING,
            AccountType.CASH,
            [Money(100000, usd)],
            fill_model=OneTickSlippageFillModel(),
            fee_model=FixedFeeModel(Money(2, usd)),
        )
        engine.add_instrument(instrument)
        engine.add_strategy(strategy)
        quotes = _quotes(instrument.id)
        batch_event_counts: list[int] = []
        for quote in quotes:
            engine.add_data([quote], sort=True)
            engine.run(streaming=True)
            engine.clear_data()
            batch_event_counts.append(1)
        engine.end()

        result = engine.get_result()
        fills = engine.generate_fills_report().to_dict(orient="records")
        orders = engine.generate_orders_report().to_dict(orient="records")
        positions = engine.generate_positions_report().to_dict(orient="records")
        return {
            "batch_count": len(batch_event_counts),
            "batch_event_counts": batch_event_counts,
            "fill_count": len(fills),
            "order_count": len(orders),
            "position_count": len(positions),
            "strategy_submitted_instrument_count": len(strategy._submitted),
            "account_total": str(result.summary["account.SIM.balance.USD.total"]),
            "authoritative": False,
        }
    finally:
        engine.dispose()


def run_forward_streaming_fixture() -> dict[str, Any]:
    """Prove streamed batches retain native engine, account, and strategy state."""

    instrument = TestInstrumentProvider.audusd_sim()
    first = _run_forward_streaming(instrument)
    second = _run_forward_streaming(instrument)
    return {"first": first, "second": second, "equal": first == second}


def run_native_forward_session_fixture() -> dict[str, Any]:
    """Exercise the concrete session against RC5 with warm-up and live input."""

    instance_id = "forward-native-session-fixture"
    checkpoint = content_digest("forward-native-session-checkpoint")
    engine_input = _forward_payload()
    event_tape = engine_input["event_tape"]
    if not isinstance(event_tape, dict):
        raise RuntimeError("forward session fixture event tape is invalid")
    warmup_events = event_tape.get("events")
    if not isinstance(warmup_events, list) or len(warmup_events) != 2:
        raise RuntimeError("forward session fixture requires two warm-up events")
    tape_fingerprint = event_tape["source_tape_fingerprint"]
    adapter_version = event_tape["adapter_version"]
    event_records = tuple(
        NautilusEventRecord(
            dependency_id=event["dependency_id"],
            event_id=event["event_id"],
            instrument_id=event["instrument_id"],
            event_type=event["event_type"],
            event_time_ns=event["event_time_ns"],
            sequence=event["sequence"],
            values=event["values"],
        )
        for event in warmup_events
    )

    serialized_batch = _forward_invocation_batch()
    source, manifest, contexts, entrypoint, max_intents = deserialize_invocation_batch(
        serialized_batch
    )
    context_stream = BytesIO()
    component_counts = serialize_component_invocation_context_stream(
        context_stream,
        components=(
            InvocationContextStreamSource(
                "component-1",
                source,
                manifest,
                contexts,
                entrypoint,
                max_intents,
            ),
        ),
    )
    context_bytes = context_stream.getvalue()
    context_digest = f"sha256:{hashlib.sha256(context_bytes).hexdigest()}"
    context_reference = {
        "artifact": {
            "content_digest": context_digest,
            "byte_length": len(context_bytes),
            "media_type": NAUTILUS_COMPONENT_CONTEXT_STREAM_MEDIA_TYPE,
            "schema_version": NAUTILUS_COMPONENT_CONTEXT_STREAM_SCHEMA,
            "storage_key": context_digest,
            "retention_class": "pinned_input",
        },
        "context_count": sum(component_counts.values()),
        "component_counts": [
            {"component_id": component_id, "context_count": count}
            for component_id, count in sorted(component_counts.items())
        ],
    }
    native_stream = BytesIO()
    native_summary = serialize_nautilus_native_event_stream(
        native_stream,
        event_records,
        source_tape_fingerprint=tape_fingerprint,
        adapter_version=adapter_version,
        expected_event_count=len(event_records),
    )
    native_bytes = native_stream.getvalue()
    native_reference = {
        "artifact": {
            "content_digest": native_summary.content_digest,
            "byte_length": native_summary.byte_length,
            "media_type": NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE,
            "schema_version": NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA,
            "storage_key": native_summary.content_digest,
            "retention_class": "pinned_input",
        },
        "source_tape_fingerprint": tape_fingerprint,
        "adapter_version": adapter_version,
        "event_count": native_summary.event_count,
    }
    engine_input["event_tape"] = {
        "source_tape_fingerprint": tape_fingerprint,
        "adapter_version": adapter_version,
        "event_count": native_summary.event_count,
    }
    engine_fingerprint = content_digest(engine_input)
    bundle = {
        "engine_input": engine_input,
        "strategy_context_stream": context_reference,
        "native_event_stream": native_reference,
    }
    parameters = engine_input["parameters"]
    component = NautilusForwardBootstrapComponent(
        component_id="component-1",
        execution_binding_fingerprint=content_digest("execution-binding"),
        resolved_component_fingerprint=content_digest("resolved-component"),
        strategy_fingerprint=manifest.strategy.fingerprint,
        package_fingerprint=content_digest("package"),
        package_archive_digest=content_digest("package-archive"),
        dependency_lock_digest=content_digest("dependency-lock"),
        manifest_fingerprint=manifest.fingerprint,
        source_digest=content_digest(source),
        parameters_digest=content_digest(parameters),
        random_seed=engine_input["random_seed"],
    )
    bootstrap = NautilusForwardRuntimeBootstrap(
        instance_id=instance_id,
        execution_plan_fingerprint=content_digest("execution-plan"),
        portfolio_fingerprint=engine_input["portfolio"]["fingerprint"],
        snapshot_fingerprint=engine_input["data_snapshot_fingerprint"],
        warmup_receipt_fingerprint=content_digest("warmup-receipt"),
        warmup_result_fingerprint=content_digest("warmup-result"),
        warmup_tape_fingerprint=tape_fingerprint,
        warmup_event_count=native_summary.event_count,
        warmup_source_artifact_digests=(),
        warmup_cursor_event_id=event_records[-1].event_id,
        warmup_cursor_sequence=event_records[-1].sequence,
        warmup_cursor_event_fingerprint=content_digest("warmup-cursor-event"),
        processed_checkpoint_fingerprint=checkpoint,
        processed_prefix_fingerprint=content_digest("empty-processed-prefix"),
        before_event_fingerprint=content_digest("before-live-event"),
        engine_input_fingerprint=engine_fingerprint,
        runtime_input_bundle_digest=content_digest(
            {
                "engine": engine_fingerprint,
                "context": context_digest,
                "native": native_summary.content_digest,
            }
        ),
        native_event_stream_digest=native_summary.content_digest,
        native_event_stream_adapter_version=adapter_version,
        components=(component,),
        processed_events=(),
    )
    session_factory = build_native_forward_session_factory(
        bootstrap,
        bundle,
        open_context_stream=lambda: nullcontext(BytesIO(context_bytes)),
        open_native_event_stream=lambda: nullcontext(BytesIO(native_bytes)),
    )

    event_time = _FORWARD_EVENT_TIME + timedelta(seconds=1)
    source_digest = content_digest("live-source-event")
    canonical = CanonicalForwardEvent(
        "adapter-event-3",
        3,
        event_time,
        event_time + timedelta(seconds=1),
        source_digest,
    )
    market_event = MarketEvent(
        "prices",
        canonical.event_id,
        "EURUSD.SIM",
        canonical.event_time,
        canonical.sequence,
        {
            "bid": Decimal("1.1002"),
            "ask": Decimal("1.1004"),
            "bid_size": Decimal("100000"),
            "ask_size": Decimal("100000"),
        },
    )
    binding = NautilusForwardDeliveryBinding(
        instance_id=instance_id,
        event_fingerprint=content_digest(canonical),
        redis_stream_id="1704205801000-0",
        redis_entry_fingerprint=content_digest("live-redis-entry"),
        dispatch_record_fingerprint=content_digest("live-dispatch"),
        request_fingerprint=content_digest("live-request"),
        pre_event_checkpoint_fingerprint=checkpoint,
        warmup_receipt_fingerprint=bootstrap.warmup_receipt_fingerprint,
        admission_decision="enqueue",
    )
    delivery_tape = materialize_nautilus_forward_tape(
        instance_id,
        (canonical,),
        (market_event,),
        event_type_by_dependency={"prices": "quote"},
        delivery_bindings=(binding,),
    )
    delivery = NautilusForwardDeliveryInput(binding, delivery_tape, market_event, source_digest)
    host_window = ForwardStrategyContextWindow(
        instance_id,
        manifest,
        parameters=parameters,
        random_seed=component.random_seed,
    )
    _, _, host_contexts, _, _ = deserialize_invocation_batch(serialized_batch)
    host_window.seed_from_authenticated_contexts(
        host_contexts,
        context_stream_fingerprint=context_digest,
    )
    preparation = host_window.prepare_delivery(delivery)
    session = session_factory(instance_id)
    try:
        first = session.execute(delivery, preparation)
        duplicate = session.execute(delivery, preparation)
        if first != duplicate or first.account_event_binding.canonical_event != canonical:
            raise RuntimeError("forward session did not preserve native event idempotency")
        session.restore(checkpoint_fingerprint=checkpoint)
        replayed = session.execute(delivery, preparation)
        if replayed.fingerprint != first.fingerprint:
            raise RuntimeError("forward session restore changed native account effects")

        # Model the state supplied after restart without claiming an OS
        # process boundary: a new runtime receives an authenticated bootstrap
        # with the event in its processed prefix, not the old replay list.
        host_window.commit(preparation)
        next_checkpoint = content_digest("forward-native-session-checkpoint-after-event-3")
        processed_event = NautilusForwardBootstrapEvent(
            canonical,
            market_event,
            source_digest,
        )
        next_canonical = CanonicalForwardEvent(
            "adapter-event-4",
            4,
            event_time + timedelta(minutes=1),
            event_time + timedelta(minutes=1, seconds=1),
            content_digest("live-source-event-4"),
        )
        next_market_event = MarketEvent(
            "prices",
            next_canonical.event_id,
            "EURUSD.SIM",
            next_canonical.event_time,
            next_canonical.sequence,
            {
                "bid": Decimal("1.1003"),
                "ask": Decimal("1.1005"),
                "bid_size": Decimal("100000"),
                "ask_size": Decimal("100000"),
            },
        )
        next_bootstrap = replace(
            bootstrap,
            processed_checkpoint_fingerprint=next_checkpoint,
            processed_prefix_fingerprint=content_digest(
                {"prior_checkpoint": checkpoint, "events": [processed_event]}
            ),
            before_event_fingerprint=content_digest(next_canonical),
            processed_events=(processed_event,),
        )
        next_factory = build_native_forward_session_factory(
            next_bootstrap,
            bundle,
            open_context_stream=lambda: nullcontext(BytesIO(context_bytes)),
            open_native_event_stream=lambda: nullcontext(BytesIO(native_bytes)),
        )
        next_binding = NautilusForwardDeliveryBinding(
            instance_id=instance_id,
            event_fingerprint=content_digest(next_canonical),
            redis_stream_id="1704205802000-0",
            redis_entry_fingerprint=content_digest("live-redis-entry-4"),
            dispatch_record_fingerprint=content_digest("live-dispatch-4"),
            request_fingerprint=content_digest("live-request-4"),
            pre_event_checkpoint_fingerprint=next_checkpoint,
            warmup_receipt_fingerprint=bootstrap.warmup_receipt_fingerprint,
            admission_decision="enqueue",
        )
        next_tape = materialize_nautilus_forward_tape(
            instance_id,
            (next_canonical,),
            (next_market_event,),
            event_type_by_dependency={"prices": "quote"},
            delivery_bindings=(next_binding,),
        )
        next_delivery = NautilusForwardDeliveryInput(
            next_binding,
            next_tape,
            next_market_event,
            next_canonical.source_digest,
        )
        next_preparation = host_window.prepare_delivery(next_delivery)
        restored_session = next_factory(instance_id)
        try:
            after_process_loss = restored_session.execute(next_delivery, next_preparation)
            restored_session.restore(checkpoint_fingerprint=next_checkpoint)
            replayed_after_restart = restored_session.execute(next_delivery, next_preparation)
            if (
                replayed_after_restart.account_event_binding.fingerprint
                != after_process_loss.account_event_binding.fingerprint
            ):
                raise RuntimeError("non-empty-prefix restore changed native account effects")
        finally:
            restored_session.close()
        repeated_session = next_factory(instance_id)
        try:
            repeated_after_process_loss = repeated_session.execute(
                next_delivery,
                next_preparation,
            )
            if (
                repeated_after_process_loss.account_event_binding.fingerprint
                != after_process_loss.account_event_binding.fingerprint
            ):
                raise RuntimeError(
                    "fresh-process replay from a non-empty prefix is not deterministic"
                )
        finally:
            repeated_session.close()
        return {
            "passed": True,
            "authoritative": False,
            "non_empty_prefix_runtime_reconstruction": True,
            "account_event_fingerprint": first.account_event_binding.fingerprint,
            "reconstructed_account_event_fingerprint": (
                after_process_loss.account_event_binding.fingerprint
            ),
            "runtime_session_fingerprint": first.runtime_session_fingerprint,
            "result_fingerprint": first.fingerprint,
        }
    finally:
        session.close()


class _ForwardTapeParityConfig(StrategyConfig):
    def __new__(cls, instrument_id, bar_type, expected_by_key):
        config = StrategyConfig.__new__(cls, StrategyId("S-FORWARD-PARITY"))
        config.instrument_id = instrument_id
        config.bar_type = bar_type
        config.expected_by_key = expected_by_key
        return config


class _ForwardTapeParityStrategy(Strategy):
    def on_start(self) -> None:
        self._observed = []
        self._unexpected = 0
        instrument_id = self.config.instrument_id
        self.subscribe_quotes(instrument_id)
        self.subscribe_trades(instrument_id)
        self.subscribe_bars(self.config.bar_type)

    def on_quote(self, event) -> None:
        self._observe(
            "quote",
            event.instrument_id,
            event.ts_event,
            {
                "bid": str(event.bid_price),
                "ask": str(event.ask_price),
                "bid_size": str(event.bid_size),
                "ask_size": str(event.ask_size),
            },
        )

    def on_trade(self, event) -> None:
        aggressor = getattr(event.aggressor_side, "name", str(event.aggressor_side)).upper()
        self._observe(
            "trade",
            event.instrument_id,
            event.ts_event,
            {
                "price": str(event.price),
                "size": str(event.size),
                "aggressor_side": aggressor,
            },
        )

    def on_bar(self, event) -> None:
        self._observe(
            "ohlcv",
            event.bar_type.instrument_id,
            event.ts_event,
            {
                "open": str(event.open),
                "high": str(event.high),
                "low": str(event.low),
                "close": str(event.close),
                "volume": str(event.volume),
            },
        )

    def _observe(self, event_type, instrument_id, event_time_ns, values) -> None:
        instrument_text = str(instrument_id)
        event_key = (event_type, instrument_text, int(event_time_ns))
        expected = self.config.expected_by_key.get(event_key)
        if expected is None:
            self._unexpected += 1
            return
        self._observed.append(
            {
                "dependency_id": expected.dependency_id,
                "event_id": expected.event_id,
                "instrument_id": instrument_text,
                "event_type": event_type,
                "event_time_ns": int(event_time_ns),
                "sequence": expected.sequence,
                "values": values,
            }
        )


def _forward_tape_event_wire(record) -> dict[str, Any]:
    return {
        "dependency_id": record.dependency_id,
        "event_id": record.event_id,
        "instrument_id": record.instrument_id,
        "event_type": record.event_type,
        "event_time_ns": record.event_time_ns,
        "sequence": record.sequence,
        "values": dict(record.values),
    }


def _run_forward_event_tape_parity(instrument: Any) -> dict[str, Any]:
    """Send backend-materialized quote, trade, and bar events through Nautilus."""

    instance_id = "rc5-forward-parity-instance"
    instrument_id = str(instrument.id)
    bar_type = BarType(
        instrument.id,
        BarSpecification(1, BarAggregation.MINUTE, PriceType.LAST),
    )
    start = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    market_inputs = (
        (
            "quote-feed",
            "quote",
            {"bid": "1.10000", "ask": "1.10020", "bid_size": "100000", "ask_size": "100000"},
        ),
        ("trade-feed", "trade", {"price": "1.10010", "size": "1000", "aggressor_side": "BUY"}),
        (
            "minute-bars",
            "ohlcv",
            {
                "open": "1.10000",
                "high": "1.10100",
                "low": "1.09900",
                "close": "1.10050",
                "volume": "2500",
            },
        ),
    )
    canonical_events = []
    market_events = []
    bindings = []
    event_types: dict[str, str] = {}
    for sequence, (dependency_id, event_type, values) in enumerate(market_inputs):
        event_id = f"forward-event-{sequence}"
        event_time = start + timedelta(seconds=sequence + 1)
        canonical = CanonicalForwardEvent(
            event_id,
            sequence,
            event_time,
            event_time + timedelta(seconds=1),
            content_digest({"source": event_id}),
        )
        market = MarketEvent(
            dependency_id,
            event_id,
            instrument_id,
            event_time,
            sequence,
            values,
        )
        canonical_events.append(canonical)
        market_events.append(market)
        event_types[dependency_id] = event_type
        bindings.append(
            NautilusForwardDeliveryBinding(
                instance_id,
                content_digest(canonical),
                f"{1_704_221_400_000 + sequence}-0",
                content_digest({"redis-entry": sequence}),
                content_digest({"dispatch": sequence}),
                content_digest({"request": sequence}),
                content_digest({"checkpoint": sequence}),
                content_digest("forward-warmup-receipt"),
                "enqueue",
            )
        )
    tape = materialize_nautilus_forward_tape(
        instance_id,
        tuple(canonical_events),
        tuple(market_events),
        event_type_by_dependency=event_types,
        delivery_bindings=tuple(bindings),
    )
    expected_by_key = {
        (record.event_type, record.instrument_id, record.event_time_ns): record
        for record in (envelope.record for envelope in tape.envelopes)
    }
    instrument_definition = {
        "instrument_id": instrument_id,
        "price_precision": instrument.price_precision,
        "size_precision": instrument.size_precision,
        "bar_type": str(bar_type),
    }
    native_events = [
        materialize_native_event(
            _forward_tape_event_wire(envelope.record),
            instrument_definition,
        )
        for envelope in tape.envelopes
    ]
    engine = BacktestEngine(
        BacktestEngineConfig(logging=LoggerConfig(bypass_logging=True), bypass_logging=True)
    )
    try:
        usd = Currency.from_str("USD")
        engine.add_venue(
            Venue("SIM"),
            OmsType.NETTING,
            AccountType.CASH,
            [Money(100000, usd)],
            fill_model=OneTickSlippageFillModel(),
            fee_model=FixedFeeModel(Money(2, usd)),
        )
        engine.add_instrument(instrument)
        strategy = _ForwardTapeParityStrategy(
            _ForwardTapeParityConfig(instrument.id, bar_type, expected_by_key)
        )
        engine.add_strategy(strategy)
        engine.add_data(native_events, sort=True)
        engine.run()
        receipt = verify_nautilus_forward_event_tape_parity(tape, tuple(strategy._observed))
        return {
            "authoritative": False,
            "event_count": len(tape.envelopes),
            "event_types": sorted(event_types.values()),
            "expected_wire_digest": receipt.expected_wire_digest,
            "forward_tape_fingerprint": tape.fingerprint,
            "instance_id": instance_id,
            "mismatches": list(receipt.mismatches),
            "observed_event_count": receipt.observed_event_count,
            "observed_wire_digest": receipt.observed_wire_digest,
            "passed": receipt.passed and strategy._unexpected == 0,
            "receipt_fingerprint": receipt.fingerprint,
            "unexpected_callback_count": strategy._unexpected,
        }
    finally:
        engine.dispose()


def run_fixture_suite() -> dict[str, Any]:
    """Run real deterministic engine paths and return JSON-safe evidence."""

    single = (TestInstrumentProvider.audusd_sim(),)
    multi = (TestInstrumentProvider.audusd_sim(), TestInstrumentProvider.gbpusd_sim())
    first = _run(single)
    second = _run(single)
    multi_result = _run(multi)
    target_result = run_target_allocation_probe()
    raw_order_result = run_order_risk_probe()
    component_pnl_result = run_native_component_cycle_pnl_probe()
    signed_fee_result = run_native_signed_fee_reconciliation_probe()
    rebalance_schedule_result = run_rebalance_schedule_probe()
    forward_streaming_result = run_forward_streaming_fixture()
    forward_native_session_result = run_native_forward_session_fixture()
    forward_event_tape_parity = _run_forward_event_tape_parity(single[0])
    native_order_fill_cost = {
        **first,
        "raw_order_risk_probe": raw_order_result,
        "target_allocation_probe": target_result,
    }
    return {
        "engine_lifecycle": "passed",
        "native_component_pnl_attribution": component_pnl_result,
        "native_signed_fee_reconciliation": signed_fee_result,
        "native_order_fill_cost": native_order_fill_cost,
        "portfolio_rebalance_schedule": rebalance_schedule_result,
        "multi_instrument_accounting": multi_result,
        "deterministic_replay": {
            "first": first,
            "second": second,
            "equal": first == second,
        },
        "forward_event_tape_parity": forward_event_tape_parity,
        "forward_streaming_session": forward_streaming_result,
        "forward_native_session": forward_native_session_result,
        "authoritative": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run_fixture_suite(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover - image entrypoint
    raise SystemExit(main())


__all__ = [
    "main",
    "run_fixture_suite",
    "run_forward_streaming_fixture",
    "run_native_forward_session_fixture",
]
