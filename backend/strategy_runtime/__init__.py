"""Minimal strategy invocation runtime for an already-isolated worker process.

The host must still launch this package through the hardened sandbox adapter.
The runner adds a second, process-local defense: static source preflight,
restricted builtins/imports, source-digest binding, and typed SDK output
validation before an intent can reach host allocation and risk.
"""

from strategy_runtime.runner import (
    InvocationStatus,
    StrategyInvocationResult,
    run_strategy_event,
)

__all__ = ["InvocationStatus", "StrategyInvocationResult", "run_strategy_event"]
