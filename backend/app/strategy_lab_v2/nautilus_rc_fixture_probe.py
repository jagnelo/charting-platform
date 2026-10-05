# mypy: disable-error-code="attr-defined,import-not-found"

"""Deterministic, image-local Nautilus v2 RC compatibility fixtures.

This entrypoint intentionally uses only synthetic in-memory ticks and the
Nautilus testkit's built-in instruments. It proves that the pinned image can
run real engine accounting/order paths without claiming stable authority or
forward-event parity.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusForwardDeliveryBinding,
    materialize_nautilus_forward_tape,
    verify_nautilus_forward_event_tape_parity,
)
from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
    run_native_component_cycle_pnl_probe,
    run_native_signed_fee_reconciliation_probe,
    run_order_risk_probe,
    run_rebalance_schedule_probe,
    run_target_allocation_probe,
)
from app.strategy_lab_v2.nautilus_runtime_data import materialize_native_event
from app.strategy_lab_v2.sdk import MarketEvent


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
        "authoritative": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run_fixture_suite(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover - image entrypoint
    raise SystemExit(main())


__all__ = ["main", "run_fixture_suite", "run_forward_streaming_fixture"]
