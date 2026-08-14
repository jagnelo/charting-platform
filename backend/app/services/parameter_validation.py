"""Small JSON-parameter contract shared by unified-Python run APIs."""

from __future__ import annotations

import math
from typing import Any


def normalise_parameter_schema(schema: object) -> dict[str, dict[str, Any]]:
    if not isinstance(schema, dict):
        return {}
    properties = schema.get("properties", schema)
    if not isinstance(properties, dict):
        return {}
    return {
        str(name): spec
        for name, spec in properties.items()
        if isinstance(name, str) and isinstance(spec, dict)
    }


def validate_parameter_values(schema: object, values: object) -> list[dict[str, object]]:
    if not isinstance(values, dict):
        return [
            {
                "code": "parameters_must_be_object",
                "message": "parameters must be a JSON object",
                "parameter": None,
            }
        ]
    properties = normalise_parameter_schema(schema)
    required = schema.get("required", []) if isinstance(schema, dict) else []
    required_names = (
        {item for item in required if isinstance(item, str)}
        if isinstance(required, list)
        else set()
    )
    errors: list[dict[str, object]] = []
    additional_allowed = (
        not isinstance(schema, dict) or schema.get("additionalProperties", True) is not False
    )
    for name in sorted(required_names - values.keys()):
        errors.append(
            {
                "code": "parameter_required",
                "message": f"parameter {name!r} is required",
                "parameter": name,
            }
        )
    if not additional_allowed:
        for name in sorted(set(values) - set(properties)):
            errors.append(
                {
                    "code": "parameter_unknown",
                    "message": f"parameter {name!r} is not declared",
                    "parameter": name,
                }
            )
    for name, value in values.items():
        spec = properties.get(name)
        if spec is None:
            continue
        expected = spec.get("type")
        if expected and not _matches_type(value, expected):
            errors.append(
                {
                    "code": "parameter_type",
                    "message": f"parameter {name!r} must be {expected}",
                    "parameter": name,
                }
            )
            continue
        if "enum" in spec and isinstance(spec["enum"], list) and value not in spec["enum"]:
            errors.append(
                {
                    "code": "parameter_enum",
                    "message": f"parameter {name!r} is outside its enum",
                    "parameter": name,
                }
            )
            continue
        if (
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        ):
            if isinstance(spec.get("minimum"), int | float) and value < spec["minimum"]:
                errors.append(
                    {
                        "code": "parameter_minimum",
                        "message": f"parameter {name!r} is below its minimum",
                        "parameter": name,
                    }
                )
            if isinstance(spec.get("maximum"), int | float) and value > spec["maximum"]:
                errors.append(
                    {
                        "code": "parameter_maximum",
                        "message": f"parameter {name!r} is above its maximum",
                        "parameter": name,
                    }
                )
    return errors


def _matches_type(value: object, expected: object) -> bool:
    if expected == "number":
        return (
            isinstance(value, int | float)
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return True
