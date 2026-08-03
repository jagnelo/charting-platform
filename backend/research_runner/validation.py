"""Standalone copy of the runner's static source gate.

Keep this module standard-library only: the isolated image must not import the
application, provider adapters, configuration, or credentials.
"""

import ast
from dataclasses import dataclass

_ROOTS = {"market", "ta", "stats", "research", "output", "np", "pd", "scipy", "statsmodels"}
_BANNED = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.Lambda, ast.ClassDef, ast.With, ast.AsyncWith, ast.Try, ast.Raise)
_CALLS = {"eval", "exec", "compile", "open", "input", "__import__", "globals", "locals", "vars", "getattr", "setattr", "delattr", "help", "breakpoint"}
_BANNED_DATA_CALLS = {"read_csv", "read_excel", "read_json", "read_parquet", "read_pickle", "read_sql", "read_sql_query", "to_csv", "to_excel", "to_json", "to_parquet", "to_pickle", "to_sql", "load", "save", "savetxt", "fromfile"}


@dataclass(frozen=True)
class CodeDiagnostic:
    code: str
    message: str
    line: int
    column: int


@dataclass(frozen=True)
class ValidationResult:
    diagnostics: tuple[CodeDiagnostic, ...]

    @property
    def valid(self) -> bool:
        return not self.diagnostics


def validate_workstation_python(source: str) -> ValidationResult:
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        return ValidationResult((CodeDiagnostic("syntax_error", exc.msg, exc.lineno or 1, (exc.offset or 1) - 1),))
    diagnostics: list[CodeDiagnostic] = []
    # Names introduced by the program itself may be used for ordinary Python
    # composition (for example ``fit = model.fit(); fit.rsquared``).  They are
    # still constrained by the same banned-syntax/call/attribute checks; this
    # only prevents the namespace gate from mistaking a local value for a host
    # module.  Imports and unbound names remain rejected.
    bound_names = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
    }
    approved_names = _ROOTS | bound_names
    for node in ast.walk(tree):
        if isinstance(node, _BANNED):
            diagnostics.append(CodeDiagnostic("forbidden_syntax", f"{type(node).__name__} is not available.", getattr(node, "lineno", 1), getattr(node, "col_offset", 0)))
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            diagnostics.append(CodeDiagnostic("forbidden_attribute", "Dunder attributes are not available.", node.lineno, node.col_offset))
        if isinstance(node, ast.Call):
            root = node.func
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(node.func, ast.Attribute) and isinstance(root, ast.Name) and root.id in {"np", "pd"} and node.func.attr in _BANNED_DATA_CALLS:
                diagnostics.append(CodeDiagnostic("forbidden_data_access", f"{root.id}.{node.func.attr}() cannot access files or external data.", node.lineno, node.col_offset))
            if isinstance(root, ast.Name) and root.id in _CALLS:
                diagnostics.append(CodeDiagnostic("forbidden_call", f"{root.id}() is not available.", node.lineno, node.col_offset))
            elif isinstance(root, ast.Name) and root.id not in approved_names:
                diagnostics.append(CodeDiagnostic("unapproved_namespace", f"{root.id} is not approved.", node.lineno, node.col_offset))
    return ValidationResult(tuple(diagnostics))
