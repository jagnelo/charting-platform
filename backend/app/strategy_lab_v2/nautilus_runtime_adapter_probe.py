"""Run the serialized strategy protocol through the isolated Nautilus engine."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    EventGranularity,
    ProductClass,
    StrategyVersion,
)
from app.strategy_lab_v2.nautilus_runtime_adapter import run_native_backtest
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    StrategyContext,
    StrategyDataDependency,
    StrategySdkManifest,
)
from strategy_runtime import serialize_invocation_batch

_EVENT_TIME = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
_EVENT_TIME_NS = 1_704_205_800_000_000_000
_SOURCE = """
class Strategy:
    def __init__(self):
        self.submitted = False

    def on_event(self, context):
        if self.submitted:
            return []
        self.submitted = True
        return [OrderIntent(
            instrument_id='EURUSD.SIM',
            side=OrderSide.BUY,
            quantity=Decimal('1000'),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.IOC,
        )]
"""


def _payload() -> dict[str, object]:
    return {
        "trial_id": "trial-adapter-probe",
        "attempt_id": "attempt-adapter-probe",
        "data_snapshot_fingerprint": content_digest("adapter-probe-snapshot"),
        "event_tape": {
            "source_tape_fingerprint": content_digest("adapter-probe-tape"),
            "adapter_version": "strategy-lab.nautilus-event-adapter.v1",
            "events": [
                {
                    "dependency_id": "prices",
                    "event_id": "adapter-event-1",
                    "instrument_id": "EURUSD.SIM",
                    "event_type": "quote",
                    "event_time_ns": _EVENT_TIME_NS,
                    "sequence": 1,
                    "values": {
                        "bid": "1.1000",
                        "ask": "1.1002",
                        "bid_size": "100000",
                        "ask_size": "100000",
                    },
                },
                {
                    "dependency_id": "prices",
                    "event_id": "adapter-event-2",
                    "instrument_id": "EURUSD.SIM",
                    "event_type": "quote",
                    "event_time_ns": _EVENT_TIME_NS,
                    "sequence": 2,
                    "values": {
                        "bid": "1.1001",
                        "ask": "1.1003",
                        "bid_size": "100000",
                        "ask_size": "100000",
                    },
                },
            ],
        },
        "instruments": [
            {
                "instrument_id": "EURUSD.SIM",
                "raw_symbol": "EURUSD",
                "venue_id": "SIM",
                "product_class": "fx",
                "base_currency": "EUR",
                "quote_currency": "USD",
                "price_precision": 5,
                "size_precision": 0,
                "price_increment": "0.00001",
                "size_increment": "1",
                "multiplier": "1",
                "min_quantity": None,
                "max_quantity": None,
                "activation_ns": None,
                "expiration_ns": None,
                "bar_type": "EURUSD.SIM-1-MINUTE-MID-INTERNAL",
            }
        ],
        "venue": {
            "venue_id": "SIM",
            "oms_type": "netting",
            "account_type": "cash",
            "base_currency": "USD",
            "cash": [{"currency": "USD", "amount": "100000"}],
        },
        "strategy_source_digest": content_digest(_SOURCE),
        "strategy_manifest_fingerprint": _manifest().fingerprint,
        "entrypoint": "strategy.main:Strategy",
        "parameters": {"window": 20},
        "random_seed": 17,
        "input_version": "strategy-lab.nautilus-engine-input.v1",
    }


def _manifest() -> StrategySdkManifest:
    requirement = CapabilityRequirement(
        instrument_id="EURUSD.SIM",
        product_class=ProductClass.FX,
        event_granularity=EventGranularity.QUOTE,
        event_type="quote",
        timeframe="tick",
        start=_EVENT_TIME - timedelta(days=1),
        end=_EVENT_TIME + timedelta(days=1),
        adjustment=AdjustmentMode.RAW,
        session="24x7",
        feed="consolidated",
        execution_model="market",
        account_model="cash",
        corporate_action_semantics="raw-unadjusted-v1",
    )
    return StrategySdkManifest(
        StrategyVersion("strategy-adapter-probe", "v1", "2.0", content_digest(_SOURCE)),
        (
            StrategyDataDependency(
                "prices",
                requirement,
                ("bid", "ask", "bid_size", "ask_size"),
                lookback_periods=2,
            ),
        ),
    )


def _invocation_batch() -> str:
    manifest = _manifest()
    first = MarketEvent(
        "prices",
        "adapter-event-1",
        "EURUSD.SIM",
        _EVENT_TIME,
        1,
        {
            "bid": "1.1000",
            "ask": "1.1002",
            "bid_size": "100000",
            "ask_size": "100000",
        },
    )
    second = MarketEvent(
        "prices",
        "adapter-event-2",
        "EURUSD.SIM",
        _EVENT_TIME,
        2,
        {
            "bid": "1.1001",
            "ask": "1.1003",
            "bid_size": "100000",
            "ask_size": "100000",
        },
    )
    contexts = (
        StrategyContext(
            _EVENT_TIME,
            2,
            17,
            {"window": 20},
            {"prices": (first, second)},
        ),
    )
    return serialize_invocation_batch(
        source=_SOURCE,
        manifest=manifest,
        contexts=contexts,
        entrypoint="strategy.main:Strategy",
    )


def main() -> int:
    result = run_native_backtest(
        _payload(),
        serialized_strategy_invocation_batch=_invocation_batch(),
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover - image entrypoint
    raise SystemExit(main())


__all__ = ["main"]
