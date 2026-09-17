"""Canonical JSON wire protocol for the restricted strategy runtime.

The protocol is intentionally explicit instead of relying on pickle or Python
object serialization.  It preserves Decimal, datetime, tuple, set, and mapping
identity, then reconstructs the engine-neutral SDK records before invocation.
The request envelope is suitable for a read-only mounted input bundle; the
result envelope contains only typed intents and digest-bound evidence.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

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
    StrategyIntent,
    StrategySdkManifest,
    TargetPositionIntent,
    TimeInForce,
)

WIRE_PROTOCOL_VERSION = "strategy-lab.strategy-runtime.v1"
BATCH_WIRE_PROTOCOL_VERSION = "strategy-lab.strategy-runtime.batch.v1"


class _DuplicateFieldError(ValueError):
    """Raised when a JSON object contains the same field more than once."""


class _NonFiniteConstantError(ValueError):
    """Raised when a parser encounters a non-standard non-finite constant."""


def _reject_duplicate_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateFieldError(key)
        result[key] = value
    return result


def _reject_non_finite_constant(value: str) -> Any:
    raise _NonFiniteConstantError(value)


def _load_json(payload: str, field_name: str) -> Any:
    try:
        return json.loads(
            payload,
            object_pairs_hook=_reject_duplicate_fields,
            parse_constant=_reject_non_finite_constant,
        )
    except _DuplicateFieldError as error:
        raise ValueError(f"{field_name} contains duplicate JSON fields") from error
    except _NonFiniteConstantError as error:
        raise ValueError(f"{field_name} contains a non-finite JSON constant") from error
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} is not valid JSON") from error


def _iso_datetime(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("wire datetimes must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _decode_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed.astimezone(UTC)


def _encode_value(value: Any) -> Any:
    """Encode JSON-shaped values while retaining the value's scalar type."""

    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("wire Decimal values must be finite")
        return {"$type": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"$type": "datetime", "value": _iso_datetime(value)}
    if isinstance(value, date):
        return {"$type": "date", "value": value.isoformat()}
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("wire float values must be finite")
        return {"$type": "float", "value": value.hex()}
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("wire mapping keys must be strings")
        return {
            "$type": "mapping",
            "value": {key: _encode_value(value[key]) for key in sorted(value)},
        }
    if isinstance(value, tuple):
        return {"$type": "tuple", "value": [_encode_value(item) for item in value]}
    if isinstance(value, list):
        return {"$type": "list", "value": [_encode_value(item) for item in value]}
    if isinstance(value, set | frozenset):
        encoded = [_encode_value(item) for item in value]
        encoded.sort(key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")))
        return {"$type": "set", "value": encoded}
    raise TypeError(f"unsupported wire value: {type(value).__name__}")


def _decode_value(value: Any) -> Any:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if value != value or value in {float("inf"), float("-inf")}:
            raise ValueError("wire float values must be finite")
        return value
    if not isinstance(value, Mapping):
        raise TypeError("wire values must be JSON scalars or tagged objects")
    if set(value) != {"$type", "value"}:
        raise ValueError("wire tagged values must contain $type and value only")
    kind = value["$type"]
    payload = value["value"]
    if kind == "decimal":
        if not isinstance(payload, str):
            raise TypeError("wire decimal payload must be a string")
        decimal_result = Decimal(payload)
        if not decimal_result.is_finite():
            raise ValueError("wire Decimal values must be finite")
        return decimal_result
    if kind == "datetime":
        return _decode_datetime(payload, "wire datetime")
    if kind == "date":
        if not isinstance(payload, str):
            raise TypeError("wire date payload must be a string")
        return date.fromisoformat(payload)
    if kind == "float":
        if not isinstance(payload, str):
            raise TypeError("wire float payload must be a hexadecimal string")
        float_result = float.fromhex(payload)
        if float_result != float_result or float_result in {float("inf"), float("-inf")}:
            raise ValueError("wire float values must be finite")
        return float_result
    if kind in {"mapping", "tuple", "list", "set"}:
        if kind == "mapping":
            if not isinstance(payload, Mapping) or any(
                not isinstance(key, str) for key in payload
            ):
                raise TypeError("wire mapping payload must be a string-keyed object")
            return {key: _decode_value(payload[key]) for key in sorted(payload)}
        if not isinstance(payload, list):
            raise TypeError(f"wire {kind} payload must be a list")
        decoded = [_decode_value(item) for item in payload]
        if kind == "tuple":
            return tuple(decoded)
        if kind == "set":
            try:
                return set(decoded)
            except TypeError as error:
                raise TypeError("wire set payload must contain hashable values") from error
        return decoded
    raise ValueError(f"unsupported wire value type: {kind!r}")


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be an object")
    if any(not isinstance(key, str) for key in value):
        raise TypeError(f"{field_name} keys must be strings")
    return value


def _list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")
    return value


def _encode_requirement(requirement: CapabilityRequirement) -> dict[str, Any]:
    if not isinstance(requirement, CapabilityRequirement):
        raise TypeError("data dependency requirement must use CapabilityRequirement")
    return {
        "instrument_id": requirement.instrument_id,
        "product_class": requirement.product_class.value,
        "event_granularity": requirement.event_granularity.value,
        "event_type": requirement.event_type,
        "timeframe": requirement.timeframe,
        "start": _iso_datetime(requirement.start),
        "end": _iso_datetime(requirement.end),
        "adjustment": requirement.adjustment.value,
        "session": requirement.session,
        "feed": requirement.feed,
        "execution_model": requirement.execution_model,
        "account_model": requirement.account_model,
        "corporate_action_semantics": requirement.corporate_action_semantics,
    }


def _decode_requirement(value: Any) -> CapabilityRequirement:
    item = _mapping(value, "requirement")
    required = {
        "instrument_id",
        "product_class",
        "event_granularity",
        "event_type",
        "timeframe",
        "start",
        "end",
        "adjustment",
        "session",
        "feed",
        "execution_model",
        "account_model",
        "corporate_action_semantics",
    }
    if set(item) != required:
        raise ValueError("requirement fields are invalid")
    try:
        return CapabilityRequirement(
            instrument_id=item["instrument_id"],
            product_class=ProductClass(item["product_class"]),
            event_granularity=EventGranularity(item["event_granularity"]),
            event_type=item["event_type"],
            timeframe=item["timeframe"],
            start=_decode_datetime(item["start"], "requirement.start"),
            end=_decode_datetime(item["end"], "requirement.end"),
            adjustment=AdjustmentMode(item["adjustment"]),
            session=item["session"],
            feed=item["feed"],
            execution_model=item["execution_model"],
            account_model=item["account_model"],
            corporate_action_semantics=item["corporate_action_semantics"],
        )
    except (TypeError, ValueError) as error:
        raise ValueError("requirement values are invalid") from error


def _encode_manifest(manifest: StrategySdkManifest) -> dict[str, Any]:
    if not isinstance(manifest, StrategySdkManifest):
        raise TypeError("manifest must use StrategySdkManifest")
    strategy = manifest.strategy
    return {
        "strategy": {
            "strategy_id": strategy.strategy_id,
            "version_id": strategy.version_id,
            "sdk_version": strategy.sdk_version,
            "source_digest": strategy.source_digest,
            "dependencies": [
                {
                    "distribution": item.distribution,
                    "version": item.version,
                    "artifact_digest": item.artifact_digest,
                }
                for item in strategy.dependencies
            ],
            "parameter_schema": _encode_value(strategy.parameter_schema),
            "default_parameters": _encode_value(strategy.default_parameters),
        },
        "data_dependencies": [
            {
                "dependency_id": item.dependency_id,
                "requirement": _encode_requirement(item.requirement),
                "fields": list(item.fields),
                "lookback_periods": item.lookback_periods,
            }
            for item in manifest.data_dependencies
        ],
        "model_dependencies": [
            {
                "distribution": item.distribution,
                "version": item.version,
                "artifact_digest": item.artifact_digest,
            }
            for item in manifest.model_dependencies
        ],
    }


def _decode_dependency(value: Any) -> StrategyDependency:
    item = _mapping(value, "strategy dependency")
    if set(item) != {"distribution", "version", "artifact_digest"}:
        raise ValueError("strategy dependency fields are invalid")
    return StrategyDependency(item["distribution"], item["version"], item["artifact_digest"])


def _decode_manifest(value: Any) -> StrategySdkManifest:
    root = _mapping(value, "manifest")
    if set(root) != {"strategy", "data_dependencies", "model_dependencies"}:
        raise ValueError("manifest fields are invalid")
    strategy_data = _mapping(root["strategy"], "strategy")
    if set(strategy_data) != {
        "strategy_id",
        "version_id",
        "sdk_version",
        "source_digest",
        "dependencies",
        "parameter_schema",
        "default_parameters",
    }:
        raise ValueError("strategy fields are invalid")
    strategy = StrategyVersion(
        strategy_id=strategy_data["strategy_id"],
        version_id=strategy_data["version_id"],
        sdk_version=strategy_data["sdk_version"],
        source_digest=strategy_data["source_digest"],
        dependencies=tuple(
            _decode_dependency(item) for item in _list(strategy_data["dependencies"], "dependencies")
        ),
        parameter_schema=_mapping(
            _decode_value(strategy_data["parameter_schema"]), "parameter_schema"
        ),
        default_parameters=_mapping(
            _decode_value(strategy_data["default_parameters"]), "default_parameters"
        ),
    )
    data_dependencies: list[StrategyDataDependency] = []
    for raw in _list(root["data_dependencies"], "data_dependencies"):
        item = _mapping(raw, "data dependency")
        if set(item) != {"dependency_id", "requirement", "fields", "lookback_periods"}:
            raise ValueError("data dependency fields are invalid")
        fields = _list(item["fields"], "data dependency fields")
        data_dependencies.append(
            StrategyDataDependency(
                dependency_id=item["dependency_id"],
                requirement=_decode_requirement(item["requirement"]),
                fields=tuple(fields),
                lookback_periods=item["lookback_periods"],
            )
        )
    model_dependencies = tuple(
        _decode_dependency(item)
        for item in _list(root["model_dependencies"], "model_dependencies")
    )
    return StrategySdkManifest(strategy, tuple(data_dependencies), model_dependencies)


def _encode_context(context: StrategyContext) -> dict[str, Any]:
    if not isinstance(context, StrategyContext):
        raise TypeError("context must use StrategyContext")
    return {
        "event_time": _iso_datetime(context.event_time),
        "event_sequence": context.event_sequence,
        "random_seed": context.random_seed,
        "parameters": _encode_value(context.parameters),
        "market_events": {
            dependency_id: [
                {
                    "dependency_id": event.dependency_id,
                    "event_id": event.event_id,
                    "instrument_id": event.instrument_id,
                    "event_time": _iso_datetime(event.event_time),
                    "sequence": event.sequence,
                    "values": _encode_value(event.values),
                }
                for event in events
            ]
            for dependency_id, events in sorted(context.market_events.items())
        },
        "positions": {
            instrument_id: {
                "instrument_id": position.instrument_id,
                "quantity": _encode_value(position.quantity),
                "average_price": _encode_value(position.average_price),
                "market_value": _encode_value(position.market_value),
            }
            for instrument_id, position in sorted(context.positions.items())
        },
    }


def _decode_context(value: Any) -> StrategyContext:
    root = _mapping(value, "context")
    if set(root) != {
        "event_time",
        "event_sequence",
        "random_seed",
        "parameters",
        "market_events",
        "positions",
    }:
        raise ValueError("context fields are invalid")
    event_root = _mapping(root["market_events"], "market_events")
    market_events: dict[str, tuple[MarketEvent, ...]] = {}
    for dependency_id, raw_events in event_root.items():
        events: list[MarketEvent] = []
        for raw in _list(raw_events, f"market_events[{dependency_id}]"):
            item = _mapping(raw, "market event")
            if set(item) != {
                "dependency_id",
                "event_id",
                "instrument_id",
                "event_time",
                "sequence",
                "values",
            }:
                raise ValueError("market event fields are invalid")
            events.append(
                MarketEvent(
                    dependency_id=item["dependency_id"],
                    event_id=item["event_id"],
                    instrument_id=item["instrument_id"],
                    event_time=_decode_datetime(item["event_time"], "market event time"),
                    sequence=item["sequence"],
                    values=_mapping(_decode_value(item["values"]), "market event values"),
                )
            )
        market_events[dependency_id] = tuple(events)

    positions_root = _mapping(root["positions"], "positions")
    positions: dict[str, PositionSnapshot] = {}
    for instrument_id, raw in positions_root.items():
        item = _mapping(raw, "position")
        if set(item) != {"instrument_id", "quantity", "average_price", "market_value"}:
            raise ValueError("position fields are invalid")
        positions[instrument_id] = PositionSnapshot(
            instrument_id=item["instrument_id"],
            quantity=_decode_value(item["quantity"]),
            average_price=_decode_value(item["average_price"]),
            market_value=_decode_value(item["market_value"]),
        )
    return StrategyContext(
        event_time=_decode_datetime(root["event_time"], "context.event_time"),
        event_sequence=root["event_sequence"],
        random_seed=root["random_seed"],
        parameters=_mapping(_decode_value(root["parameters"]), "parameters"),
        market_events=market_events,
        positions=positions,
    )


def serialize_invocation(
    *,
    source: str,
    manifest: StrategySdkManifest,
    context: StrategyContext,
    entrypoint: str,
    max_intents_per_event: int = 100,
) -> str:
    """Serialize a deterministic invocation envelope for a mounted request file."""

    if not isinstance(source, str):
        raise TypeError("source must be a string")
    if not isinstance(entrypoint, str) or not entrypoint.strip():
        raise ValueError("entrypoint must not be empty")
    if (
        not isinstance(max_intents_per_event, int)
        or isinstance(max_intents_per_event, bool)
        or max_intents_per_event < 1
    ):
        raise ValueError("max_intents_per_event must be a positive integer")
    payload = {
        "protocol_version": WIRE_PROTOCOL_VERSION,
        "source": source,
        "manifest": _encode_manifest(manifest),
        "context": _encode_context(context),
        "entrypoint": entrypoint,
        "max_intents_per_event": max_intents_per_event,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deserialize_invocation(payload: str) -> tuple[str, StrategySdkManifest, StrategyContext, str, int]:
    """Decode and validate a serialized invocation envelope."""

    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("invocation payload must not be empty")
    root = _load_json(payload, "invocation payload")
    item = _mapping(root, "invocation")
    if set(item) != {
        "protocol_version",
        "source",
        "manifest",
        "context",
        "entrypoint",
        "max_intents_per_event",
    }:
        raise ValueError("invocation fields are invalid")
    if item["protocol_version"] != WIRE_PROTOCOL_VERSION:
        raise ValueError("unsupported strategy runtime protocol version")
    source = item["source"]
    if not isinstance(source, str):
        raise TypeError("invocation source must be a string")
    entrypoint = item["entrypoint"]
    if not isinstance(entrypoint, str) or not entrypoint.strip():
        raise ValueError("invocation entrypoint must not be empty")
    max_intents = item["max_intents_per_event"]
    if not isinstance(max_intents, int) or isinstance(max_intents, bool) or max_intents < 1:
        raise ValueError("invocation max_intents_per_event must be positive")
    return source, _decode_manifest(item["manifest"]), _decode_context(item["context"]), entrypoint, max_intents


def serialize_invocation_batch(
    *,
    source: str,
    manifest: StrategySdkManifest,
    contexts: Sequence[StrategyContext],
    entrypoint: str,
    max_intents_per_event: int = 100,
) -> str:
    """Serialize a deterministic multi-context request for one runtime session."""

    if not isinstance(source, str):
        raise TypeError("batch invocation source must be a string")
    if not isinstance(contexts, Sequence) or isinstance(contexts, str | bytes):
        raise TypeError("batch invocation contexts must be a sequence")
    contexts_tuple = tuple(contexts)
    if not contexts_tuple:
        raise ValueError("batch invocation contexts must not be empty")
    if any(not isinstance(context, StrategyContext) for context in contexts_tuple):
        raise TypeError("batch invocation contexts must use StrategyContext values")
    if not isinstance(entrypoint, str) or not entrypoint.strip():
        raise ValueError("batch invocation entrypoint must not be empty")
    if (
        not isinstance(max_intents_per_event, int)
        or isinstance(max_intents_per_event, bool)
        or max_intents_per_event < 1
    ):
        raise ValueError("batch invocation max_intents_per_event must be positive")
    payload = {
        "protocol_version": BATCH_WIRE_PROTOCOL_VERSION,
        "source": source,
        "manifest": _encode_manifest(manifest),
        "contexts": [_encode_context(context) for context in contexts_tuple],
        "entrypoint": entrypoint,
        "max_intents_per_event": max_intents_per_event,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deserialize_invocation_batch(
    payload: str,
) -> tuple[str, StrategySdkManifest, tuple[StrategyContext, ...], str, int]:
    """Decode a strict multi-context request envelope."""

    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("batch invocation payload must not be empty")
    root = _load_json(payload, "batch invocation payload")
    item = _mapping(root, "batch invocation")
    if set(item) != {
        "protocol_version",
        "source",
        "manifest",
        "contexts",
        "entrypoint",
        "max_intents_per_event",
    }:
        raise ValueError("batch invocation fields are invalid")
    if item["protocol_version"] != BATCH_WIRE_PROTOCOL_VERSION:
        raise ValueError("unsupported strategy runtime batch protocol version")
    source = item["source"]
    if not isinstance(source, str):
        raise TypeError("batch invocation source must be a string")
    entrypoint = item["entrypoint"]
    if not isinstance(entrypoint, str) or not entrypoint.strip():
        raise ValueError("batch invocation entrypoint must not be empty")
    max_intents = item["max_intents_per_event"]
    if not isinstance(max_intents, int) or isinstance(max_intents, bool) or max_intents < 1:
        raise ValueError("batch invocation max_intents_per_event must be positive")
    raw_contexts = _list(item["contexts"], "batch invocation contexts")
    if not raw_contexts:
        raise ValueError("batch invocation contexts must not be empty")
    contexts = tuple(_decode_context(raw) for raw in raw_contexts)
    return source, _decode_manifest(item["manifest"]), contexts, entrypoint, max_intents


def _encode_intent(intent: StrategyIntent) -> dict[str, Any]:
    if isinstance(intent, OrderIntent):
        return {
            "type": "order",
            "instrument_id": intent.instrument_id,
            "side": intent.side.value,
            "quantity": _encode_value(intent.quantity),
            "order_type": intent.order_type.value,
            "time_in_force": intent.time_in_force.value,
            "limit_price": _encode_value(intent.limit_price),
            "stop_price": _encode_value(intent.stop_price),
            "client_tag": intent.client_tag,
        }
    if isinstance(intent, TargetPositionIntent):
        return {
            "type": "target_position",
            "instrument_id": intent.instrument_id,
            "target_fraction": _encode_value(intent.target_fraction),
        }
    raise TypeError("result intents must use typed StrategyIntent values")


def _invocation_result_payload(result: Any) -> dict[str, Any]:
    """Return the strict JSON-shaped payload shared by single and batch results."""

    from strategy_runtime.runner import StrategyInvocationResult

    if not isinstance(result, StrategyInvocationResult):
        raise TypeError("result must use StrategyInvocationResult")
    return {
        "protocol_version": WIRE_PROTOCOL_VERSION,
        "source_digest": result.source_digest,
        "context_fingerprint": result.context_fingerprint,
        "entrypoint": result.entrypoint,
        "status": result.status.value,
        "intents": [_encode_intent(intent) for intent in result.intents],
        "rejection_reasons": list(result.rejection_reasons),
        "error_digest": result.error_digest,
        "fingerprint": result.fingerprint,
    }


def serialize_invocation_result(result: Any) -> str:
    """Serialize a :class:`StrategyInvocationResult` without exception text."""

    payload = _invocation_result_payload(result)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deserialize_invocation_result(payload: str) -> Any:
    """Decode a typed invocation result and verify its content fingerprint."""

    from strategy_runtime.runner import InvocationStatus, StrategyInvocationResult

    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("result payload must not be empty")
    root = _load_json(payload, "result payload")
    item = _mapping(root, "result")
    required = {
        "protocol_version",
        "source_digest",
        "context_fingerprint",
        "entrypoint",
        "status",
        "intents",
        "rejection_reasons",
        "error_digest",
        "fingerprint",
    }
    if set(item) != required:
        raise ValueError("result fields are invalid")
    if item["protocol_version"] != WIRE_PROTOCOL_VERSION:
        raise ValueError("unsupported strategy runtime protocol version")
    intents: list[StrategyIntent] = []
    for raw in _list(item["intents"], "intents"):
        intent = _mapping(raw, "intent")
        kind = intent.get("type")
        if kind == "order":
            if set(intent) != {
                "type",
                "instrument_id",
                "side",
                "quantity",
                "order_type",
                "time_in_force",
                "limit_price",
                "stop_price",
                "client_tag",
            }:
                raise ValueError("order intent fields are invalid")
            intents.append(
                OrderIntent(
                    instrument_id=intent["instrument_id"],
                    side=OrderSide(intent["side"]),
                    quantity=_decode_value(intent["quantity"]),
                    order_type=OrderType(intent["order_type"]),
                    time_in_force=TimeInForce(intent["time_in_force"]),
                    limit_price=_decode_value(intent["limit_price"]),
                    stop_price=_decode_value(intent["stop_price"]),
                    client_tag=intent["client_tag"],
                )
            )
        elif kind == "target_position":
            if set(intent) != {"type", "instrument_id", "target_fraction"}:
                raise ValueError("target-position intent fields are invalid")
            intents.append(
                TargetPositionIntent(
                    instrument_id=intent["instrument_id"],
                    target_fraction=_decode_value(intent["target_fraction"]),
                )
            )
        else:
            raise ValueError("unsupported strategy intent type")
    result = StrategyInvocationResult(
        source_digest=item["source_digest"],
        context_fingerprint=item["context_fingerprint"],
        entrypoint=item["entrypoint"],
        status=InvocationStatus(item["status"]),
        intents=tuple(intents),
        rejection_reasons=tuple(_list(item["rejection_reasons"], "rejection_reasons")),
        error_digest=item["error_digest"],
    )
    if item["fingerprint"] != result.fingerprint:
        raise ValueError("result fingerprint does not match its payload")
    return result


def serialize_invocation_batch_result(results: Sequence[Any]) -> str:
    """Serialize bounded typed results from one stateful batch runtime."""

    if not isinstance(results, Sequence) or isinstance(results, str | bytes):
        raise TypeError("batch results must be a sequence")
    result_tuple = tuple(results)
    if not result_tuple:
        raise ValueError("batch results must not be empty")
    payload = {
        "protocol_version": BATCH_WIRE_PROTOCOL_VERSION,
        "results": [_invocation_result_payload(result) for result in result_tuple],
        "fingerprint": content_digest(result_tuple),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def deserialize_invocation_batch_result(payload: str) -> tuple[Any, ...]:
    """Decode batch results and verify every invocation and envelope identity."""

    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("batch result payload must not be empty")
    root = _load_json(payload, "batch result payload")
    item = _mapping(root, "batch result")
    if set(item) != {"protocol_version", "results", "fingerprint"}:
        raise ValueError("batch result fields are invalid")
    if item["protocol_version"] != BATCH_WIRE_PROTOCOL_VERSION:
        raise ValueError("unsupported strategy runtime batch protocol version")
    raw_results = _list(item["results"], "batch results")
    if not raw_results:
        raise ValueError("batch results must not be empty")
    results = tuple(
        deserialize_invocation_result(
            json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        for raw in raw_results
    )
    if item["fingerprint"] != content_digest(results):
        raise ValueError("batch result fingerprint does not match its payload")
    return results


__all__ = [
    "BATCH_WIRE_PROTOCOL_VERSION",
    "WIRE_PROTOCOL_VERSION",
    "deserialize_invocation_batch",
    "deserialize_invocation_batch_result",
    "deserialize_invocation",
    "deserialize_invocation_result",
    "serialize_invocation_batch",
    "serialize_invocation_batch_result",
    "serialize_invocation",
    "serialize_invocation_result",
]
