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
    Currency,
    Money,
    OmsType,
    OrderSide,
    Price,
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

from app.strategy_lab_v2.nautilus_runtime_adapter_probe import (
    run_native_component_cycle_pnl_probe,
    run_native_signed_fee_reconciliation_probe,
    run_order_risk_probe,
    run_rebalance_schedule_probe,
    run_target_allocation_probe,
)


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
        "forward_event_tape_parity": "deferred_authoritative_fixture",
        "authoritative": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(run_fixture_suite(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover - image entrypoint
    raise SystemExit(main())


__all__ = ["main", "run_fixture_suite"]
