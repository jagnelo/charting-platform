"""Isolated Nautilus runtime adapter for one immutable engine-input payload.

The backend owns the engine-neutral :class:`NautilusEngineInput` contract, but
the legacy backend environment must never import Nautilus.  This module is
copied into the exact RC image and is therefore the first runtime-local bridge:
it validates the serialized input, materializes native instruments and venue,
then runs one ``BacktestEngine`` or a catalog-chunked ``BacktestNode`` and emits
scalar evidence.

The returned evidence is deliberately non-authoritative.  It proves that the
isolated runtime executed the payload; result publication still requires the
existing conformance, artifact, and worker gates.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, BinaryIO
from uuid import NAMESPACE_URL, uuid5

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.nautilus_native_event_stream import (
    deserialize_nautilus_native_event_stream,
)
from app.strategy_lab_v2.nautilus_portfolio_wire import portfolio_composition_from_wire
from app.strategy_lab_v2.nautilus_runtime_data import (
    NautilusRuntimeDataError,
    materialize_native_event,
    materialize_native_instrument,
    materialize_native_venue,
)
from app.strategy_lab_v2.nautilus_strategy_binding import component_strategy_bindings_from_wire
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
        "portfolio",
        "strategy_source_digest",
        "strategy_manifest_fingerprint",
        "entrypoint",
        "parameters",
        "random_seed",
        "evaluation_window",
        "strategy_bindings",
        "input_version",
    }
)
_TAPE_FIELDS = frozenset({"source_tape_fingerprint", "events", "adapter_version"})
_STREAM_TAPE_FIELDS = frozenset({"source_tape_fingerprint", "event_count", "adapter_version"})
NAUTILUS_CATALOG_INPUT_CHUNK_SIZE = 10_000
NAUTILUS_CATALOG_REPLAY_CHUNK_SIZE = 100_000


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


def _evaluation_window(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    window = _mapping(value, "evaluation window")
    if set(window) != {
        "fingerprint",
        "purpose",
        "warmup_start_ns",
        "start_ns",
        "end_ns",
    }:
        raise NautilusRuntimeDataError("evaluation window fields are invalid")
    require_sha256_digest(window["fingerprint"], field_name="evaluation_window.fingerprint")
    _text(window["purpose"], "evaluation_window.purpose")
    start_ns = _integer(window["start_ns"], "evaluation_window.start_ns")
    end_ns = _integer(window["end_ns"], "evaluation_window.end_ns")
    if start_ns < 0 or end_ns <= start_ns:
        raise NautilusRuntimeDataError("evaluation window bounds are invalid")
    warmup_start_ns = window["warmup_start_ns"]
    if warmup_start_ns is not None:
        warmup_start_ns = _integer(warmup_start_ns, "evaluation_window.warmup_start_ns")
        if warmup_start_ns < 0 or warmup_start_ns > start_ns:
            raise NautilusRuntimeDataError("evaluation warm-up bound is invalid")
    return window


def _validate_engine_input(
    payload: Mapping[str, Any],
) -> tuple[
    Mapping[str, Any],
    list[Mapping[str, Any]],
    list[Mapping[str, Any]],
    int,
    bool,
]:
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
    try:
        portfolio = portfolio_composition_from_wire(item["portfolio"])
    except (TypeError, ValueError) as error:
        raise NautilusRuntimeDataError("engine input portfolio policy is invalid") from error
    if item["input_version"] != "strategy-lab.nautilus-engine-input.v4":
        raise NautilusRuntimeDataError("engine input version is unsupported")
    evaluation_window = _evaluation_window(item["evaluation_window"])
    try:
        strategy_bindings = component_strategy_bindings_from_wire(item["strategy_bindings"])
    except (TypeError, ValueError) as error:
        raise NautilusRuntimeDataError(
            "engine input component strategy bindings are invalid"
        ) from error
    components_by_id = {component.component_id: component for component in portfolio.components}
    bindings_by_id = {binding.component_id: binding for binding in strategy_bindings}
    if set(bindings_by_id) != set(components_by_id):
        raise NautilusRuntimeDataError(
            "engine input strategy bindings do not cover the complete portfolio"
        )
    if any(
        bindings_by_id[component_id].strategy_fingerprint != component.strategy_fingerprint
        for component_id, component in components_by_id.items()
    ):
        raise NautilusRuntimeDataError(
            "engine input strategy binding differs from portfolio identity"
        )
    primary_binding = bindings_by_id[sorted(bindings_by_id)[0]]
    if (
        primary_binding.strategy_source_digest != item["strategy_source_digest"]
        or primary_binding.strategy_manifest_fingerprint != item["strategy_manifest_fingerprint"]
        or primary_binding.entrypoint != item["entrypoint"]
    ):
        raise NautilusRuntimeDataError(
            "engine input strategy source digest/manifest anchor differs from component bindings"
        )
    tape = _mapping(item["event_tape"], "event tape")
    tape_fields = frozenset(tape)
    if tape_fields not in {_TAPE_FIELDS, _STREAM_TAPE_FIELDS}:
        raise NautilusRuntimeDataError("event tape fields are invalid")
    require_sha256_digest(tape["source_tape_fingerprint"], field_name="source_tape_fingerprint")
    _text(tape["adapter_version"], "event tape adapter_version")
    known_ids = set(instrument_ids)
    if tape_fields == _TAPE_FIELDS:
        raw_events = tape["events"]
        if not isinstance(raw_events, list):
            raise NautilusRuntimeDataError("event tape events must be a list")
        events = [_mapping(value, "event") for value in raw_events]
        event_ids = [_text(value.get("event_id"), "event.event_id") for value in events]
        if len(event_ids) != len(set(event_ids)):
            raise NautilusRuntimeDataError("event ids must be unique")
        if any(
            _text(event.get("instrument_id"), "event.instrument_id") not in known_ids
            for event in events
        ):
            raise NautilusRuntimeDataError("event tape contains an instrument without a definition")
        if evaluation_window is not None:
            lower_ns = evaluation_window["warmup_start_ns"]
            if lower_ns is None:
                lower_ns = evaluation_window["start_ns"]
            if any(
                not lower_ns
                <= _integer(event.get("event_time_ns"), "event.event_time_ns")
                < evaluation_window["end_ns"]
                for event in events
            ):
                raise NautilusRuntimeDataError(
                    "event tape contains an event outside its evaluation input window"
                )
        return venue, instrument_items, events, len(events), False
    event_count = _integer(tape["event_count"], "event tape event_count")
    if event_count < 1:
        raise NautilusRuntimeDataError("streamed event tape must contain at least one event")
    return venue, instrument_items, [], event_count, True


def _write_native_event_catalog(
    payload: Mapping[str, Any],
    instrument_definitions: list[Mapping[str, Any]],
    native_instruments: tuple[Any, ...],
    native_event_stream: BinaryIO,
    catalog_path: Path,
    *,
    event_count: int,
) -> tuple[Any, list[Any]]:
    """Decode the authenticated native stream into bounded Parquet catalog chunks."""

    from nautilus_trader.config import BacktestDataConfig
    from nautilus_trader.model import BarType, InstrumentId
    from nautilus_trader.persistence import ParquetDataCatalog  # type: ignore[attr-defined]

    tape = payload["event_tape"]
    assert isinstance(tape, Mapping)
    source_fingerprint = tape["source_tape_fingerprint"]
    adapter_version = tape["adapter_version"]
    assert isinstance(source_fingerprint, str)
    assert isinstance(adapter_version, str)
    instrument_by_id = {item["instrument_id"]: item for item in instrument_definitions}
    catalog_path.mkdir(parents=True, exist_ok=True)
    catalog = ParquetDataCatalog(str(catalog_path))
    catalog.write_instruments(list(native_instruments))
    pending: dict[tuple[str, str], list[Any]] = {}
    observed_types: set[str] = set()
    observed_instruments: dict[str, set[str]] = {
        event_type: set() for event_type in ("quote", "trade", "ohlcv")
    }
    pending_count = 0

    def flush() -> None:
        nonlocal pending_count
        for (event_type, _instrument_id), records in sorted(pending.items()):
            if event_type == "quote":
                catalog.write_quote_ticks(records)
            elif event_type == "trade":
                catalog.write_trade_ticks(records)
            elif event_type == "ohlcv":
                catalog.write_bars(records)
            else:  # pragma: no cover - event protocol validation rejects this
                raise NautilusRuntimeDataError("native event type has no catalog writer")
        pending.clear()
        pending_count = 0

    native_event_stream.seek(0)
    records = deserialize_nautilus_native_event_stream(
        native_event_stream,
        expected_source_tape_fingerprint=source_fingerprint,
        expected_adapter_version=adapter_version,
        expected_event_count=event_count,
    )
    observed_count = 0
    for record in records:
        instrument_id = record["instrument_id"]
        definition = instrument_by_id.get(instrument_id)
        if definition is None:
            raise NautilusRuntimeDataError(
                "native event stream contains an instrument without a definition"
            )
        event_type = record["event_type"]
        native_event = materialize_native_event(
            {key: value for key, value in record.items() if key != "native_init_time_ns"},
            definition,
            native_init_time_ns=record["native_init_time_ns"],
        )
        pending.setdefault((event_type, instrument_id), []).append(native_event)
        pending_count += 1
        observed_count += 1
        observed_types.add(event_type)
        observed_instruments[event_type].add(instrument_id)
        if pending_count >= NAUTILUS_CATALOG_INPUT_CHUNK_SIZE:
            flush()
    flush()
    if observed_count != event_count:
        raise NautilusRuntimeDataError(
            "native event count differs from its authenticated reference"
        )

    data_configs: list[Any] = []
    for event_type, data_type in (("quote", "QuoteTick"), ("trade", "TradeTick")):
        identifiers = observed_instruments[event_type]
        if identifiers:
            data_configs.append(
                BacktestDataConfig(
                    data_type=data_type,  # type: ignore[call-arg]
                    catalog_path=str(catalog_path),
                    instrument_ids=tuple(
                        InstrumentId.from_str(item) for item in sorted(identifiers)
                    ),  # type: ignore[arg-type]
                )
            )
    if "ohlcv" in observed_types:
        data_configs.append(
            BacktestDataConfig(
                data_type="Bar",  # type: ignore[call-arg]
                catalog_path=str(catalog_path),
                bar_types=[
                    str(BarType.from_str(instrument_by_id[item]["bar_type"]))
                    for item in sorted(observed_instruments["ohlcv"])
                ],
            )
        )
    return catalog, data_configs


def run_native_backtest(
    payload: Mapping[str, Any],
    *,
    serialized_strategy_invocation_batch: str | None = None,
    invocation_context_stream: BinaryIO | None = None,
    native_event_stream: BinaryIO | None = None,
    native_event_stream_digest: str | None = None,
    expected_context_count: int | None = None,
    expected_component_context_counts: Mapping[str, int] | None = None,
    invocation_result_stream: BinaryIO | None = None,
    max_invocation_result_bytes: int = MAX_INVOCATION_RESULT_STREAM_BYTES,
) -> dict[str, Any]:
    """Run one validated engine input and SDK invocation input in the isolated image."""

    (
        venue_definition,
        instrument_definitions,
        event_definitions,
        event_count,
        expects_native_event_stream,
    ) = _validate_engine_input(payload)
    if expects_native_event_stream != (native_event_stream is not None):
        raise NautilusRuntimeDataError(
            "native event stream does not match the engine input tape reference"
        )
    if native_event_stream is None:
        if native_event_stream_digest is not None:
            raise NautilusRuntimeDataError(
                "native event stream digest requires the matching event stream"
            )
    else:
        if not isinstance(native_event_stream_digest, str):
            raise NautilusRuntimeDataError("native event stream digest is required")
        require_sha256_digest(
            native_event_stream_digest,
            field_name="native_event_stream_digest",
        )
    if serialized_strategy_invocation_batch is None and invocation_context_stream is None:
        raise NautilusRuntimeDataError("serialized strategy invocation batch is required")
    if expected_component_context_counts is not None:
        if invocation_context_stream is None or native_event_stream is None:
            raise NautilusRuntimeDataError(
                "component context streams require native event streaming"
            )
        if (
            not isinstance(expected_component_context_counts, Mapping)
            or not expected_component_context_counts
        ):
            raise NautilusRuntimeDataError("component context count bindings are invalid")
        if any(
            not isinstance(component_id, str)
            or not component_id.strip()
            or not isinstance(count, int)
            or isinstance(count, bool)
            or count < 1
            for component_id, count in expected_component_context_counts.items()
        ):
            raise NautilusRuntimeDataError("component context counts must be positive integers")
        if sum(expected_component_context_counts.values()) != expected_context_count:
            raise NautilusRuntimeDataError(
                "component context counts differ from the total authenticated context count"
            )
    strategy_bridge = build_native_strategy_bridge(
        payload,
        instrument_definitions,
        event_definitions,
        serialized_strategy_invocation_batch,
        invocation_context_stream=invocation_context_stream,
        native_event_stream=native_event_stream,
        expected_context_count=expected_context_count,
        expected_component_context_counts=expected_component_context_counts,
        invocation_result_stream=invocation_result_stream,
        max_invocation_result_bytes=max_invocation_result_bytes,
    )

    native_instruments = tuple(
        materialize_native_instrument(definition) for definition in instrument_definitions
    )
    native_venue, oms_type, account_type, balances = materialize_native_venue(venue_definition)
    from nautilus_trader import __version__  # type: ignore[import-not-found,attr-defined]
    from nautilus_trader.backtest import (  # type: ignore[import-not-found,attr-defined]
        BacktestEngine,
        BacktestNode,
    )
    from nautilus_trader.common import LoggerConfig  # type: ignore[import-not-found,attr-defined]
    from nautilus_trader.config import (
        BacktestEngineConfig,
        BacktestRunConfig,
        BacktestVenueConfig,
    )

    def make_evidence(result: Any, invocation_result_output: Any) -> dict[str, Any]:
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
            "input_fingerprint": (
                content_digest(payload)
                if native_event_stream_digest is None
                else content_digest(
                    {
                        "engine_input": payload,
                        "native_event_stream_digest": native_event_stream_digest,
                    }
                )
            ),
            "input_event_count": event_count,
            **(
                {
                    "native_event_stream_digest": native_event_stream_digest,
                    "native_data_source": "parquet_catalog_chunks",
                    "catalog_input_chunk_size": NAUTILUS_CATALOG_INPUT_CHUNK_SIZE,
                    "catalog_replay_chunk_size": NAUTILUS_CATALOG_REPLAY_CHUNK_SIZE,
                }
                if native_event_stream_digest is not None
                else {}
            ),
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

    if native_event_stream is not None:
        from nautilus_trader.model import BookType, Currency  # type: ignore[attr-defined]

        with TemporaryDirectory(prefix="strategy-lab-nautilus-catalog-") as temporary_root:
            catalog_path = Path(temporary_root) / "catalog"
            _catalog, data_configs = _write_native_event_catalog(
                payload,
                instrument_definitions,
                native_instruments,
                native_event_stream,
                catalog_path,
                event_count=event_count,
            )
            if not data_configs:
                raise NautilusRuntimeDataError("native event stream contains no supported data")
            venue_config = BacktestVenueConfig(
                name=str(native_venue),
                oms_type=oms_type,
                account_type=account_type,
                starting_balances=[str(balance) for balance in balances],
                book_type=BookType.L1_MBP,
                base_currency=Currency.from_str(venue_definition["base_currency"]),
            )
            run_config = BacktestRunConfig(
                venues=[venue_config],
                data=data_configs,
                engine=BacktestEngineConfig(
                    logging=LoggerConfig(bypass_logging=True),
                    bypass_logging=True,  # type: ignore[call-arg]
                ),
                id=str(uuid5(NAMESPACE_URL, content_digest(payload))),  # type: ignore[call-arg]
                chunk_size=NAUTILUS_CATALOG_REPLAY_CHUNK_SIZE,
                raise_exception=True,
                dispose_on_completion=False,
            )
            node = BacktestNode(configs=[run_config])
            try:
                node.build()
                node.add_strategy(run_config.id, strategy_bridge.strategy)
                results = node.run()
                if not isinstance(results, list) or len(results) != 1:
                    raise NautilusRuntimeDataError(
                        "catalog-backed Nautilus node did not return exactly one run result"
                    )
                invocation_result_output = strategy_bridge.result_output()
                return make_evidence(results[0], invocation_result_output)
            finally:
                node.dispose()

    from nautilus_trader.model import Currency  # type: ignore[attr-defined]

    engine = BacktestEngine(
        BacktestEngineConfig(
            logging=LoggerConfig(bypass_logging=True),
            bypass_logging=True,  # type: ignore[call-arg]
        )
    )
    try:
        engine.add_venue(
            native_venue,
            oms_type,
            account_type,
            balances,
            base_currency=Currency.from_str(venue_definition["base_currency"]),
        )
        for instrument in native_instruments:
            engine.add_instrument(instrument)
        engine.add_strategy(strategy_bridge.strategy)
        native_events = [
            materialize_native_event(
                event,
                next(
                    definition
                    for definition in instrument_definitions
                    if definition["instrument_id"] == event["instrument_id"]
                ),
            )
            for event in event_definitions
        ]
        if native_events:
            engine.add_data(native_events, sort=True)
        engine.run()
        result = engine.get_result()
        invocation_result_output = strategy_bridge.result_output()
        return make_evidence(result, invocation_result_output)
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
