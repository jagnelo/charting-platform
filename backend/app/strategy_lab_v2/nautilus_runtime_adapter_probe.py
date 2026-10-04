"""Run the serialized strategy protocol through the isolated Nautilus engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import deque
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any

from app.strategy_lab_v2 import nautilus_runtime_adapter
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    CASH_EQUITY_NOTIONAL_RISK_MODEL,
    FX_BASE_NOTIONAL_RISK_MODEL,
    AdjustmentMode,
    EventGranularity,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    SharedRiskPolicy,
    StrategyVersion,
)
from app.strategy_lab_v2.nautilus_native_event_stream import (
    serialize_nautilus_native_event_stream,
)
from app.strategy_lab_v2.nautilus_portfolio_wire import portfolio_composition_to_wire
from app.strategy_lab_v2.nautilus_runtime_adapter import (
    NAUTILUS_CATALOG_INPUT_CHUNK_SIZE,
    NAUTILUS_CATALOG_REPLAY_CHUNK_SIZE,
    run_native_backtest,
)
from app.strategy_lab_v2.nautilus_runtime_cli import main as runtime_cli_main
from app.strategy_lab_v2.nautilus_runtime_protocol import (
    NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE,
    NAUTILUS_CONTEXT_STREAM_SCHEMA,
    NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE,
    NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3,
)
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    StrategyContext,
    StrategyDataDependency,
    StrategySdkManifest,
)
from strategy_runtime import (
    MAX_INVOCATION_CONTEXT_STREAM_BYTES,
    MAX_INVOCATION_RESULT_STREAM_BYTES,
    deserialize_invocation_batch,
    deserialize_invocation_result_stream,
    serialize_invocation_batch,
    serialize_invocation_context_stream,
)

_EVENT_TIME = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
_EVENT_TIME_NS = 1_704_205_800_000_000_000
_SOURCE = """
class Strategy:
    def on_event(self, context):
        return []
"""

_TARGET_SOURCE = """
class Strategy:
    def __init__(self):
        self.submitted = False

    def on_event(self, context):
        if self.submitted:
            return []
        self.submitted = True
        return [TargetPositionIntent("AAPL.SIM", Decimal("0.5"))]
"""

_RAW_ORDER_SOURCE = """
class Strategy:
    def __init__(self):
        self.submitted = False

    def on_event(self, context):
        if self.submitted:
            return []
        self.submitted = True
        return [OrderIntent(
            instrument_id="AAPL.SIM",
            side=OrderSide.BUY,
            quantity=Decimal("100"),
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.DAY,
        )]
"""


def _payload() -> dict[str, object]:
    manifest = _manifest()
    portfolio = PortfolioComposition(
        portfolio_id="portfolio-adapter-probe",
        version_id="portfolio-v1",
        initial_capital=Decimal("100000"),
        base_currency="USD",
        components=(
            PortfolioComponent(
                component_id="component-1",
                strategy_fingerprint=manifest.strategy.fingerprint,
                instrument_ids=("EURUSD.SIM",),
                capital_weight=Decimal("1"),
            ),
        ),
        shared_risk_policy=SharedRiskPolicy(risk_models=(FX_BASE_NOTIONAL_RISK_MODEL,)),
    )
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
            "account_type": "margin",
            "base_currency": "USD",
            "cash": [{"currency": "USD", "amount": "100000"}],
        },
        "portfolio": portfolio_composition_to_wire(portfolio),
        "strategy_source_digest": content_digest(_SOURCE),
        "strategy_manifest_fingerprint": manifest.fingerprint,
        "entrypoint": "strategy.main:Strategy",
        "parameters": {"window": 20},
        "random_seed": 17,
        "strategy_bindings": [
            {
                "component_id": "component-1",
                "strategy_fingerprint": manifest.strategy.fingerprint,
                "strategy_source_digest": content_digest(_SOURCE),
                "strategy_manifest_fingerprint": manifest.fingerprint,
                "entrypoint": "strategy.main:Strategy",
                "parameters_digest": content_digest({"window": 20}),
                "max_intents_per_event": 100,
            }
        ],
        "input_version": "strategy-lab.nautilus-engine-input.v3",
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
        account_model="margin",
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


def run_target_allocation_probe() -> dict[str, Any]:
    """Exercise target allocation through the pinned native callback adapter."""

    return _run_native_execution_probe(target_position=True)


def run_order_risk_probe() -> dict[str, Any]:
    """Exercise raw SDK orders through platform risk before native submission."""

    return _run_native_execution_probe(target_position=False)


def _run_native_execution_probe(*, target_position: bool) -> dict[str, Any]:
    instrument_id = "AAPL.SIM"
    strategy_source = _TARGET_SOURCE if target_position else _RAW_ORDER_SOURCE
    later_time = _EVENT_TIME + timedelta(seconds=1)
    events = (
        MarketEvent(
            "prices",
            "target-event-1",
            instrument_id,
            _EVENT_TIME,
            1,
            {"bid": "99.99", "ask": "100.01", "bid_size": "1000", "ask_size": "1000"},
        ),
        MarketEvent(
            "prices",
            "target-event-2",
            instrument_id,
            _EVENT_TIME,
            2,
            {"bid": "100.00", "ask": "100.02", "bid_size": "1000", "ask_size": "1000"},
        ),
        MarketEvent(
            "prices",
            "target-event-3",
            instrument_id,
            later_time,
            3,
            {"bid": "100.01", "ask": "100.03", "bid_size": "1000", "ask_size": "1000"},
        ),
    )
    requirement = CapabilityRequirement(
        instrument_id=instrument_id,
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.QUOTE,
        event_type="quote",
        timeframe="tick",
        start=_EVENT_TIME - timedelta(days=1),
        end=later_time + timedelta(days=1),
        adjustment=AdjustmentMode.RAW,
        session="regular",
        feed="consolidated",
        execution_model="market",
        account_model="cash",
        corporate_action_semantics="raw-unadjusted-v1",
    )
    manifest = StrategySdkManifest(
        StrategyVersion(
            "strategy-target-probe" if target_position else "strategy-raw-order-probe",
            "v1",
            "2.0",
            content_digest(strategy_source),
        ),
        (StrategyDataDependency("prices", requirement, ("bid", "ask", "bid_size", "ask_size"), 1),),
    )
    portfolio = PortfolioComposition(
        portfolio_id="portfolio-target-probe",
        version_id="portfolio-v1",
        initial_capital=Decimal("100000"),
        base_currency="USD",
        components=(
            PortfolioComponent(
                "core",
                manifest.strategy.fingerprint,
                (instrument_id,),
                Decimal("1"),
            ),
        ),
        shared_risk_policy=SharedRiskPolicy(
            risk_models=(CASH_EQUITY_NOTIONAL_RISK_MODEL,),
        ),
    )
    event_records = [
        {
            "dependency_id": event.dependency_id,
            "event_id": event.event_id,
            "instrument_id": event.instrument_id,
            "event_type": "quote",
            "event_time_ns": int(event.event_time.timestamp()) * 1_000_000_000,
            "sequence": event.sequence,
            "values": dict(event.values),
        }
        for event in events
    ]
    payload: dict[str, object] = {
        "trial_id": "trial-target-probe",
        "attempt_id": "attempt-target-probe",
        "data_snapshot_fingerprint": content_digest("target-probe-snapshot"),
        "event_tape": {
            "source_tape_fingerprint": content_digest(event_records),
            "adapter_version": "strategy-lab.nautilus-event-adapter.v1",
            "events": event_records,
        },
        "instruments": [
            {
                "instrument_id": instrument_id,
                "raw_symbol": "AAPL",
                "venue_id": "SIM",
                "product_class": "equity",
                "base_currency": None,
                "quote_currency": "USD",
                "price_precision": 2,
                "size_precision": 0,
                "price_increment": "0.01",
                "size_increment": "1",
                "multiplier": "1",
                "min_quantity": "1",
                "max_quantity": None,
                "activation_ns": None,
                "expiration_ns": None,
                "bar_type": None,
            }
        ],
        "venue": {
            "venue_id": "SIM",
            "oms_type": "netting",
            "account_type": "cash",
            "base_currency": "USD",
            "cash": [{"currency": "USD", "amount": "100000"}],
        },
        "portfolio": portfolio_composition_to_wire(portfolio),
        "strategy_source_digest": manifest.strategy.source_digest,
        "strategy_manifest_fingerprint": manifest.fingerprint,
        "entrypoint": "strategy.main:Strategy",
        "parameters": {},
        "random_seed": 11,
        "strategy_bindings": [
            {
                "component_id": "core",
                "strategy_fingerprint": manifest.strategy.fingerprint,
                "strategy_source_digest": manifest.strategy.source_digest,
                "strategy_manifest_fingerprint": manifest.fingerprint,
                "entrypoint": "strategy.main:Strategy",
                "parameters_digest": content_digest({}),
                "max_intents_per_event": 100,
            }
        ],
        "input_version": "strategy-lab.nautilus-engine-input.v3",
    }
    batch = serialize_invocation_batch(
        source=strategy_source,
        manifest=manifest,
        contexts=(
            StrategyContext(
                _EVENT_TIME,
                2,
                11,
                {},
                {"prices": events[:2]},
            ),
            StrategyContext(
                later_time,
                3,
                11,
                {},
                {"prices": events},
            ),
        ),
        entrypoint="strategy.main:Strategy",
    )
    result = run_native_backtest(payload, serialized_strategy_invocation_batch=batch)
    summary = result.get("summary")
    if not isinstance(summary, dict):
        raise RuntimeError("target allocation probe has no native account summary")
    balance_text = summary.get("account.SIM.balance.USD.total")
    if not isinstance(balance_text, str):
        raise RuntimeError("native target allocation summary has no formatted USD balance")
    balance_parts = balance_text.split()
    if len(balance_parts) != 2 or balance_parts[1] != "USD":
        raise RuntimeError("native target allocation summary balance is not denominated in USD")
    remaining_cash = Decimal(balance_parts[0])
    if target_position:
        if (
            result.get("authoritative") is not False
            or result.get("total_orders") != 1
            or result.get("total_positions") != 1
            or not Decimal("45000") < remaining_cash < Decimal("55000")
        ):
            raise RuntimeError(
                "native target allocation did not reconcile order, position, and cash"
            )
        return {
            "instrument_id": instrument_id,
            "requested_target_fraction": "0.5",
            "total_orders": result["total_orders"],
            "total_positions": result["total_positions"],
            "initial_cash": "100000",
            "remaining_cash": str(remaining_cash),
            "observed_deployment": str(Decimal("100000") - remaining_cash),
            "account_base_currency": "USD",
            "authoritative": False,
        }
    if (
        result.get("authoritative") is not False
        or result.get("total_orders") != 1
        or result.get("total_positions") != 1
        or not Decimal("89000") < remaining_cash < Decimal("91000")
    ):
        raise RuntimeError("native raw-order risk probe did not reconcile order and account")
    return {
        "instrument_id": instrument_id,
        "requested_order_quantity": "100",
        "estimated_signed_base_notional": "10001",
        "total_orders": result["total_orders"],
        "total_positions": result["total_positions"],
        "initial_cash": "100000",
        "remaining_cash": str(remaining_cash),
        "observed_deployment": str(Decimal("100000") - remaining_cash),
        "account_base_currency": "USD",
        "authoritative": False,
    }


def run_context_stream_cli_probe(
    *,
    event_count: int = 2,
    replay_chunk_size: int | None = None,
) -> dict[str, Any]:
    """Exercise the strict stream/catalog CLI path against the native engine."""

    serialized_batch = _invocation_batch()
    source, manifest, _contexts, entrypoint, max_intents = deserialize_invocation_batch(
        serialized_batch
    )
    if not isinstance(event_count, int) or isinstance(event_count, bool) or event_count < 2:
        raise ValueError("event_count must be an integer of at least two")
    if replay_chunk_size is not None and (
        not isinstance(replay_chunk_size, int)
        or isinstance(replay_chunk_size, bool)
        or replay_chunk_size < 1
    ):
        raise ValueError("replay_chunk_size must be a positive integer")
    source_engine_input = _payload()
    source_event_tape = source_engine_input["event_tape"]
    if not isinstance(source_event_tape, dict):
        raise RuntimeError("adapter probe event tape is invalid")
    source_events: list[dict[str, Any]] = [
        {
            "dependency_id": "prices",
            "event_id": f"adapter-event-{index + 1}",
            "instrument_id": "EURUSD.SIM",
            "event_type": "quote",
            "event_time_ns": _EVENT_TIME_NS + max(0, index - 1) * 1_000_000_000,
            "sequence": index + 1,
            "values": {
                "bid": f"1.{1000 + index % 100:04d}",
                "ask": f"1.{1002 + index % 100:04d}",
                "bid_size": "100000",
                "ask_size": "100000",
            },
        }
        for index in range(event_count)
    ]
    source_event_tape["events"] = source_events
    source_event_tape["source_tape_fingerprint"] = content_digest(source_events)

    def contexts() -> Iterator[StrategyContext]:
        history: deque[MarketEvent] = deque(maxlen=3)
        position = 0
        while position < len(source_events):
            group_time_ns = source_events[position]["event_time_ns"]
            group_time = _EVENT_TIME + timedelta(
                seconds=(group_time_ns - _EVENT_TIME_NS) // 1_000_000_000
            )
            group: list[MarketEvent] = []
            while (
                position < len(source_events)
                and source_events[position]["event_time_ns"] == group_time_ns
            ):
                event = source_events[position]
                group.append(
                    MarketEvent(
                        event["dependency_id"],
                        event["event_id"],
                        event["instrument_id"],
                        group_time,
                        event["sequence"],
                        event["values"],
                    )
                )
                position += 1
            history.extend(group)
            yield StrategyContext(
                group_time,
                max(event.sequence for event in group),
                17,
                {"window": 20},
                {"prices": tuple(history)},
            )

    context_iter = contexts()
    context_wire = BytesIO()
    context_count = serialize_invocation_context_stream(
        context_wire,
        source=source,
        manifest=manifest,
        contexts=context_iter,
        entrypoint=entrypoint,
        max_intents_per_event=max_intents,
    )
    context_bytes = context_wire.getvalue()
    context_digest = f"sha256:{hashlib.sha256(context_bytes).hexdigest()}"
    native_event_wire = BytesIO()
    native_event_summary = serialize_nautilus_native_event_stream(
        native_event_wire,
        source_events,
        source_tape_fingerprint=source_event_tape["source_tape_fingerprint"],
        adapter_version=source_event_tape["adapter_version"],
        expected_event_count=len(source_events),
    )
    native_event_bytes = native_event_wire.getvalue()
    native_event_digest = native_event_summary.content_digest
    engine_input = dict(source_engine_input)
    event_tape = dict(source_event_tape)
    event_tape.pop("events")
    event_tape["event_count"] = native_event_summary.event_count
    engine_input["event_tape"] = event_tape
    bundle = {
        "schema": NAUTILUS_RUNTIME_BUNDLE_SCHEMA_V3,
        "engine_input": engine_input,
        "strategy_context_stream": {
            "artifact": {
                "content_digest": context_digest,
                "byte_length": len(context_bytes),
                "media_type": NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE,
                "schema_version": NAUTILUS_CONTEXT_STREAM_SCHEMA,
                "storage_key": context_digest,
                "retention_class": "pinned_input",
            },
            "context_count": context_count,
        },
        "native_event_stream": {
            "artifact": {
                "content_digest": native_event_digest,
                "byte_length": len(native_event_bytes),
                "media_type": NAUTILUS_NATIVE_EVENT_STREAM_MEDIA_TYPE,
                "schema_version": NAUTILUS_NATIVE_EVENT_STREAM_SCHEMA,
                "storage_key": native_event_digest,
                "retention_class": "pinned_input",
            },
            "source_tape_fingerprint": source_event_tape["source_tape_fingerprint"],
            "adapter_version": source_event_tape["adapter_version"],
            "event_count": native_event_summary.event_count,
        },
    }
    previous = {
        name: os.environ.get(name)
        for name in (
            "STRATEGY_INPUT_BUNDLE_DIGEST",
            "STRATEGY_ATTEMPT_ID",
            "STRATEGY_CONTEXT_STREAM_DIGEST",
            "STRATEGY_NATIVE_EVENT_STREAM_DIGEST",
        )
    }
    previous_replay_chunk_size = NAUTILUS_CATALOG_REPLAY_CHUNK_SIZE
    try:
        if replay_chunk_size is not None:
            nautilus_runtime_adapter.NAUTILUS_CATALOG_REPLAY_CHUNK_SIZE = replay_chunk_size
        with tempfile.TemporaryDirectory(prefix="strategy-lab-context-probe-") as directory:
            root = Path(directory)
            bundle_path = root / "bundle.json"
            context_path = root / "contexts.ndjson"
            native_event_path = root / "native-events.ndjson"
            result_stream_path = root / "invocations.ndjson"
            output_path = root / "result.json"
            bundle_path.write_text(
                json.dumps(bundle, allow_nan=False, separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
            context_path.write_bytes(context_bytes)
            native_event_path.write_bytes(native_event_bytes)
            result_stream_path.touch()
            output_path.touch()
            os.environ["STRATEGY_INPUT_BUNDLE_DIGEST"] = content_digest(bundle)
            os.environ["STRATEGY_ATTEMPT_ID"] = "attempt-adapter-probe"
            os.environ["STRATEGY_CONTEXT_STREAM_DIGEST"] = context_digest
            os.environ["STRATEGY_NATIVE_EVENT_STREAM_DIGEST"] = native_event_digest
            runtime_cli_main(
                [
                    "--input",
                    str(bundle_path),
                    "--output",
                    str(output_path),
                    "--expected-version",
                    "2.0.0rc5",
                    "--snapshot-fingerprint",
                    content_digest("adapter-probe-snapshot"),
                    "--max-input-bytes",
                    str(MAX_INVOCATION_CONTEXT_STREAM_BYTES),
                    "--context-stream",
                    str(context_path),
                    "--native-event-stream",
                    str(native_event_path),
                    "--invocation-results",
                    str(result_stream_path),
                    "--max-result-bytes",
                    str(MAX_INVOCATION_RESULT_STREAM_BYTES),
                ]
            )
            result = json.loads(output_path.read_text(encoding="utf-8"))
            result_stream_bytes = result_stream_path.read_bytes()
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        nautilus_runtime_adapter.NAUTILUS_CATALOG_REPLAY_CHUNK_SIZE = previous_replay_chunk_size
    if (
        result.get("strategy_invocation_input_protocol") != "context-stream"
        or result.get("authoritative") is not False
        or result.get("input_event_count") != event_count
        or result.get("total_orders") != 0
        or result.get("total_positions") != 0
        or result.get("native_data_source") != "parquet_catalog_chunks"
        or result.get("catalog_input_chunk_size") != NAUTILUS_CATALOG_INPUT_CHUNK_SIZE
        or result.get("catalog_replay_chunk_size")
        != (replay_chunk_size or previous_replay_chunk_size)
    ):
        raise RuntimeError("native catalog-stream CLI probe did not produce expected evidence")
    stream_receipt = result.get("strategy_invocation_result_stream")
    if not isinstance(stream_receipt, dict):
        raise RuntimeError("native context-stream CLI probe did not stream invocation results")
    if (
        stream_receipt.get("byte_length") != len(result_stream_bytes)
        or stream_receipt.get("content_digest")
        != f"sha256:{hashlib.sha256(result_stream_bytes).hexdigest()}"
    ):
        raise RuntimeError("native invocation result stream receipt differs from its bytes")
    decoded_results = tuple(
        deserialize_invocation_result_stream(
            BytesIO(result_stream_bytes),
            expected_result_count=stream_receipt.get("result_count"),
        )
    )
    if len(decoded_results) != context_count or not stream_receipt.get("all_succeeded"):
        raise RuntimeError("native invocation result stream is empty or contains failures")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--context-stream-cli",
        action="store_true",
        help="exercise the runtime bundle and verified context-sidecar CLI path",
    )
    parser.add_argument(
        "--catalog-chunk-cli",
        action="store_true",
        help="cross the native-input writer boundary and multiple BacktestNode replay chunks",
    )
    args = parser.parse_args(argv)
    if args.context_stream_cli:
        result = run_context_stream_cli_probe()
    elif args.catalog_chunk_cli:
        result = run_context_stream_cli_probe(
            event_count=NAUTILUS_CATALOG_INPUT_CHUNK_SIZE + 5,
            replay_chunk_size=1_000,
        )
    else:
        result = run_native_backtest(
            _payload(),
            serialized_strategy_invocation_batch=_invocation_batch(),
        )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":  # pragma: no cover - image entrypoint
    raise SystemExit(main())


__all__ = ["main", "run_context_stream_cli_probe"]
