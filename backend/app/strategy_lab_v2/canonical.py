"""Canonical JSON and immutable JSON helpers used for reproducible identities."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Any


def _canonical_value(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return [
            "dataclass",
            f"{type(value).__module__}.{type(value).__qualname__}",
            [
                [item.name, _canonical_value(getattr(value, item.name))]
                for item in dataclasses.fields(value)
                if not item.name.startswith("_")
            ],
        ]
    if isinstance(value, Enum):
        return [
            "enum",
            f"{type(value).__module__}.{type(value).__qualname__}",
            _canonical_value(value.value),
        ]
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite decimals are not canonical JSON values")
        if value.is_zero():
            decimal_identity = "0:0:0"
        else:
            sign, digits, exponent = value.as_tuple()
            if not isinstance(exponent, int):
                raise ValueError("finite decimals must have an integral exponent")
            normalized_digits = list(digits)
            while normalized_digits[-1] == 0:
                normalized_digits.pop()
                exponent += 1
            decimal_identity = f"{sign}:{''.join(map(str, normalized_digits))}:{exponent}"
        return ["decimal", decimal_identity]
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetimes in canonical data must be timezone-aware")
        return [
            "datetime",
            value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        ]
    if isinstance(value, date):
        return ["date", value.isoformat()]
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        return ["mapping", [[key, _canonical_value(value[key])] for key in sorted(value)]]
    if isinstance(value, set | frozenset):
        normalized = [_canonical_value(item) for item in value]
        normalized.sort(
            key=lambda item: json.dumps(
                item, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
            )
        )
        return ["set", normalized]
    if isinstance(value, tuple | list):
        sequence_type = "tuple" if isinstance(value, tuple) else "list"
        return [sequence_type, [_canonical_value(item) for item in value]]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not canonical JSON values")
        return ["float", value.hex()]
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["bool", value]
    if isinstance(value, int):
        return ["int", str(value)]
    if isinstance(value, str):
        return ["str", value]
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Serialize values with explicit type tags to avoid cross-type hash collisions."""

    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def content_digest(value: Any) -> str:
    """Return the versioned SHA-256 content address for a canonical value."""

    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def freeze_json(value: Any) -> Any:
    """Validate JSON-shaped input and recursively freeze mappings and sequences."""

    _canonical_value(value)
    return _freeze_value(value)


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return MappingProxyType(
            {
                item.name: _freeze_value(getattr(value, item.name))
                for item in dataclasses.fields(value)
                if not item.name.startswith("_")
            }
        )
    if isinstance(value, tuple | list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, set | frozenset):
        frozen = tuple(_freeze_value(item) for item in value)
        return tuple(sorted(frozen, key=canonical_json))
    if isinstance(value, Enum):
        return _freeze_value(value.value)
    return value


def require_sha256_digest(value: str, *, field_name: str = "digest") -> None:
    prefix = "sha256:"
    if not isinstance(value, str) or len(value) != len(prefix) + 64 or not value.startswith(prefix):
        raise ValueError(f"{field_name} must be a sha256 content digest")
    try:
        int(value[len(prefix) :], 16)
    except ValueError as error:
        raise ValueError(f"{field_name} must contain a hexadecimal SHA-256 digest") from error
