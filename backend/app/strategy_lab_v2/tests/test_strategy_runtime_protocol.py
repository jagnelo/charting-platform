from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    EventGranularity,
    ProductClass,
    StrategyDependency,
    StrategyVersion,
)
from app.strategy_lab_v2.sdk import (
    MarketEvent,
    OrderIntent,
    OrderSide,
    OrderType,
    PositionSnapshot,
    StrategyContext,
    StrategyDataDependency,
    StrategySdkManifest,
    TargetPositionIntent,
    TimeInForce,
)
from strategy_runtime import (
    BATCH_WIRE_PROTOCOL_VERSION,
    InvocationStatus,
    deserialize_invocation,
    deserialize_invocation_batch,
    deserialize_invocation_batch_result,
    deserialize_invocation_result,
    main,
    run_strategy_events,
    serialize_invocation,
    serialize_invocation_batch,
    serialize_invocation_batch_result,
    serialize_invocation_result,
)
from strategy_runtime.runner import run_strategy_event

NOW = datetime(2024, 1, 2, 15, 0, tzinfo=UTC)


def _manifest(source: str) -> StrategySdkManifest:
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=NOW - timedelta(days=10),
        end=NOW + timedelta(days=10),
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="XNYS.regular",
        feed="consolidated",
        execution_model="bar-close",
        account_model="cash",
        corporate_action_semantics="split-adjusted-v1",
    )
    return StrategySdkManifest(
        StrategyVersion(
            "strategy-1",
            "version-1",
            "2.0",
            content_digest(source),
            dependencies=(
                StrategyDependency("example-model", "1.2.3", content_digest("wheel")),
            ),
            parameter_schema={"threshold": {"type": "number"}},
            default_parameters={"threshold": Decimal("1.5000")},
        ),
        (StrategyDataDependency("daily-bars", requirement, ("close",), lookback_periods=3),),
    )


def _context() -> StrategyContext:
    return StrategyContext(
        event_time=NOW,
        event_sequence=1,
        random_seed=17,
        parameters={"threshold": Decimal("1.5"), "window": (1, 2)},
        market_events={
            "daily-bars": (
                MarketEvent(
                    "daily-bars",
                    "bar-1",
                    "US.AAPL",
                    NOW,
                    1,
                    {"close": Decimal("190"), "tags": frozenset({"regular", "close"})},
                ),
            )
        },
        positions={
            "US.AAPL": PositionSnapshot(
                "US.AAPL", Decimal("2"), Decimal("180"), Decimal("380")
            )
        },
    )


def test_invocation_wire_round_trip_is_canonical_and_typed() -> None:
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    manifest = _manifest(source)
    encoded = serialize_invocation(
        source=source,
        manifest=manifest,
        context=_context(),
        entrypoint="strategy.main:Strategy",
        max_intents_per_event=7,
    )
    decoded_source, decoded_manifest, decoded_context, entrypoint, limit = deserialize_invocation(encoded)
    assert deserialize_invocation(encoded)[0] == decoded_source
    assert decoded_source == source
    assert decoded_manifest == manifest
    assert decoded_context == _context()
    assert entrypoint == "strategy.main:Strategy"
    assert limit == 7
    assert encoded == serialize_invocation(
        source=decoded_source,
        manifest=decoded_manifest,
        context=decoded_context,
        entrypoint=entrypoint,
        max_intents_per_event=limit,
    )


def test_result_wire_round_trip_preserves_intents_and_fingerprint() -> None:
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    manifest = _manifest(source)
    result = run_strategy_event(
        source,
        manifest=manifest,
        context=_context(),
        entrypoint="strategy.main:Strategy",
    )
    assert result.status is InvocationStatus.SUCCEEDED
    with_order = result.__class__(
        source_digest=result.source_digest,
        context_fingerprint=result.context_fingerprint,
        entrypoint=result.entrypoint,
        status=InvocationStatus.SUCCEEDED,
        intents=(
            OrderIntent(
                "US.AAPL",
                OrderSide.BUY,
                Decimal("1.25"),
                OrderType.LIMIT,
                TimeInForce.GTC,
                limit_price=Decimal("189.50"),
                client_tag="wire-test",
            ),
            TargetPositionIntent("US.AAPL", Decimal("0.2")),
        ),
    )
    encoded = serialize_invocation_result(with_order)
    decoded = deserialize_invocation_result(encoded)
    assert decoded == with_order
    assert decoded.fingerprint == with_order.fingerprint

    tampered = encoded.replace(with_order.fingerprint, content_digest("tampered"))
    with pytest.raises(ValueError, match="fingerprint"):
        deserialize_invocation_result(tampered)


def test_batch_wire_round_trip_preserves_context_order_and_result_identity() -> None:
    source = """
class Strategy:
    def on_event(self, context):
        return [TargetPositionIntent('US.AAPL', Decimal(context.event_sequence) / Decimal(10))]
"""
    manifest = _manifest(source)
    first = _context()
    second_event = MarketEvent(
        "daily-bars",
        "bar-2",
        "US.AAPL",
        NOW + timedelta(days=1),
        2,
        {"close": Decimal("191")},
    )
    second = replace(
        first,
        event_time=NOW + timedelta(days=1),
        event_sequence=2,
        market_events={"daily-bars": (second_event,)},
    )
    contexts = (first, second)
    encoded = serialize_invocation_batch(
        source=source,
        manifest=manifest,
        contexts=contexts,
        entrypoint="strategy.main:Strategy",
        max_intents_per_event=7,
    )
    decoded_source, decoded_manifest, decoded_contexts, entrypoint, limit = deserialize_invocation_batch(
        encoded
    )
    assert decoded_source == source
    assert decoded_manifest == manifest
    assert decoded_contexts == contexts
    assert entrypoint == "strategy.main:Strategy"
    assert limit == 7
    assert encoded == serialize_invocation_batch(
        source=decoded_source,
        manifest=decoded_manifest,
        contexts=decoded_contexts,
        entrypoint=entrypoint,
        max_intents_per_event=limit,
    )

    results = run_strategy_events(
        source,
        manifest=manifest,
        contexts=contexts,
        entrypoint=entrypoint,
        max_intents_per_event=limit,
    )
    assert len(results) == 2
    assert all(item.status is InvocationStatus.SUCCEEDED for item in results)
    result_payload = serialize_invocation_batch_result(results)
    assert deserialize_invocation_batch_result(result_payload) == results
    tampered = result_payload.replace(
        '"fingerprint":"', '"fingerprint":"sha256:tampered', 1
    )
    with pytest.raises(ValueError, match="fingerprint"):
        deserialize_invocation_batch_result(tampered)


def test_batch_wire_rejects_empty_contexts_unknown_fields_and_versions() -> None:
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    manifest = _manifest(source)
    with pytest.raises(ValueError, match="must not be empty"):
        serialize_invocation_batch(
            source=source,
            manifest=manifest,
            contexts=(),
            entrypoint="strategy.main:Strategy",
        )
    encoded = serialize_invocation_batch(
        source=source,
        manifest=manifest,
        contexts=(_context(),),
        entrypoint="strategy.main:Strategy",
    )
    with pytest.raises(ValueError, match="unsupported"):
        deserialize_invocation_batch(encoded.replace(BATCH_WIRE_PROTOCOL_VERSION, "old"))
    with pytest.raises(ValueError, match="duplicate"):
        deserialize_invocation_batch(encoded.replace(
            '"source":', '"source":"duplicate", "source":', 1
        ))


def test_protocol_rejects_unknown_fields_and_versions() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        deserialize_invocation("not-json")
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    encoded = serialize_invocation(
        source=source,
        manifest=_manifest(source),
        context=_context(),
        entrypoint="strategy.main:Strategy",
    )
    with pytest.raises(ValueError, match="unsupported"):
        deserialize_invocation(encoded.replace("strategy-lab.strategy-runtime.v1", "old"))
    with pytest.raises(ValueError, match="duplicate"):
        deserialize_invocation(encoded.replace(
            '"source":', '"source":"duplicate", "source":', 1
        ))
    with pytest.raises(ValueError, match="non-finite"):
        deserialize_invocation(encoded.replace(
            '"max_intents_per_event":100', '"max_intents_per_event":NaN', 1
        ))


def test_cli_reads_request_and_atomically_publishes_result(tmp_path) -> None:
    source = """
class Strategy:
    def on_event(self, context):
        return [TargetPositionIntent('US.AAPL', Decimal('0.5'))]
"""
    manifest = _manifest(source)
    request = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request.write_text(
        serialize_invocation(
            source=source,
            manifest=manifest,
            context=_context(),
            entrypoint="strategy.main:Strategy",
        ),
        encoding="utf-8",
    )
    assert main(["--request", str(request), "--result", str(result_path)]) == 0
    decoded = deserialize_invocation_result(result_path.read_text(encoding="utf-8"))
    assert decoded.status is InvocationStatus.SUCCEEDED
    assert len(decoded.intents) == 1


def test_cli_runs_batch_request_in_one_stateful_process(tmp_path) -> None:
    source = """
class Strategy:
    def __init__(self):
        self.count = 0

    def on_event(self, context):
        self.count += 1
        return [TargetPositionIntent('US.AAPL', Decimal(self.count) / Decimal(10))]
"""
    manifest = _manifest(source)
    first = _context()
    second = replace(
        first,
        event_time=NOW + timedelta(days=1),
        event_sequence=2,
        market_events={
            "daily-bars": (
                MarketEvent(
                    "daily-bars",
                    "bar-2",
                    "US.AAPL",
                    NOW + timedelta(days=1),
                    2,
                    {"close": Decimal("191")},
                ),
            )
        },
    )
    request = tmp_path / "batch-request.json"
    result_path = tmp_path / "batch-result.json"
    request.write_text(
        serialize_invocation_batch(
            source=source,
            manifest=manifest,
            contexts=(first, second),
            entrypoint="strategy.main:Strategy",
        ),
        encoding="utf-8",
    )

    assert main(["--request", str(request), "--result", str(result_path)]) == 0
    decoded = deserialize_invocation_batch_result(result_path.read_text(encoding="utf-8"))
    assert len(decoded) == 2
    assert all(item.status is InvocationStatus.SUCCEEDED for item in decoded)
    assert isinstance(decoded[0].intents[0], TargetPositionIntent)
    assert isinstance(decoded[1].intents[0], TargetPositionIntent)
    assert decoded[0].intents[0].target_fraction == Decimal("0.1")
    assert decoded[1].intents[0].target_fraction == Decimal("0.2")


def test_cli_returns_nonzero_without_publishing_malformed_request(tmp_path) -> None:
    request = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request.write_text("{}", encoding="utf-8")
    assert main(["--request", str(request), "--result", str(result_path)]) == 1
    assert not result_path.exists()
