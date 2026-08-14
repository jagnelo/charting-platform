import pytest

from app.services.code_validation import validate_workstation_python
from app.services.python_conditions import VisualConditionCompileError, compile_visual_condition


def test_visual_price_and_indicator_conditions_compile_to_one_boolean_python_source():
    source = compile_visual_condition(
        {
            "operator": "AND",
            "conditions": [
                {"type": "price_threshold", "field": "close", "op": "gt", "value": 100},
                {
                    "type": "indicator_threshold",
                    "indicator": "rsi",
                    "params": {"period": 14},
                    "output": "rsi",
                    "op": "lt",
                    "value": 70,
                },
            ],
        }
    )
    result = validate_workstation_python(source)
    assert result.valid
    assert result.output_contracts == ("boolean",)
    assert 'ta.indicator("rsi"' in source
    assert "output.boolean('match'" in source


def test_visual_cross_and_nested_logical_conditions_are_compiled_without_legacy_calls():
    source = compile_visual_condition(
        {
            "operator": "OR",
            "conditions": [
                {
                    "operator": "NOT",
                    "conditions": [
                        {"type": "price_change", "lookback_bars": 5, "op": "lt", "value": 0}
                    ],
                },
                {
                    "type": "indicator_cross",
                    "indicator_a": {"type": "sma", "params": {"period": 20}, "output": "sma"},
                    "indicator_b": {"type": "ema", "params": {"period": 50}, "output": "ema"},
                    "op": "crosses_above",
                },
            ],
        }
    )
    assert "ta.indicator" in source
    assert "market.percent_change(5)" in source
    assert "_evaluate_condition" not in source
    assert validate_workstation_python(source).valid


@pytest.mark.parametrize(
    ("condition", "code"),
    [
        ({"operator": "NOT", "conditions": []}, "invalid_group"),
        (
            {"operator": "AND", "conditions": [{"type": "not_a_real_condition"}]},
            "unsupported_condition",
        ),
        (
            {"operator": "AND", "conditions": [{"type": "price_threshold", "value": float("nan")}]},
            "invalid_value",
        ),
    ],
)
def test_visual_condition_compiler_rejects_ambiguous_or_unsafe_nodes(condition, code):
    with pytest.raises(VisualConditionCompileError) as error:
        compile_visual_condition(condition)
    assert error.value.code == code


def test_visual_metadata_conditions_use_prepared_market_metadata():
    source = compile_visual_condition(
        {
            "operator": "AND",
            "conditions": [
                {
                    "type": "fundamental_filter",
                    "field": "sector",
                    "op": "eq",
                    "value": "Technology",
                },
                {"type": "stats_filter", "field": "market_cap", "op": "gt", "value": 1_000_000},
            ],
        }
    )
    assert "market.metadata().get" in source
    assert validate_workstation_python(source).valid


def test_generated_performance_condition_exposes_lookback_to_preflight():
    source = compile_visual_condition(
        {"type": "price_change", "lookback_bars": 63, "op": "gte", "value": 1}
    )
    validation = validate_workstation_python(source)
    assert validation.valid
    assert validation.lookback_hint == 63
