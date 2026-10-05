"""Typed, bounded JSON DTO codec for isolated Nautilus forward sessions."""

from __future__ import annotations

import dataclasses
import json
import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.forward_account import (
    ForwardAccountEvent,
    ForwardRuntimeExecutionReceipt,
    ShadowFill,
    ShadowOrder,
)
from app.strategy_lab_v2.forward_account_worker import ForwardAccountEventBinding
from app.strategy_lab_v2.forward_context import (
    ForwardPortfolioContextPreparation,
    ForwardStrategyContextPreparation,
)
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusEventRecord,
    NautilusForwardDeliveryBinding,
    NautilusForwardEventEnvelope,
    NautilusForwardEventTape,
)
from app.strategy_lab_v2.nautilus_forward_delivery import NautilusForwardDeliveryInput
from app.strategy_lab_v2.nautilus_forward_session import NautilusForwardExecutionResult
from app.strategy_lab_v2.nautilus_runtime_ipc import MAX_NAUTILUS_RUNTIME_IPC_FRAME_BYTES
from app.strategy_lab_v2.sdk import (
    IntentKind,
    MarketEvent,
    OrderIntent,
    OrderSide,
    OrderType,
    PositionSnapshot,
    StrategyContext,
    TimeInForce,
)

NAUTILUS_FORWARD_WIRE_SCHEMA = "strategy-lab.nautilus-forward-dto.v1"
_TAG = "$type"
_DATACLASSES = (
    CanonicalForwardEvent,
    ForwardAccountEvent,
    ForwardAccountEventBinding,
    ForwardPortfolioContextPreparation,
    ForwardRuntimeExecutionReceipt,
    ForwardStrategyContextPreparation,
    MarketEvent,
    NautilusEventRecord,
    NautilusForwardDeliveryBinding,
    NautilusForwardDeliveryInput,
    NautilusForwardEventEnvelope,
    NautilusForwardEventTape,
    NautilusForwardExecutionResult,
    OrderIntent,
    PositionSnapshot,
    ShadowFill,
    ShadowOrder,
    StrategyContext,
)
_ENUMS = (IntentKind, OrderSide, OrderType, TimeInForce)
_TYPES: dict[str, type[Any]] = {
    f"forward.{item.__name__}": item for item in (*_DATACLASSES, *_ENUMS)
}
_NAMES = {value: key for key, value in _TYPES.items()}


class NautilusForwardJsonWireCodec:
    """Encode/decode a closed set of public DTOs without dynamic imports or pickle."""

    def open_payload(self, *, instance_id: str) -> Mapping[str, object]:
        _nonempty(instance_id, "instance_id")
        return {"schema": NAUTILUS_FORWARD_WIRE_SCHEMA, "instance_id": instance_id}

    def decode_open_payload(self, payload: Mapping[str, object]) -> str:
        value = _strict_fields(payload, {"schema", "instance_id"}, "open payload")
        _check_schema(value)
        return _nonempty(value["instance_id"], "instance_id")

    def execute_payload(
        self,
        delivery: NautilusForwardDeliveryInput,
        preparation: ForwardStrategyContextPreparation | ForwardPortfolioContextPreparation,
    ) -> Mapping[str, object]:
        _validate_pair(delivery, preparation)
        payload = {
            "schema": NAUTILUS_FORWARD_WIRE_SCHEMA,
            "delivery": _encode(delivery),
            "preparation": _encode(preparation),
            "delivery_fingerprint": delivery.fingerprint,
            "preparation_fingerprint": preparation.fingerprint,
        }
        _check_payload_size(payload)
        return payload

    def decode_execute_payload(
        self, payload: Mapping[str, object]
    ) -> tuple[
        NautilusForwardDeliveryInput,
        ForwardStrategyContextPreparation | ForwardPortfolioContextPreparation,
    ]:
        value = _strict_fields(
            payload,
            {
                "schema",
                "delivery",
                "preparation",
                "delivery_fingerprint",
                "preparation_fingerprint",
            },
            "execute payload",
        )
        _check_schema(value)
        delivery = _decode(value["delivery"])
        preparation = _decode(value["preparation"])
        if not isinstance(delivery, NautilusForwardDeliveryInput):
            raise ValueError("forward wire delivery has the wrong DTO type")
        if not isinstance(
            preparation, ForwardStrategyContextPreparation | ForwardPortfolioContextPreparation
        ):
            raise ValueError("forward wire preparation has the wrong DTO type")
        if value["delivery_fingerprint"] != delivery.fingerprint:
            raise ValueError("forward wire delivery fingerprint differs from its content")
        if value["preparation_fingerprint"] != preparation.fingerprint:
            raise ValueError("forward wire preparation fingerprint differs from its content")
        _validate_pair(delivery, preparation)
        return delivery, preparation

    def execution_result_payload(
        self, result: NautilusForwardExecutionResult
    ) -> Mapping[str, object]:
        if not isinstance(result, NautilusForwardExecutionResult):
            raise TypeError("result must use NautilusForwardExecutionResult")
        payload = {
            "schema": NAUTILUS_FORWARD_WIRE_SCHEMA,
            "result": _encode(result),
            "result_fingerprint": result.fingerprint,
        }
        _check_payload_size(payload)
        return payload

    def execution_result(self, payload: Mapping[str, object]) -> NautilusForwardExecutionResult:
        value = _strict_fields(payload, {"schema", "result", "result_fingerprint"}, "result")
        _check_schema(value)
        result = _decode(value["result"])
        if not isinstance(result, NautilusForwardExecutionResult):
            raise ValueError("forward wire result has the wrong DTO type")
        if value["result_fingerprint"] != result.fingerprint:
            raise ValueError("forward execution result fingerprint differs from its content")
        return result

    def restore_payload(
        self, *, instance_id: str, checkpoint_fingerprint: str
    ) -> Mapping[str, object]:
        _nonempty(instance_id, "instance_id")
        require_sha256_digest(checkpoint_fingerprint, field_name="checkpoint_fingerprint")
        return {
            "schema": NAUTILUS_FORWARD_WIRE_SCHEMA,
            "instance_id": instance_id,
            "checkpoint_fingerprint": checkpoint_fingerprint,
        }

    def decode_restore_payload(self, payload: Mapping[str, object]) -> tuple[str, str]:
        value = _strict_fields(
            payload,
            {"schema", "instance_id", "checkpoint_fingerprint"},
            "restore payload",
        )
        _check_schema(value)
        instance_id = _nonempty(value["instance_id"], "instance_id")
        checkpoint = _nonempty(value["checkpoint_fingerprint"], "checkpoint_fingerprint")
        require_sha256_digest(checkpoint, field_name="checkpoint_fingerprint")
        return instance_id, checkpoint


def _validate_pair(
    delivery: NautilusForwardDeliveryInput,
    preparation: ForwardStrategyContextPreparation | ForwardPortfolioContextPreparation,
) -> None:
    if not isinstance(delivery, NautilusForwardDeliveryInput):
        raise TypeError("delivery must use NautilusForwardDeliveryInput")
    if not isinstance(
        preparation, ForwardStrategyContextPreparation | ForwardPortfolioContextPreparation
    ):
        raise TypeError("preparation must use a typed forward context preparation")
    binding = delivery.delivery_binding
    if preparation.instance_id != binding.instance_id:
        raise ValueError("forward delivery and preparation belong to different instances")
    if preparation.delivery_binding_fingerprint != binding.fingerprint:
        raise ValueError("forward preparation is not bound to this delivery")
    if preparation.payload_fingerprint != delivery.verified_market_payload.fingerprint:
        raise ValueError("forward preparation is not bound to this verified market payload")


def _encode(value: Any) -> object:
    if isinstance(value, Enum):
        name = _NAMES.get(type(value))
        if name is None:
            raise TypeError(f"unsupported forward wire enum: {type(value).__name__}")
        return {_TAG: "enum", "name": name, "value": value.value}
    if value is None or isinstance(value, bool | str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("forward wire values cannot contain non-finite floats")
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("forward wire values cannot contain non-finite decimals")
        return {_TAG: "decimal", "value": str(value)}
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("forward wire datetimes must be timezone-aware")
        return {_TAG: "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {_TAG: "date", "value": value.isoformat()}
    if isinstance(value, timedelta):
        return {
            _TAG: "timedelta",
            "days": value.days,
            "seconds": value.seconds,
            "microseconds": value.microseconds,
        }
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        name = _NAMES.get(type(value))
        if name is None:
            raise TypeError(f"unsupported forward wire DTO: {type(value).__name__}")
        return {
            _TAG: "dataclass",
            "name": name,
            "fields": {
                field.name: _encode(getattr(value, field.name))
                for field in dataclasses.fields(value)
                if field.init
            },
        }
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("forward wire mapping keys must be strings")
        return {
            _TAG: "mapping",
            "entries": [[key, _encode(value[key])] for key in sorted(value)],
        }
    if isinstance(value, tuple | list):
        return {
            _TAG: "tuple" if isinstance(value, tuple) else "list",
            "items": [_encode(item) for item in value],
        }
    raise TypeError(f"unsupported forward wire value: {type(value).__name__}")


def _decode(value: object) -> Any:
    if value is None or isinstance(value, bool | str | int | float):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("forward wire values cannot contain non-finite floats")
        return value
    if not isinstance(value, Mapping) or not isinstance(value.get(_TAG), str):
        raise ValueError("forward wire tagged value is invalid")
    tag = value[_TAG]
    if tag == "decimal":
        item = _strict_fields(value, {_TAG, "value"}, "decimal")
        raw = _nonempty(item["value"], "decimal")
        try:
            parsed_decimal = Decimal(raw)
        except InvalidOperation as error:
            raise ValueError("forward wire decimal is invalid") from error
        if not parsed_decimal.is_finite() or str(parsed_decimal) != raw:
            raise ValueError("forward wire decimal is not finite and canonical")
        return parsed_decimal
    if tag == "datetime":
        item = _strict_fields(value, {_TAG, "value"}, "datetime")
        raw = _nonempty(item["value"], "datetime")
        parsed_datetime = datetime.fromisoformat(raw)
        if parsed_datetime.tzinfo is None or parsed_datetime.utcoffset() is None:
            raise ValueError("forward wire datetime must be timezone-aware")
        return parsed_datetime
    if tag == "date":
        item = _strict_fields(value, {_TAG, "value"}, "date")
        return date.fromisoformat(_nonempty(item["value"], "date"))
    if tag == "timedelta":
        item = _strict_fields(value, {_TAG, "days", "seconds", "microseconds"}, "timedelta")
        return timedelta(
            days=_integer(item["days"], "timedelta days"),
            seconds=_integer(item["seconds"], "timedelta seconds"),
            microseconds=_integer(item["microseconds"], "timedelta microseconds"),
        )
    if tag == "enum":
        item = _strict_fields(value, {_TAG, "name", "value"}, "enum")
        enum_type = _TYPES.get(_nonempty(item["name"], "enum name"))
        if enum_type not in _ENUMS:
            raise ValueError("forward wire enum type is not allowlisted")
        try:
            return enum_type(item["value"])
        except (TypeError, ValueError) as error:
            raise ValueError("forward wire enum value is unsupported") from error
    if tag == "dataclass":
        item = _strict_fields(value, {_TAG, "name", "fields"}, "dataclass")
        dto_type = _TYPES.get(_nonempty(item["name"], "DTO name"))
        if dto_type not in _DATACLASSES:
            raise ValueError("forward wire DTO type is not allowlisted")
        raw_fields = item["fields"]
        if not isinstance(raw_fields, Mapping):
            raise ValueError("forward wire DTO fields must be an object")
        expected_fields = {field.name for field in dataclasses.fields(dto_type) if field.init}
        if set(raw_fields) != expected_fields:
            raise ValueError("forward wire DTO fields differ from its versioned schema")
        decoded_fields = {name: _decode(raw_fields[name]) for name in expected_fields}
        try:
            return dto_type(**decoded_fields)
        except (TypeError, ValueError) as error:
            raise ValueError("forward wire DTO failed typed validation") from error
    if tag == "mapping":
        item = _strict_fields(value, {_TAG, "entries"}, "mapping")
        entries = _sequence(item["entries"], "mapping entries")
        result: dict[str, Any] = {}
        previous: str | None = None
        for pair in entries:
            values = _sequence(pair, "mapping entry")
            if len(values) != 2:
                raise ValueError("forward wire mapping entry must have two values")
            key = _nonempty(values[0], "mapping key")
            if previous is not None and key <= previous:
                raise ValueError("forward wire mapping keys must be uniquely sorted")
            previous = key
            result[key] = _decode(values[1])
        return result
    if tag in {"tuple", "list"}:
        item = _strict_fields(value, {_TAG, "items"}, "sequence")
        decoded = [_decode(part) for part in _sequence(item["items"], "sequence items")]
        if tag == "tuple":
            return tuple(decoded)
        return decoded
    raise ValueError("forward wire type tag is unsupported")


def _strict_fields(value: object, names: set[str], description: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != names:
        raise ValueError(f"forward wire {description} fields are invalid")
    return value


def _check_schema(value: Mapping[str, Any]) -> None:
    if value["schema"] != NAUTILUS_FORWARD_WIRE_SCHEMA:
        raise ValueError("forward wire schema is unsupported")


def _check_payload_size(payload: Mapping[str, object]) -> None:
    encoded = json.dumps(
        payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    # Leave room for the IPC envelope, correlation id and frame fingerprint.
    if len(encoded) > MAX_NAUTILUS_RUNTIME_IPC_FRAME_BYTES - 512:
        raise ValueError("forward DTO payload exceeds the bounded runtime IPC frame limit")


def _sequence(value: object, name: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ValueError(f"forward wire {name} must be an array")
    return value


def _nonempty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"forward wire {name} must be a non-empty string")
    return value


def _integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"forward wire {name} must be an integer")
    return value


__all__ = ["NAUTILUS_FORWARD_WIRE_SCHEMA", "NautilusForwardJsonWireCodec"]
