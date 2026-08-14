"""Static validation for the single workstation Python language.

This is deliberately a *gate*, not a sandbox.  Passing validation only allows a
submission to be prepared for the isolated execution service; it must never make
execution in FastAPI or a general worker permissible.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

_APPROVED_ROOTS = {
    "market",
    "ta",
    "stats",
    "research",
    "output",
    "parameters",
    "np",
    "pd",
    "scipy",
    "statsmodels",
}
_SAFE_BUILTINS = {
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "filter",
    "float",
    "int",
    "len",
    "list",
    "map",
    "max",
    "min",
    "range",
    "round",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
    "zip",
}
_BANNED_NODES = (
    ast.Import,
    ast.ImportFrom,
    ast.Global,
    ast.Nonlocal,
    ast.Lambda,
    ast.ClassDef,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.Raise,
)
_BANNED_CALLS = {
    "eval",
    "exec",
    "compile",
    "open",
    "input",
    "__import__",
    "globals",
    "locals",
    "vars",
    "getattr",
    "setattr",
    "delattr",
    "help",
    "breakpoint",
}
_BANNED_DATA_CALLS = {
    "read_csv",
    "read_excel",
    "read_json",
    "read_parquet",
    "read_pickle",
    "read_sql",
    "read_sql_query",
    "to_csv",
    "to_excel",
    "to_json",
    "to_parquet",
    "to_pickle",
    "to_sql",
    "load",
    "save",
    "savetxt",
    "fromfile",
}
# Keep this list in lock-step with research_runner.validation.  These ndarray /
# wrapper attributes can write files, expose raw memory/ctypes, or mutate
# process-owned buffers.  Reject them before a source version is persisted so
# the API validator cannot claim code is valid only for the isolated runner to
# reject it later.
_BANNED_ATTRIBUTES = {
    "tofile",
    "dump",
    "dumps",
    "savetxt",
    "fromfile",
    "load",
    "save",
    "ctypes",
    "data",
    "base",
    "setflags",
    "resize",
    "fill",
    "put",
    "itemset",
}


@dataclass(frozen=True)
class CodeDiagnostic:
    code: str
    message: str
    line: int
    column: int


@dataclass(frozen=True)
class ValidationResult:
    diagnostics: tuple[CodeDiagnostic, ...]
    dependencies: tuple[str, ...]
    lookback_hint: int | None
    output_contracts: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.diagnostics


class _Validator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.diagnostics: list[CodeDiagnostic] = []
        self.dependencies: set[str] = set()
        self.lookback_hint: int | None = None
        self.output_contracts: set[str] = set()
        self.bound_names: set[str] = set()

    def add(self, node: ast.AST, code: str, message: str) -> None:
        self.diagnostics.append(
            CodeDiagnostic(
                code=code,
                message=message,
                line=getattr(node, "lineno", 1),
                column=getattr(node, "col_offset", 0),
            )
        )

    def record_lookback(self, value: object) -> None:
        """Record a statically-known positive bar window for preflight metadata."""
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            return
        self.lookback_hint = max(self.lookback_hint or 0, value)

    def visit(self, node: ast.AST) -> None:
        if isinstance(node, _BANNED_NODES):
            self.add(
                node,
                "forbidden_syntax",
                f"{type(node).__name__} is not available in workstation code.",
            )
            return
        super().visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            self.add(
                node, "forbidden_attribute", "Private and dunder attributes are not available."
            )
        elif node.attr in _BANNED_ATTRIBUTES:
            self.add(
                node,
                "forbidden_attribute",
                f"{node.attr} is not available in the isolated numerical facade.",
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("__"):
            self.add(node, "forbidden_name", "Dunder names are not available.")
        if isinstance(node.ctx, ast.Store):
            self.bound_names.add(node.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        banned_builtin = isinstance(node.func, ast.Name) and node.func.id in _BANNED_CALLS
        if banned_builtin:
            self.add(node, "forbidden_call", f"{node.func.id}() is not available.")
        root = _attribute_root(node.func)
        if (
            isinstance(node.func, ast.Attribute)
            and root in {"np", "pd"}
            and node.func.attr in _BANNED_DATA_CALLS
        ):
            self.add(
                node,
                "forbidden_data_access",
                f"{root}.{node.func.attr}() cannot access files or external data.",
            )
        if root and not banned_builtin:
            if root not in (_APPROVED_ROOTS | _SAFE_BUILTINS | self.bound_names):
                self.add(node, "unapproved_namespace", f"{root} is not an approved SDK namespace.")
            elif root in _APPROVED_ROOTS:
                self.dependencies.add(root)
        if (
            isinstance(node.func, ast.Attribute)
            and root == "market"
            and node.func.attr == "percent_change"
        ):
            # Calendar-period strings are resolved at execution time; numeric
            # bar windows are safe to expose as a static lookback hint.
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant):
                self.record_lookback(first.value)
        if isinstance(node.func, ast.Attribute) and root == "ta" and node.func.attr == "indicator":
            # The canonical facade receives (type, params, output). Inspect
            # literal parameter maps, while leaving dynamic values unclaimed.
            params = node.args[1] if len(node.args) > 1 else None
            if isinstance(params, ast.Dict):
                window_keys = {
                    "period",
                    "length",
                    "window",
                    "lookback",
                    "fast_period",
                    "slow_period",
                    "signal_period",
                    "k_period",
                    "d_period",
                    "smooth_period",
                    "stddev_period",
                    "atr_period",
                }
                for key, value in zip(params.keys, params.values):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value in window_keys
                        and isinstance(value, ast.Constant)
                    ):
                        self.record_lookback(value.value)
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "rolling",
            "sma",
            "ema",
            "rsi",
        }:
            for argument in node.args:
                if (
                    isinstance(argument, ast.Constant)
                    and isinstance(argument.value, int)
                    and argument.value > 0
                ):
                    self.record_lookback(argument.value)
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "output"
            and node.func.attr
            in {
                "scalar",
                "series",
                "boolean",
                "events",
                "table",
                "bar",
                "histogram",
                "range",
                "scatter",
                "heatmap",
                "dashboard",
            }
        ):
            self.output_contracts.add(node.func.attr)
        self.generic_visit(node)


def _attribute_root(node: ast.AST) -> str | None:
    current = node
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def validate_workstation_python(source: str) -> ValidationResult:
    """Validate source without evaluating it or importing user-selected modules."""
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        return ValidationResult(
            diagnostics=(
                CodeDiagnostic("syntax_error", exc.msg, exc.lineno or 1, (exc.offset or 1) - 1),
            ),
            dependencies=(),
            lookback_hint=None,
            output_contracts=(),
        )
    validator = _Validator()
    # Pre-compute local bindings so ordinary Python composition is valid even
    # when a value is referenced before its assignment in source traversal.
    validator.bound_names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    validator.visit(tree)
    return ValidationResult(
        diagnostics=tuple(validator.diagnostics),
        dependencies=tuple(sorted(validator.dependencies)),
        lookback_hint=validator.lookback_hint,
        output_contracts=tuple(sorted(validator.output_contracts)),
    )
