"""Execute the runtime adapter against one explicit two-tick FX payload."""

from __future__ import annotations

import json
from typing import Any

from nautilus_trader.model import (  # type: ignore[import-not-found,attr-defined]
    OrderSide,
    Quantity,
    StrategyId,
    TimeInForce,
)
from nautilus_trader.trading import (  # type: ignore[import-not-found,attr-defined]
    Strategy,
    StrategyConfig,
)

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.nautilus_runtime_adapter import run_native_backtest


class _ProbeStrategyConfig(StrategyConfig):
    def __new__(cls, instrument_ids):
        config = StrategyConfig.__new__(cls, StrategyId("ADAPTER-PROBE"))
        config.instrument_ids = tuple(instrument_ids)
        return config


class _ProbeBuyOnce(Strategy):
    def on_start(self) -> None:
        self._submitted: set[Any] = set()
        for instrument_id in self.config.instrument_ids:
            self.subscribe_quotes(instrument_id)

    def on_quote(self, quote) -> None:
        if quote.instrument_id in self._submitted:
            return
        self.submit_order(
            self.order_factory.market(
                instrument_id=quote.instrument_id,
                order_side=OrderSide.BUY,
                quantity=Quantity(1000, 0),
                time_in_force=TimeInForce.IOC,
            )
        )
        self._submitted.add(quote.instrument_id)


def _strategy_factory(instruments, _parameters):
    return _ProbeBuyOnce(_ProbeStrategyConfig(tuple(instrument.id for instrument in instruments)))


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
                    "event_time_ns": 1,
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
                    "event_time_ns": 2,
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
        "strategy_source_digest": content_digest("adapter-probe-source"),
        "strategy_manifest_fingerprint": content_digest("adapter-probe-manifest"),
        "entrypoint": "strategy.main:Strategy",
        "parameters": {"window": 20},
        "random_seed": 17,
        "input_version": "strategy-lab.nautilus-engine-input.v1",
    }


def main() -> int:
    result = run_native_backtest(_payload(), strategy_factory=_strategy_factory)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover - image entrypoint
    raise SystemExit(main())


__all__ = ["main"]
