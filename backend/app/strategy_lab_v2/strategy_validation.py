"""Static preflight checks for trusted strategy source packages.

This module is deliberately not a sandbox. It rejects common import, dynamic
execution, and object-introspection escape surfaces before a later isolated
runtime receives a package.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest

DEFAULT_ALLOWED_IMPORT_ROOTS = frozenset(
    {
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "functools",
        "itertools",
        "math",
        "statistics",
        "typing",
    }
)
_FORBIDDEN_CALLS = frozenset(
    {
        "__import__",
        "breakpoint",
        "compile",
        "eval",
        "exec",
        "getattr",
        "globals",
        "hasattr",
        "help",
        "input",
        "locals",
        "open",
        "setattr",
        "vars",
    }
)
# ``datetime`` and ``date`` are useful for typed event values, but obtaining
# the current clock from a strategy would make a replay depend on wall time.
# Attribute calls are checked independently of the receiver so aliases such as
# ``clock.now()`` cannot bypass the static preflight.
_FORBIDDEN_CALL_ATTRIBUTES = frozenset({"now", "today", "utcnow"})
_FORBIDDEN_ATTRIBUTES = frozenset(
    {
        "builtins",
        "__builtins__",
        "__class__",
        "__code__",
        "__dict__",
        "__globals__",
        "__loader__",
        "__module__",
        "__spec__",
        "environ",
        "importlib",
        "marshal",
        "modules",
        "os",
        "pathlib",
        "pickle",
        "socket",
        "subprocess",
        "sys",
    }
)
_FORBIDDEN_IMPORT_ROOTS = frozenset(
    {
        "ctypes",
        "importlib",
        "marshal",
        "os",
        "pathlib",
        "pickle",
        "requests",
        "socket",
        "subprocess",
        "sys",
        "urllib",
    }
)
_FORBIDDEN_NAMES = _FORBIDDEN_CALLS | frozenset({"__builtins__", "__import__"})


@dataclass(frozen=True, slots=True)
class StrategySourceValidation:
    """Immutable static-validation result bound to the exact source digest."""

    source_digest: str
    violations: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return not self.violations


def source_set_digest(source_digests: Mapping[str, str]) -> str:
    """Bind a single source or the exact strategy/source set deterministically."""

    if not isinstance(source_digests, Mapping) or not source_digests:
        raise ValueError("source_digests must be a non-empty strategy-to-digest mapping")
    if any(not isinstance(key, str) for key in source_digests):
        raise TypeError("source_digests keys must be strategy fingerprint strings")
    bindings = tuple(sorted(source_digests.items()))
    for strategy_fingerprint, digest in bindings:
        require_sha256_digest(strategy_fingerprint, field_name="strategy_fingerprint")
        require_sha256_digest(digest, field_name="source_digest")
    if len(bindings) == 1:
        return bindings[0][1]
    return content_digest(
        {
            "schema": "strategy-lab.strategy-source-set.v1",
            "sources": bindings,
        }
    )


def validate_strategy_source(
    source: str,
    *,
    allowed_import_roots: frozenset[str] = DEFAULT_ALLOWED_IMPORT_ROOTS,
) -> StrategySourceValidation:
    """Return deterministic static violations without importing or executing code."""

    if not isinstance(source, str):
        raise TypeError("strategy source must be a string")
    if not isinstance(allowed_import_roots, frozenset) or any(
        not isinstance(root, str) or not root.strip() for root in allowed_import_roots
    ):
        raise TypeError("allowed_import_roots must be a frozenset of non-empty strings")

    violations: list[str] = []

    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as error:
        syntax_location = (
            f"{error.lineno}:{error.offset}" if error.lineno is not None else "unknown"
        )
        violations.append(f"syntax_error@{syntax_location}: {error.msg}")
        return StrategySourceValidation(content_digest(source), tuple(violations))

    def node_location(node: ast.AST) -> str:
        return f"{getattr(node, 'lineno', 0)}:{getattr(node, 'col_offset', 0) + 1}"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.partition(".")[0]
                if (
                    root not in allowed_import_roots
                    or root in _FORBIDDEN_IMPORT_ROOTS
                    or alias.name == "*"
                    or any(part.startswith("_") for part in alias.name.split("."))
                    or (alias.asname is not None and alias.asname.startswith("_"))
                ):
                    violations.append(f"forbidden_import@{node_location(node)}: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").partition(".")[0]
            module = "." * node.level + (node.module or "")
            if (
                node.level
                or root not in allowed_import_roots
                or root in _FORBIDDEN_IMPORT_ROOTS
                or any(part.startswith("_") for part in (node.module or "").split("."))
            ):
                violations.append(f"forbidden_import@{node_location(node)}: {module}")
            else:
                for alias in node.names:
                    if (
                        alias.name.startswith("_")
                        or (alias.asname is not None and alias.asname.startswith("_"))
                        or alias.name in _FORBIDDEN_ATTRIBUTES
                        or alias.name == "*"
                    ):
                        violations.append(
                            f"forbidden_import@{node_location(node)}: {module}.{alias.name}"
                        )
        elif isinstance(node, ast.Call):
            function_name = node.func.id if isinstance(node.func, ast.Name) else None
            if function_name in _FORBIDDEN_CALLS:
                violations.append(f"forbidden_call@{node_location(node)}: {function_name}")
            elif (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _FORBIDDEN_CALL_ATTRIBUTES
            ):
                violations.append(f"forbidden_wall_clock@{node_location(node)}: {node.func.attr}")
        elif isinstance(node, ast.Attribute):
            if node.attr in _FORBIDDEN_CALL_ATTRIBUTES:
                violations.append(f"forbidden_wall_clock@{node_location(node)}: {node.attr}")
            elif node.attr in _FORBIDDEN_ATTRIBUTES or node.attr.startswith("_"):
                violations.append(f"forbidden_attribute@{node_location(node)}: {node.attr}")
        elif isinstance(node, ast.Name) and node.id in _FORBIDDEN_NAMES:
            violations.append(f"forbidden_name@{node_location(node)}: {node.id}")

    return StrategySourceValidation(content_digest(source), tuple(sorted(set(violations))))


def validate_strategy_source_set(
    sources: Mapping[str, str],
    *,
    allowed_import_roots: frozenset[str] = DEFAULT_ALLOWED_IMPORT_ROOTS,
) -> StrategySourceValidation:
    """Validate every pinned strategy source and bind one aggregate identity.

    A portfolio may contain several distinct strategies. Its authorization must
    bind the same aggregate source digest as the runtime request, while retaining
    all component validation failures rather than validating only a primary source.
    """

    if not isinstance(sources, Mapping) or not sources:
        raise ValueError("sources must be a non-empty strategy-to-source mapping")
    if any(not isinstance(key, str) for key in sources):
        raise TypeError("sources keys must be strategy fingerprint strings")
    validations: dict[str, StrategySourceValidation] = {}
    for strategy_fingerprint, source in sorted(sources.items()):
        require_sha256_digest(strategy_fingerprint, field_name="strategy_fingerprint")
        validations[strategy_fingerprint] = validate_strategy_source(
            source,
            allowed_import_roots=allowed_import_roots,
        )
    return combine_strategy_source_validations(validations)


def combine_strategy_source_validations(
    validations: Mapping[str, StrategySourceValidation],
) -> StrategySourceValidation:
    """Bind already-computed validation results to their exact strategy set."""

    if not isinstance(validations, Mapping) or not validations:
        raise ValueError("validations must be a non-empty strategy-to-validation mapping")
    if any(not isinstance(key, str) for key in validations):
        raise TypeError("validations keys must be strategy fingerprint strings")
    for strategy_fingerprint, validation in validations.items():
        require_sha256_digest(strategy_fingerprint, field_name="strategy_fingerprint")
        if not isinstance(validation, StrategySourceValidation):
            raise TypeError("validations values must be StrategySourceValidation instances")
    digest = source_set_digest(
        {
            strategy_fingerprint: validation.source_digest
            for strategy_fingerprint, validation in sorted(validations.items())
        }
    )
    if len(validations) == 1:
        only_validation = next(iter(validations.values()))
        return StrategySourceValidation(digest, only_validation.violations)
    violations = tuple(
        sorted(
            f"strategy[{strategy_fingerprint}]:{violation}"
            for strategy_fingerprint, validation in validations.items()
            for violation in validation.violations
        )
    )
    return StrategySourceValidation(digest, violations)
