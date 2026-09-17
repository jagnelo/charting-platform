from __future__ import annotations

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.strategy_validation import validate_strategy_source


def test_strategy_source_validation_accepts_safe_deterministic_source() -> None:
    source = """
from decimal import Decimal
from math import sqrt

def signal(value):
    return Decimal(value) * Decimal(str(sqrt(4)))
"""
    result = validate_strategy_source(source)
    assert result.accepted
    assert result.violations == ()
    assert result.source_digest == content_digest(source)


def test_strategy_source_validation_rejects_filesystem_network_and_dynamic_code() -> None:
    result = validate_strategy_source(
        """
import os
import socket
from pathlib import Path

def run(source):
    return eval(source), open(Path('/tmp/output'), 'w')
"""
    )
    assert not result.accepted
    assert any("forbidden_import" in item and "os" in item for item in result.violations)
    assert any("forbidden_import" in item and "socket" in item for item in result.violations)
    assert any("forbidden_call" in item and "eval" in item for item in result.violations)
    assert any("forbidden_call" in item and "open" in item for item in result.violations)


def test_strategy_source_validation_cannot_allow_forbidden_import_roots() -> None:
    result = validate_strategy_source(
        "import os\nimport math\n",
        allowed_import_roots=frozenset({"math", "os"}),
    )
    assert not result.accepted
    assert any("forbidden_import" in item and "os" in item for item in result.violations)
    assert not any("forbidden_import" in item and "math" in item for item in result.violations)


def test_strategy_source_validation_rejects_relative_and_introspection_escapes() -> None:
    result = validate_strategy_source(
        """
from .private import value

def run(obj):
    return obj.__class__.__globals__, getattr(obj, "__dict__"), globals()
"""
    )
    assert not result.accepted
    assert any("forbidden_import" in item for item in result.violations)
    assert any("forbidden_attribute" in item and "__class__" in item for item in result.violations)
    assert any("forbidden_attribute" in item and "__globals__" in item for item in result.violations)
    assert any("forbidden_name" in item and "getattr" in item for item in result.violations)
    assert any("forbidden_name" in item and "globals" in item for item in result.violations)


def test_strategy_source_validation_rejects_aliases_of_dynamic_builtins() -> None:
    result = validate_strategy_source(
        """
danger = eval

def run(source):
    return danger(source)
"""
    )
    assert not result.accepted
    assert any("forbidden_name" in item and "eval" in item for item in result.violations)


def test_strategy_source_validation_rejects_wall_clock_calls_even_with_aliases() -> None:
    result = validate_strategy_source(
        """
from datetime import date, datetime

def run():
    return datetime.now(), date.today(), clock.utcnow()
"""
    )
    assert not result.accepted
    assert sum(item.endswith(": now") for item in result.violations) == 1
    assert sum(item.endswith(": today") for item in result.violations) == 1
    assert sum(item.endswith(": utcnow") for item in result.violations) == 1


def test_strategy_source_validation_rejects_wall_clock_method_aliases() -> None:
    result = validate_strategy_source(
        """
from datetime import datetime

clock = datetime.now

def run():
    return clock()
"""
    )
    assert not result.accepted
    assert sum(item.endswith(": now") for item in result.violations) == 1


def test_strategy_source_validation_rejects_allowed_module_introspection() -> None:
    result = validate_strategy_source(
        """
import typing

system_module = typing.sys
"""
    )
    assert not result.accepted
    assert any(
        item.endswith(": sys") and "forbidden_attribute" in item
        for item in result.violations
    )


def test_strategy_source_validation_rejects_private_import_names() -> None:
    result = validate_strategy_source("from collections import _sys\n")
    assert not result.accepted
    assert any("forbidden_import" in item and "_sys" in item for item in result.violations)

    public_escape = validate_strategy_source("from typing import sys as safe\n")
    assert not public_escape.accepted
    assert any("forbidden_import" in item and "sys" in item for item in public_escape.violations)


def test_strategy_source_validation_is_deterministic_for_syntax_errors() -> None:
    source = "def broken(:\n    pass\n"
    first = validate_strategy_source(source)
    second = validate_strategy_source(source)
    assert first == second
    assert not first.accepted
    assert first.violations[0].startswith("syntax_error@1:")
