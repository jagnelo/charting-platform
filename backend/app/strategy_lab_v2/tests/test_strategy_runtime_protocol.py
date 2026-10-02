from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO

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
    INVOCATION_CONTEXT_STREAM_PROTOCOL_VERSION,
    INVOCATION_RESULT_STREAM_PROTOCOL_VERSION,
    MAX_INVOCATION_CONTEXT_STREAM_BYTES,
    MAX_INVOCATION_RESULT_STREAM_BYTES,
    MAX_WIRE_PAYLOAD_BYTES,
    InvocationResultStreamWriter,
    InvocationStatus,
    deserialize_invocation,
    deserialize_invocation_batch,
    deserialize_invocation_batch_result,
    deserialize_invocation_context_stream,
    deserialize_invocation_result,
    deserialize_invocation_result_stream,
    main,
    run_strategy_event_stream,
    run_strategy_events,
    serialize_invocation,
    serialize_invocation_batch,
    serialize_invocation_batch_result,
    serialize_invocation_context_stream,
    serialize_invocation_result,
    serialize_invocation_result_stream,
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
            dependencies=(StrategyDependency("example-model", "1.2.3", content_digest("wheel")),),
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
            "US.AAPL": PositionSnapshot("US.AAPL", Decimal("2"), Decimal("180"), Decimal("380"))
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
    decoded_source, decoded_manifest, decoded_context, entrypoint, limit = deserialize_invocation(
        encoded
    )
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
        manifest_fingerprint=result.manifest_fingerprint,
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
    decoded_source, decoded_manifest, decoded_contexts, entrypoint, limit = (
        deserialize_invocation_batch(encoded)
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
    tampered = result_payload.replace('"fingerprint":"', '"fingerprint":"sha256:tampered', 1)
    with pytest.raises(ValueError, match="fingerprint"):
        deserialize_invocation_batch_result(tampered)


def test_context_stream_wire_round_trip_consumes_contexts_incrementally() -> None:
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
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
    yielded: list[StrategyContext] = []

    def contexts():
        for context in (first, second):
            yielded.append(context)
            yield context

    payload = BytesIO()
    assert (
        serialize_invocation_context_stream(
            payload,
            source=source,
            manifest=manifest,
            contexts=contexts(),
            entrypoint="strategy.main:Strategy",
            max_intents_per_event=7,
        )
        == 2
    )
    assert yielded == [first, second]
    assert (
        f'"protocol_version":"{INVOCATION_CONTEXT_STREAM_PROTOCOL_VERSION}"'.encode()
        in payload.getvalue()
    )

    payload.seek(0)
    decoded_source, decoded_manifest, decoded_contexts, entrypoint, limit = (
        deserialize_invocation_context_stream(payload, expected_context_count=2)
    )
    assert decoded_source == source
    assert decoded_manifest == manifest
    assert entrypoint == "strategy.main:Strategy"
    assert limit == 7
    header_offset = payload.tell()
    assert next(decoded_contexts) == first
    assert payload.tell() > header_offset
    assert next(decoded_contexts) == second
    with pytest.raises(StopIteration):
        next(decoded_contexts)


def test_context_stream_wire_rejects_count_order_and_index_drift() -> None:
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    manifest = _manifest(source)
    first = _context()
    second = replace(first, event_time=NOW + timedelta(minutes=1), event_sequence=2)
    encoded = BytesIO()
    serialize_invocation_context_stream(
        encoded,
        source=source,
        manifest=manifest,
        contexts=(first, second),
        entrypoint="strategy.main:Strategy",
    )
    wire = encoded.getvalue()

    with pytest.raises(ValueError, match="strictly chronological"):
        serialize_invocation_context_stream(
            BytesIO(),
            source=source,
            manifest=manifest,
            contexts=(second, first),
            entrypoint="strategy.main:Strategy",
        )

    _, _, incomplete, _, _ = deserialize_invocation_context_stream(
        BytesIO(wire), expected_context_count=3
    )
    assert next(incomplete) == first
    assert next(incomplete) == second
    with pytest.raises(ValueError, match="count differs"):
        next(incomplete)

    tampered = wire.replace(b'"index":1', b'"index":2', 1)
    _, _, invalid_indexes, _, _ = deserialize_invocation_context_stream(BytesIO(tampered))
    assert next(invalid_indexes) == first
    with pytest.raises(ValueError, match="index is not contiguous"):
        next(invalid_indexes)

    missing_trailer = BytesIO(b"\n".join(wire.splitlines()[:-1]) + b"\n")
    _, _, truncated_contexts, _, _ = deserialize_invocation_context_stream(missing_trailer)
    assert next(truncated_contexts) == first
    assert next(truncated_contexts) == second
    with pytest.raises(ValueError, match="trailer is missing"):
        next(truncated_contexts)

    tampered_digest = wire.replace(b'"records_sha256":"sha256:', b'"records_sha256":"sha256:0', 1)
    _, _, invalid_digest, _, _ = deserialize_invocation_context_stream(BytesIO(tampered_digest))
    assert next(invalid_digest) == first
    assert next(invalid_digest) == second
    with pytest.raises(ValueError, match="digest differs"):
        next(invalid_digest)

    stream_limit = len(wire.split(b"\n", 1)[0]) + 1
    with pytest.raises(ValueError, match="configured byte bound"):
        serialize_invocation_context_stream(
            BytesIO(),
            source=source,
            manifest=manifest,
            contexts=(first,),
            entrypoint="strategy.main:Strategy",
            max_stream_bytes=stream_limit,
        )
    with pytest.raises(ValueError, match="configured byte bound"):
        _, _, bounded_contexts, _, _ = deserialize_invocation_context_stream(
            BytesIO(wire), max_stream_bytes=stream_limit
        )
        next(bounded_contexts)
    assert MAX_INVOCATION_CONTEXT_STREAM_BYTES > MAX_WIRE_PAYLOAD_BYTES


def test_result_stream_round_trip_is_incremental_and_integrity_checked() -> None:
    source = """
class Strategy:
    def on_event(self, context):
        return [TargetPositionIntent('US.AAPL', Decimal(context.event_sequence) / Decimal(10))]
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
    results = run_strategy_event_stream(
        source,
        manifest=manifest,
        contexts=(first, second),
        entrypoint="strategy.main:Strategy",
    )
    payload = BytesIO()
    assert serialize_invocation_result_stream(payload, results) == (2, True)
    assert (
        f'"protocol_version":"{INVOCATION_RESULT_STREAM_PROTOCOL_VERSION}"'.encode()
        in payload.getvalue()
    )

    payload.seek(0)
    decoded = tuple(deserialize_invocation_result_stream(payload, expected_result_count=2))
    assert len(decoded) == 2
    assert all(item.status is InvocationStatus.SUCCEEDED for item in decoded)
    assert decoded[0].intents[0].target_fraction == Decimal("0.1")
    assert decoded[1].intents[0].target_fraction == Decimal("0.2")

    tampered = payload.getvalue().replace(b'"result_count":2', b'"result_count":3')
    invalid = deserialize_invocation_result_stream(BytesIO(tampered))
    assert next(invalid) == decoded[0]
    assert next(invalid) == decoded[1]
    with pytest.raises(ValueError, match="count differs"):
        next(invalid)
    assert MAX_INVOCATION_RESULT_STREAM_BYTES > MAX_WIRE_PAYLOAD_BYTES


def test_result_stream_writer_returns_bounded_content_receipt() -> None:
    source = """
class Strategy:
    def on_event(self, context):
        return []
"""
    manifest = _manifest(source)
    result = run_strategy_event(
        source,
        manifest=manifest,
        context=_context(),
        entrypoint="strategy.main:Strategy",
    )
    payload = BytesIO()
    writer = InvocationResultStreamWriter(payload)
    writer.write(result)
    summary = writer.finish()

    assert summary.result_count == 1
    assert summary.all_succeeded is True
    assert summary.byte_length == len(payload.getvalue())
    assert summary.content_digest == f"sha256:{hashlib.sha256(payload.getvalue()).hexdigest()}"
    with pytest.raises(ValueError, match="already finalized"):
        writer.write(result)
    with pytest.raises(ValueError, match="already finalized"):
        writer.finish()

    payload.seek(0)
    decoded = tuple(deserialize_invocation_result_stream(payload))
    assert decoded == (result,)

    oversized = InvocationResultStreamWriter(BytesIO(), max_stream_bytes=128)
    with pytest.raises(ValueError, match="configured byte bound"):
        oversized.write(result)
    with pytest.raises(ValueError, match="must not be empty"):
        InvocationResultStreamWriter(BytesIO()).finish()


def test_strategy_context_stream_runner_pulls_one_context_per_result() -> None:
    source = """
class Strategy:
    def on_event(self, context):
        return []
"""
    first = _context()
    second = replace(first, event_time=NOW + timedelta(days=1), event_sequence=2)
    observed: list[StrategyContext] = []

    def contexts():
        for context in (first, second):
            observed.append(context)
            yield context

    results = run_strategy_event_stream(
        source,
        manifest=_manifest(source),
        contexts=contexts(),
        entrypoint="strategy.main:Strategy",
    )
    assert observed == []
    assert next(results).status is InvocationStatus.SUCCEEDED
    assert observed == [first]
    assert next(results).status is InvocationStatus.SUCCEEDED
    assert observed == [first, second]
    with pytest.raises(StopIteration):
        next(results)


def test_wire_datetimes_normalize_equivalent_offsets_to_utc() -> None:
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    manifest = _manifest(source)
    offset = timezone(timedelta(hours=2))
    offset_event = MarketEvent(
        "daily-bars",
        "bar-1",
        "US.AAPL",
        NOW.astimezone(offset),
        1,
        {"close": Decimal("190"), "tags": frozenset({"regular", "close"})},
    )
    offset_context = replace(
        _context(),
        event_time=NOW.astimezone(offset),
        market_events={"daily-bars": (offset_event,)},
    )

    encoded_utc = serialize_invocation(
        source=source,
        manifest=manifest,
        context=_context(),
        entrypoint="strategy.main:Strategy",
    )
    encoded_offset = serialize_invocation(
        source=source,
        manifest=manifest,
        context=offset_context,
        entrypoint="strategy.main:Strategy",
    )

    assert encoded_offset == encoded_utc
    decoded = deserialize_invocation(encoded_offset)[2]
    assert decoded.event_time.tzinfo is UTC
    assert decoded.market_events["daily-bars"][0].event_time.tzinfo is UTC


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
        deserialize_invocation_batch(
            encoded.replace('"source":', '"source":"duplicate", "source":', 1)
        )


def test_batch_wire_rejects_non_chronological_contexts_before_execution() -> None:
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    manifest = _manifest(source)
    first = _context()
    duplicate = replace(first, event_sequence=first.event_sequence)

    with pytest.raises(ValueError, match="strictly chronological"):
        serialize_invocation_batch(
            source=source,
            manifest=manifest,
            contexts=(first, duplicate),
            entrypoint="strategy.main:Strategy",
        )

    valid_payload = serialize_invocation_batch(
        source=source,
        manifest=manifest,
        contexts=(
            first,
            replace(first, event_sequence=2, market_events={"daily-bars": ()}),
        ),
        entrypoint="strategy.main:Strategy",
    )
    tampered = valid_payload.replace('"event_sequence":2', '"event_sequence":0', 1)
    with pytest.raises(ValueError, match="strictly chronological"):
        deserialize_invocation_batch(tampered)

    with pytest.raises(ValueError, match="strictly chronological"):
        run_strategy_events(
            source,
            manifest=manifest,
            contexts=(first, duplicate),
            entrypoint="strategy.main:Strategy",
        )


def test_wire_rejects_source_manifest_digest_mismatch() -> None:
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    manifest = _manifest(source)
    with pytest.raises(ValueError, match="source digest"):
        serialize_invocation(
            source=source + "\n",
            manifest=manifest,
            context=_context(),
            entrypoint="strategy.main:Strategy",
        )

    encoded = serialize_invocation(
        source=source,
        manifest=manifest,
        context=_context(),
        entrypoint="strategy.main:Strategy",
    )
    wire_source = source.replace("\n", "\\n")
    tampered = encoded.replace(wire_source, wire_source + "\\n", 1)
    with pytest.raises(ValueError, match="source digest"):
        deserialize_invocation(tampered)

    batch_encoded = serialize_invocation_batch(
        source=source,
        manifest=manifest,
        contexts=(_context(),),
        entrypoint="strategy.main:Strategy",
    )
    batch_tampered = batch_encoded.replace(wire_source, wire_source + "\\n", 1)
    with pytest.raises(ValueError, match="source digest"):
        deserialize_invocation_batch(batch_tampered)


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
        deserialize_invocation(encoded.replace('"source":', '"source":"duplicate", "source":', 1))
    with pytest.raises(ValueError, match="non-finite"):
        deserialize_invocation(
            encoded.replace('"max_intents_per_event":100', '"max_intents_per_event":NaN', 1)
        )


def test_protocol_rejects_oversized_inbound_payload_before_json_decode() -> None:
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    encoded = serialize_invocation(
        source=source,
        manifest=_manifest(source),
        context=_context(),
        entrypoint="strategy.main:Strategy",
    )
    oversized = encoded + (" " * (MAX_WIRE_PAYLOAD_BYTES - len(encoded.encode("utf-8")) + 1))
    with pytest.raises(ValueError, match="byte limit"):
        deserialize_invocation(oversized)


def test_protocol_serializers_reject_oversized_outbound_envelopes() -> None:
    source = "x" * MAX_WIRE_PAYLOAD_BYTES
    with pytest.raises(ValueError, match="byte limit"):
        serialize_invocation(
            source=source,
            manifest=_manifest(source),
            context=_context(),
            entrypoint="strategy.main:Strategy",
        )


def test_cli_rejects_oversized_request_before_reading_unbounded_text(tmp_path) -> None:
    request = tmp_path / "oversized-request.json"
    result_path = tmp_path / "result.json"
    request.write_bytes(b"{" + (b" " * MAX_WIRE_PAYLOAD_BYTES))

    assert main(["--request", str(request), "--result", str(result_path)]) == 1
    assert not result_path.exists()


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


def test_cli_streams_context_requests_and_atomically_publishes_result_stream(tmp_path) -> None:
    source = """
class Strategy:
    def on_event(self, context):
        return [TargetPositionIntent('US.AAPL', Decimal(context.event_sequence) / Decimal(10))]
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
    encoded_request = BytesIO()
    assert (
        serialize_invocation_context_stream(
            encoded_request,
            source=source,
            manifest=manifest,
            contexts=(first, second),
            entrypoint="strategy.main:Strategy",
        )
        == 2
    )
    request = tmp_path / "context-stream.jsonl"
    result_path = tmp_path / "result-stream.jsonl"
    request.write_bytes(encoded_request.getvalue())

    assert main(["--request", str(request), "--result", str(result_path)]) == 0
    with result_path.open("rb") as result_stream:
        decoded = tuple(
            deserialize_invocation_result_stream(result_stream, expected_result_count=2)
        )
    assert len(decoded) == 2
    assert all(item.status is InvocationStatus.SUCCEEDED for item in decoded)
    assert decoded[0].intents[0].target_fraction == Decimal("0.1")
    assert decoded[1].intents[0].target_fraction == Decimal("0.2")


def test_cli_validates_complete_context_stream_before_invoking_strategy(
    tmp_path, monkeypatch
) -> None:
    source = "class Strategy:\n    def on_event(self, context):\n        return []\n"
    encoded_request = BytesIO()
    serialize_invocation_context_stream(
        encoded_request,
        source=source,
        manifest=_manifest(source),
        contexts=(_context(),),
        entrypoint="strategy.main:Strategy",
    )
    request = tmp_path / "malformed-context-stream.jsonl"
    result_path = tmp_path / "result-stream.jsonl"
    request.write_bytes(encoded_request.getvalue() + b"{malformed}\n")

    import strategy_runtime.runner as runtime_runner

    monkeypatch.setattr(
        runtime_runner,
        "run_strategy_event_stream",
        lambda *_args, **_kwargs: pytest.fail("strategy ran before input verification"),
    )
    assert main(["--request", str(request), "--result", str(result_path)]) == 1
    assert not result_path.exists()


def test_cli_returns_nonzero_without_publishing_malformed_request(tmp_path) -> None:
    request = tmp_path / "request.json"
    result_path = tmp_path / "result.json"
    request.write_text("{}", encoding="utf-8")
    assert main(["--request", str(request), "--result", str(result_path)]) == 1
    assert not result_path.exists()
