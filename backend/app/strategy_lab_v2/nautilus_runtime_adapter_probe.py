"""Run the serialized strategy protocol through the isolated Nautilus engine."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    EventGranularity,
    ProductClass,
    StrategyVersion,
)
from app.strategy_lab_v2.nautilus_runtime_adapter import run_native_backtest
from app.strategy_lab_v2.nautilus_runtime_cli import main as runtime_cli_main
from app.strategy_lab_v2.nautilus_runtime_protocol import (
    NAUTILUS_CONTEXT_STREAM_MEDIA_TYPE,
    NAUTILUS_CONTEXT_STREAM_SCHEMA,
    NAUTILUS_RUNTIME_BUNDLE_SCHEMA,
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


def run_context_stream_cli_probe() -> dict[str, Any]:
    """Exercise the strict bundle/sidecar CLI path against the native engine."""

    serialized_batch = _invocation_batch()
    source, manifest, contexts, entrypoint, max_intents = deserialize_invocation_batch(
        serialized_batch
    )
    context_wire = BytesIO()
    context_count = serialize_invocation_context_stream(
        context_wire,
        source=source,
        manifest=manifest,
        contexts=contexts,
        entrypoint=entrypoint,
        max_intents_per_event=max_intents,
    )
    context_bytes = context_wire.getvalue()
    context_digest = f"sha256:{hashlib.sha256(context_bytes).hexdigest()}"
    bundle = {
        "schema": NAUTILUS_RUNTIME_BUNDLE_SCHEMA,
        "engine_input": _payload(),
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
    }
    previous = {
        name: os.environ.get(name)
        for name in (
            "STRATEGY_INPUT_BUNDLE_DIGEST",
            "STRATEGY_ATTEMPT_ID",
            "STRATEGY_CONTEXT_STREAM_DIGEST",
        )
    }
    try:
        with tempfile.TemporaryDirectory(prefix="strategy-lab-context-probe-") as directory:
            root = Path(directory)
            bundle_path = root / "bundle.json"
            context_path = root / "contexts.ndjson"
            result_stream_path = root / "invocations.ndjson"
            output_path = root / "result.json"
            bundle_path.write_text(
                json.dumps(bundle, allow_nan=False, separators=(",", ":"), sort_keys=True),
                encoding="utf-8",
            )
            context_path.write_bytes(context_bytes)
            result_stream_path.touch()
            output_path.touch()
            os.environ["STRATEGY_INPUT_BUNDLE_DIGEST"] = content_digest(bundle)
            os.environ["STRATEGY_ATTEMPT_ID"] = "attempt-adapter-probe"
            os.environ["STRATEGY_CONTEXT_STREAM_DIGEST"] = context_digest
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
    if (
        result.get("strategy_invocation_input_protocol") != "context-stream"
        or result.get("authoritative") is not False
    ):
        raise RuntimeError("native context-stream CLI probe did not produce expected evidence")
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
    if not decoded_results or not stream_receipt.get("all_succeeded"):
        raise RuntimeError("native invocation result stream is empty or contains failures")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--context-stream-cli",
        action="store_true",
        help="exercise the runtime bundle and verified context-sidecar CLI path",
    )
    args = parser.parse_args(argv)
    if args.context_stream_cli:
        result = run_context_stream_cli_probe()
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
