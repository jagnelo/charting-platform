from app.services.parameter_validation import validate_parameter_values


def test_parameter_validation_supports_defaults_style_schema_constraints():
    schema = {
        "properties": {
            "lookback": {"type": "integer", "minimum": 1, "maximum": 500},
            "mode": {"type": "string", "enum": ["close", "open"]},
        },
        "required": ["lookback"],
        "additionalProperties": False,
    }
    assert validate_parameter_values(schema, {"lookback": 20, "mode": "close"}) == []
    errors = validate_parameter_values(schema, {"lookback": 0, "mode": "high", "extra": True})
    assert {error["code"] for error in errors} == {
        "parameter_minimum",
        "parameter_enum",
        "parameter_unknown",
    }


def test_parameter_validation_rejects_non_object_values():
    errors = validate_parameter_values({"x": {"type": "number"}}, [1])
    assert errors[0]["code"] == "parameters_must_be_object"
