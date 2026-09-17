from __future__ import annotations

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
    InvocationStatus,
    deserialize_invocation,
    deserialize_invocation_result,
    main,
    serialize_invocation,
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


def test_cli_returns_nonzero_without_publishing_malformed_request(tmp_path) -> None:
    request = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request.write_text("{}", encoding="utf-8")
    assert main(["--request", str(request), "--result", str(result_path)]) == 1
    assert not result_path.exists()
