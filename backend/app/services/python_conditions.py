"""Compile the visual condition tree into the unified workstation Python AST.

The visual editor is intentionally a source generator, not a second execution
engine.  The generated source uses only the public ``market``, ``ta``, ``np``
and ``output`` SDK namespaces and is therefore validated and executed by the
same code path as hand-authored Python conditions.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from app.services.code_validation import validate_workstation_python


class VisualConditionCompileError(ValueError):
    def __init__(self, code: str, message: str, *, path: str = "condition") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


@dataclass
class _Builder:
    lines: list[str]
    counter: int = 0

    def name(self, prefix: str = "condition") -> str:
        value = f"_{prefix}_{self.counter}"
        self.counter += 1
        return value


_INDICATOR_TYPES = {
    # Keep this list in sync with the public indicator registry.  The compiler
    # rejects unknown values rather than emitting an executable but ambiguous
    # source string.
    "sma",
    "ema",
    "wma",
    "rsi",
    "macd",
    "bb",
    "vwap",
    "avwap",
    "atr",
    "stoch",
    "obv",
    "cci",
    "volume",
    "volume_ratio",
    "ichimoku",
    "psar",
    "donchian",
    "keltner",
    "williams_r",
    "hma",
    "aroon",
    "mfi",
    "roc",
    "momentum",
    "stddev",
    "pivot_points",
    "cmf",
    "dema",
    "tema",
    "trix",
    "ppo",
    "adx",
}
_PRICE_FIELDS = {"open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"}
_COMPARISON_OPS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "=="}
_CROSS_OPS = {"crosses_above": "above", "crosses_below": "below", "gt": "gt", "lt": "lt"}
_PERIODS = {"1D", "1W", "1M", "3M", "6M", "MTD", "QTD", "YTD", "1Y"}


def _literal(value: Any, *, path: str) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise VisualConditionCompileError(
                "invalid_value", "Condition values must be finite.", path=path
            )
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, dict):
        return (
            "{"
            + ", ".join(
                f"{_literal(str(k), path=path)}: {_literal(v, path=path)}" for k, v in value.items()
            )
            + "}"
        )
    raise VisualConditionCompileError(
        "invalid_value", "Condition value must be a scalar or parameter object.", path=path
    )


def _number(value: Any, *, path: str) -> float | int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not math.isfinite(float(value))
    ):
        raise VisualConditionCompileError(
            "invalid_value", "Condition threshold must be finite numeric data.", path=path
        )
    return value


def _params(raw: Any, *, path: str) -> dict[str, Any]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise VisualConditionCompileError(
            "invalid_parameters", "Indicator parameters must be an object.", path=path
        )
    normalized: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key or key.startswith("_"):
            raise VisualConditionCompileError(
                "invalid_parameters", "Indicator parameter names are invalid.", path=path
            )
        if not isinstance(value, str | int | float | bool):
            raise VisualConditionCompileError(
                "invalid_parameters", "Indicator parameters must be scalar values.", path=path
            )
        if isinstance(value, float) and not math.isfinite(value):
            raise VisualConditionCompileError(
                "invalid_parameters", "Indicator parameters must be finite.", path=path
            )
        normalized[key] = value
    return normalized


def _indicator(ref: dict[str, Any], builder: _Builder, *, path: str) -> str:
    indicator_type = str(ref.get("type") or "").lower()
    if indicator_type not in _INDICATOR_TYPES:
        raise VisualConditionCompileError(
            "unsupported_indicator",
            f"Indicator {indicator_type!r} is not supported by the unified SDK.",
            path=path,
        )
    params = _params(ref.get("params"), path=f"{path}.params")
    output = ref.get("output")
    if output is not None and not isinstance(output, str):
        raise VisualConditionCompileError(
            "invalid_output", "Indicator output must be a string.", path=f"{path}.output"
        )
    target = builder.name("indicator")
    builder.lines.append(
        f"{target} = ta.indicator({_literal(indicator_type, path=path)}, {_literal(params, path=path)}, {_literal(output, path=path) if output else 'None'})"
    )
    return target


def _finite_latest(series: str) -> str:
    return f"(len({series}) > 0 and np.isfinite({series}[-1]))"


def _finite_pair(left: str, right: str) -> str:
    return f"(len({left}) > 1 and len({right}) > 1 and np.isfinite({left}[-1]) and np.isfinite({right}[-1]) and np.isfinite({left}[-2]) and np.isfinite({right}[-2]))"


def _field(field: Any, *, path: str) -> str:
    token = str(field or "close").lower()
    if token not in _PRICE_FIELDS:
        raise VisualConditionCompileError(
            "unsupported_field", f"Price field {token!r} is not supported.", path=path
        )
    return f"market.{_PRICE_FIELDS[token]}()"


def _comparison(left: str, op: Any, right: str, *, path: str) -> str:
    operator = str(op or "gt")
    symbol = _COMPARISON_OPS.get(operator)
    if symbol is None:
        raise VisualConditionCompileError(
            "unsupported_operator", f"Comparison operator {operator!r} is not supported.", path=path
        )
    return f"({left} {symbol} {right})"


def _compile_node(node: Any, builder: _Builder, *, path: str) -> str:
    if not isinstance(node, dict):
        raise VisualConditionCompileError(
            "invalid_node", "Every condition node must be an object.", path=path
        )
    if "operator" in node and "conditions" in node:
        operator = str(node.get("operator") or "AND").upper()
        children = node.get("conditions")
        if not isinstance(children, list) or not children:
            raise VisualConditionCompileError(
                "invalid_group", "Condition groups require at least one child.", path=path
            )
        if operator == "NOT" and len(children) != 1:
            raise VisualConditionCompileError(
                "invalid_group", "NOT groups require exactly one child.", path=path
            )
        expressions = [
            _compile_node(child, builder, path=f"{path}.conditions[{index}]")
            for index, child in enumerate(children)
        ]
        joiner = " and " if operator == "AND" else " or " if operator == "OR" else None
        if joiner:
            return "(" + joiner.join(expressions) + ")"
        if operator == "NOT":
            return f"(not {expressions[0]})"
        raise VisualConditionCompileError(
            "unsupported_group_operator",
            f"Group operator {operator!r} is not supported.",
            path=path,
        )

    ctype = str(node.get("type") or "")
    op = str(node.get("op") or "gt")
    if ctype == "price_threshold":
        value = _literal(_number(node.get("value"), path=f"{path}.value"), path=f"{path}.value")
        price = _field(node.get("field"), path=f"{path}.field")
        return f"({_finite_latest(price)} and {_comparison(price + '[-1]', op, value, path=path + '.op')})"
    if ctype == "indicator_threshold":
        series = _indicator(
            {
                "type": node.get("indicator"),
                "params": node.get("params"),
                "output": node.get("output"),
            },
            builder,
            path=path,
        )
        value = _literal(_number(node.get("value"), path=f"{path}.value"), path=f"{path}.value")
        return f"({_finite_latest(series)} and {_comparison(series + '[-1]', op, value, path=path + '.op')})"
    if ctype == "price_indicator":
        price = _field(node.get("field"), path=f"{path}.field")
        series = _indicator(
            {
                "type": node.get("indicator"),
                "params": node.get("params"),
                "output": node.get("output"),
            },
            builder,
            path=path,
        )
        valid = f"(len({price}) > 0 and {_finite_latest(series)})"
        if op in _CROSS_OPS and op.startswith("crosses_"):
            direction = _CROSS_OPS[op]
            relation = "<=" if direction == "above" else ">="
            current = ">" if direction == "above" else "<"
            return f"({valid} and len({price}) > 1 and len({series}) > 1 and np.isfinite({price}[-2]) and np.isfinite({series}[-2]) and {price}[-2] {relation} {series}[-2] and {price}[-1] {current} {series}[-1])"
        return (
            f"({valid} and {_comparison(price + '[-1]', op, series + '[-1]', path=path + '.op')})"
        )
    if ctype == "indicator_cross":
        left = _indicator(node.get("indicator_a") or {}, builder, path=f"{path}.indicator_a")
        right = _indicator(node.get("indicator_b") or {}, builder, path=f"{path}.indicator_b")
        direction = _CROSS_OPS.get(op)
        if direction in {"above", "below"}:
            relation = "<=" if direction == "above" else ">="
            current = ">" if direction == "above" else "<"
            return f"({_finite_pair(left, right)} and {left}[-2] {relation} {right}[-2] and {left}[-1] {current} {right}[-1])"
        return f"({_finite_pair(left, right)} and {_comparison(left + '[-1]', op, right + '[-1]', path=path + '.op')})"
    if ctype in {"price_change", "price_change_period", "performance"}:
        if ctype == "price_change":
            lookback = int(_number(node.get("lookback_bars"), path=f"{path}.lookback_bars"))
            if lookback < 1:
                raise VisualConditionCompileError(
                    "invalid_lookback", "Lookback bars must be positive.", path=path
                )
            change = f"market.percent_change({lookback})"
        else:
            period = str(node.get("period") or "1D")
            if period not in _PERIODS:
                raise VisualConditionCompileError(
                    "unsupported_period",
                    f"Period {period!r} is not supported.",
                    path=f"{path}.period",
                )
            change = f"market.percent_change({_literal(period, path=path)})"
        value = _literal(_number(node.get("value"), path=f"{path}.value"), path=f"{path}.value")
        return f"({change} is not None and {_comparison(change, op, value, path=path + '.op')})"
    if ctype in {"week52_new_high", "week52_new_low"}:
        method = "week52_new_high" if ctype.endswith("high") else "week52_new_low"
        return f"market.{method}()"
    if ctype in {"pct_from_52w_high", "pct_from_52w_low"}:
        method = "pct_from_52w_high" if ctype.endswith("high") else "pct_from_52w_low"
        value = _literal(_number(node.get("value"), path=f"{path}.value"), path=f"{path}.value")
        change = f"market.{method}()"
        return f"({change} is not None and {_comparison(change, op, value, path=path + '.op')})"
    if ctype in {"stats_filter", "fundamental_filter"}:
        field = str(node.get("field") or "")
        if not field or field.startswith("_"):
            raise VisualConditionCompileError(
                "invalid_field", "Metadata field is required.", path=f"{path}.field"
            )
        value = _literal(node.get("value"), path=f"{path}.value")
        actual = f"market.metadata().get({_literal(field, path=path)})"
        if ctype == "fundamental_filter" and op in {"eq", "contains"}:
            rhs = f"str({actual}).lower()"
            expected = f"str({value}).lower()"
            expression = f"({rhs} == {expected})" if op == "eq" else f"({expected} in {rhs})"
            return f"({actual} is not None and {expression})"
        numeric = f"float({actual})"
        return f"({actual} is not None and {_comparison(numeric, op, value, path=path + '.op')})"
    raise VisualConditionCompileError(
        "unsupported_condition",
        f"Condition type {ctype!r} is not supported by the unified Python editor.",
        path=path,
    )


def compile_visual_condition(condition: dict[str, Any]) -> str:
    """Return deterministic Boolean Python source for a visual condition tree."""
    builder = _Builder(lines=[])
    expression = _compile_node(condition, builder, path="condition")
    builder.lines.append(f"output.boolean('match', bool({expression}))")
    source = "\n".join(builder.lines)
    validation = validate_workstation_python(source)
    if not validation.valid:
        first = validation.diagnostics[0]
        raise VisualConditionCompileError(
            "generated_source_invalid", first.message, path=f"line:{first.line}"
        )
    return source
