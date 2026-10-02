"""Isolated Nautilus runtime adapter for one immutable engine-input payload.

The backend owns the engine-neutral :class:`NautilusEngineInput` contract, but
the legacy backend environment must never import Nautilus.  This module is
copied into the exact RC image and is therefore the first runtime-local bridge:
it validates the serialized input, materializes native instruments, venue, and
market events, runs one native ``BacktestEngine``, and emits scalar evidence.

The returned evidence is deliberately non-authoritative.  It proves that the
isolated runtime executed the payload; result publication still requires the
existing conformance, artifact, and worker gates.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping
from typing import Any, BinaryIO

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.nautilus_runtime_data import (
    NautilusRuntimeDataError,
    materialize_native_event,
    materialize_native_instrument,
    materialize_native_venue,
)
from app.strategy_lab_v2.nautilus_strategy_bridge import build_native_strategy_bridge
from strategy_runtime import (
    INVOCATION_RESULT_STREAM_PROTOCOL_VERSION,
    MAX_INVOCATION_RESULT_STREAM_BYTES,
    InvocationResultStreamSummary,
)

NAUTILUS_RUNTIME_ADAPTER_VERSION = "strategy-lab.nautilus-runtime-adapter.v1"

_ENGINE_INPUT_FIELDS = frozenset(
    {
        "trial_id",
        "attempt_id",
        "data_snapshot_fingerprint",
        "event_tape",
        "instruments",
        "venue",
        "strategy_source_digest",
        "strategy_manifest_fingerprint",
        "entrypoint",
        "parameters",
        "random_seed",
        "input_version",
    }
)
_TAPE_FIELDS = frozenset({"source_tape_fingerprint", "events", "adapter_version"})


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise NautilusRuntimeDataError(f"{field_name} must be a string-keyed mapping")
    return value


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NautilusRuntimeDataError(f"{field_name} must be a non-empty string")
    if any(character in value for character in "\x00\r\n"):
        raise NautilusRuntimeDataError(f"{field_name} contains control characters")
    return value


def _integer(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise NautilusRuntimeDataError(f"{field_name} must be an integer")
    return value


def _validate_engine_input(
    payload: Mapping[str, Any],
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    item = _mapping(payload, "engine input")
    if set(item) != _ENGINE_INPUT_FIELDS:
        raise NautilusRuntimeDataError("engine input fields are invalid")
    for field_name in ("trial_id", "attempt_id", "entrypoint", "input_version"):
        _text(item[field_name], field_name)
    for field_name in (
        "data_snapshot_fingerprint",
        "strategy_source_digest",
        "strategy_manifest_fingerprint",
    ):
        require_sha256_digest(item[field_name], field_name=field_name)
    _integer(item["random_seed"], "random_seed")
    instruments = item["instruments"]
    if not isinstance(instruments, list) or not instruments:
        raise NautilusRuntimeDataError("engine input instruments must be a non-empty list")
    instrument_items = [_mapping(value, "instrument definition") for value in instruments]
    instrument_ids = [_text(value["instrument_id"], "instrument_id") for value in instrument_items]
    if len(instrument_ids) != len(set(instrument_ids)):
        raise NautilusRuntimeDataError("engine input instrument ids must be unique")
    venue = _mapping(item["venue"], "venue definition")
    tape = _mapping(item["event_tape"], "event tape")
    if set(tape) != _TAPE_FIELDS:
        raise NautilusRuntimeDataError("event tape fields are invalid")
    _text(tape["source_tape_fingerprint"], "source_tape_fingerprint")
    _text(tape["adapter_version"], "event tape adapter_version")
    raw_events = tape["events"]
    if not isinstance(raw_events, list):
        raise NautilusRuntimeDataError("event tape events must be a list")
    events = [_mapping(value, "event") for value in raw_events]
    event_ids = [_text(value.get("event_id"), "event.event_id") for value in events]
    if len(event_ids) != len(set(event_ids)):
        raise NautilusRuntimeDataError("event ids must be unique")
    known_ids = set(instrument_ids)
    if any(
        _text(event.get("instrument_id"), "event.instrument_id") not in known_ids
        for event in events
    ):
        raise NautilusRuntimeDataError("event tape contains an instrument without a definition")
    return venue, instrument_items, events


def run_native_backtest(
    payload: Mapping[str, Any],
    *,
    serialized_strategy_invocation_batch: str | None = None,
    invocation_context_stream: BinaryIO | None = None,
    expected_context_count: int | None = None,
    invocation_result_stream: BinaryIO | None = None,
    max_invocation_result_bytes: int = MAX_INVOCATION_RESULT_STREAM_BYTES,
) -> dict[str, Any]:
    """Run one validated engine input and SDK invocation input in the isolated image."""

    venue_definition, instrument_definitions, event_definitions = _validate_engine_input(payload)
    if serialized_strategy_invocation_batch is None and invocation_context_stream is None:
        raise NautilusRuntimeDataError("serialized strategy invocation batch is required")
    strategy_bridge = build_native_strategy_bridge(
        payload,
        instrument_definitions,
        event_definitions,
        serialized_strategy_invocation_batch,
        invocation_context_stream=invocation_context_stream,
        expected_context_count=expected_context_count,
        invocation_result_stream=invocation_result_stream,
        max_invocation_result_bytes=max_invocation_result_bytes,
    )

    native_instruments = tuple(
        materialize_native_instrument(definition) for definition in instrument_definitions
    )
    native_venue, oms_type, account_type, balances = materialize_native_venue(venue_definition)
    native_events = [
        materialize_native_event(
            event,
            instrument_definitions[
                next(
                    index
                    for index, definition in enumerate(instrument_definitions)
                    if definition["instrument_id"] == event["instrument_id"]
                )
            ],
        )
        for event in event_definitions
    ]
    from nautilus_trader import __version__  # type: ignore[import-not-found,attr-defined]
    from nautilus_trader.backtest import (  # type: ignore[import-not-found,attr-defined]
        BacktestEngine,
        BacktestEngineConfig,
    )
    from nautilus_trader.common import LoggerConfig  # type: ignore[import-not-found,attr-defined]

    engine = BacktestEngine(
        BacktestEngineConfig(
            logging=LoggerConfig(bypass_logging=True),
            bypass_logging=True,
        )
    )
    try:
        engine.add_venue(native_venue, oms_type, account_type, balances)
        for instrument in native_instruments:
            engine.add_instrument(instrument)
        engine.add_strategy(strategy_bridge.strategy)
        if native_events:
            engine.add_data(native_events, sort=True)
        engine.run()
        result = engine.get_result()
        invocation_result_output = strategy_bridge.result_output()
        summary = getattr(result, "summary", {})
        if not isinstance(summary, Mapping):
            raise NautilusRuntimeDataError("Nautilus result summary is not a mapping")
        scalar_summary = {str(key): str(value) for key, value in sorted(summary.items())}
        result_evidence: dict[str, Any]
        if isinstance(invocation_result_output, InvocationResultStreamSummary):
            result_evidence = {
                "strategy_invocation_result_stream": {
                    "protocol_version": INVOCATION_RESULT_STREAM_PROTOCOL_VERSION,
                    "content_digest": invocation_result_output.content_digest,
                    "byte_length": invocation_result_output.byte_length,
                    "result_count": invocation_result_output.result_count,
                    "all_succeeded": invocation_result_output.all_succeeded,
                }
            }
        else:
            invocation_result_wire = invocation_result_output
            if not isinstance(invocation_result_wire, str):
                raise NautilusRuntimeDataError("strategy invocation result output is invalid")
            result_evidence = {
                "strategy_invocation_result_wire": invocation_result_wire,
                "strategy_invocation_result_digest": content_digest(invocation_result_wire),
                "strategy_invocation_count": result_invocation_count(invocation_result_wire),
            }
        evidence = {
            "adapter_version": NAUTILUS_RUNTIME_ADAPTER_VERSION,
            "authoritative": False,
            "engine": "nautilus",
            "engine_version": __version__,
            "input_fingerprint": content_digest(payload),
            "input_event_count": len(native_events),
            "strategy_invocation_input_digest": strategy_bridge.input_fingerprint,
            "strategy_invocation_input_protocol": strategy_bridge.input_protocol,
            **(
                {"strategy_invocation_batch_digest": strategy_bridge.input_fingerprint}
                if strategy_bridge.input_protocol == "batch"
                else {}
            ),
            **result_evidence,
            "iterations": int(result.iterations),
            "total_events": int(result.total_events),
            "total_orders": int(result.total_orders),
            "total_positions": int(result.total_positions),
            "summary": scalar_summary,
            "forward_event_tape_parity": "deferred_authoritative_adapter",
        }
        evidence["execution_evidence_digest"] = content_digest(evidence)
        return evidence
    finally:
        engine.dispose()


def result_invocation_count(result_wire: str) -> int:
    """Validate and count the emitted invocation batch for summary evidence."""

    from strategy_runtime import deserialize_invocation_batch_result

    return len(deserialize_invocation_batch_result(result_wire))


def runtime_package_version() -> str:
    """Return the exact package version from the isolated distribution."""

    return importlib.metadata.version("nautilus-trader")


__all__ = [
    "NAUTILUS_RUNTIME_ADAPTER_VERSION",
    "NautilusRuntimeDataError",
    "run_native_backtest",
    "runtime_package_version",
]
