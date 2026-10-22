"""Pinned Decimal context for deterministic platform-level arithmetic."""

from __future__ import annotations

from collections.abc import Callable
from decimal import ROUND_HALF_EVEN, Context, localcontext
from functools import wraps
from typing import ParamSpec, TypeVar

DECIMAL_PRECISION = 34
_DECIMAL_CONTEXT = Context(prec=DECIMAL_PRECISION, rounding=ROUND_HALF_EVEN)

_Parameters = ParamSpec("_Parameters")
_Result = TypeVar("_Result")


def deterministic_decimal_math(
    function: Callable[_Parameters, _Result],
) -> Callable[_Parameters, _Result]:
    """Run a calculation in a fixed local Decimal context without mutating callers."""

    @wraps(function)
    def wrapped(*args: _Parameters.args, **kwargs: _Parameters.kwargs) -> _Result:
        with localcontext(_DECIMAL_CONTEXT):
            return function(*args, **kwargs)

    return wrapped
