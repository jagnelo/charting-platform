"""Static validation for the single workstation Python language.

This is deliberately a *gate*, not a sandbox.  Passing validation only allows a
submission to be prepared for the isolated execution service; it must never make
execution in FastAPI or a general worker permissible.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

_APPROVED_ROOTS = {"market", "ta", "stats", "research", "output", "np", "pd", "scipy", "statsmodels"}
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
    "eval", "exec", "compile", "open", "input", "__import__", "globals", "locals",
    "vars", "getattr", "setattr", "delattr", "help", "breakpoint",
}
_BANNED_DATA_CALLS = {
    "read_csv", "read_excel", "read_json", "read_parquet", "read_pickle", "read_sql", "read_sql_query",
    "to_csv", "to_excel", "to_json", "to_parquet", "to_pickle", "to_sql", "load", "save", "savetxt", "fromfile",
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
        self.diagnostics.append(CodeDiagnostic(
            code=code,
            message=message,
            line=getattr(node, "lineno", 1),
            column=getattr(node, "col_offset", 0),
        ))

    def visit(self, node: ast.AST) -> None:
        if isinstance(node, _BANNED_NODES):
            self.add(node, "forbidden_syntax", f"{type(node).__name__} is not available in workstation code.")
            return
        super().visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            self.add(node, "forbidden_attribute", "Dunder attributes are not available.")
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
        if isinstance(node.func, ast.Attribute) and root in {"np", "pd"} and node.func.attr in _BANNED_DATA_CALLS:
            self.add(node, "forbidden_data_access", f"{root}.{node.func.attr}() cannot access files or external data.")
        if root and not banned_builtin:
            if root not in (_APPROVED_ROOTS | self.bound_names):
                self.add(node, "unapproved_namespace", f"{root} is not an approved SDK namespace.")
            elif root in _APPROVED_ROOTS:
                self.dependencies.add(root)
        if isinstance(node.func, ast.Attribute) and node.func.attr in {"rolling", "sma", "ema", "rsi"}:
            for argument in node.args:
                if isinstance(argument, ast.Constant) and isinstance(argument.value, int) and argument.value > 0:
                    self.lookback_hint = max(self.lookback_hint or 0, argument.value)
        if (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "output"
            and node.func.attr in {"scalar", "series", "boolean", "events", "table", "histogram", "scatter", "heatmap"}
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
            diagnostics=(CodeDiagnostic("syntax_error", exc.msg, exc.lineno or 1, (exc.offset or 1) - 1),),
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
