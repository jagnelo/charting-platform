"""Guard: CPU-bound breadth evaluators must never run on the asyncio event loop.

``evaluate_breadth`` and friends are pure synchronous loops over every member bar.
Calling them directly inside an async handler blocks the loop, so concurrent reads
(benchmark-family readiness, snapshots, ETF reads) queue behind them. Async code
must dispatch them through ``asyncio.to_thread``.
"""

import ast
from pathlib import Path

import app.routers.analysis as analysis_module

_CPU_BOUND = {
    "evaluate_breadth",
    "evaluate_breadth_history",
    "detect_breadth_occurrences",
    "_python_breadth_occurrences",
}


def _is_to_thread(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "to_thread"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "asyncio"
    )


def test_async_code_only_reaches_breadth_evaluators_through_asyncio_to_thread():
    tree = ast.parse(Path(analysis_module.__file__).read_text())
    offloaded_calls = 0
    direct_calls: list[int] = []
    for func in (n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)):
        for node in ast.walk(func):
            if _is_to_thread(node):
                if node.args and isinstance(node.args[0], ast.Name):
                    offloaded_calls += node.args[0].id in _CPU_BOUND
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in _CPU_BOUND
            ):
                direct_calls.append(node.lineno)

    assert direct_calls == [], f"event-loop-blocking calls at lines {direct_calls}"
    assert offloaded_calls >= 6, "expected every breadth evaluator call to use asyncio.to_thread"
