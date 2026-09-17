"""Minimal strategy invocation runtime for an already-isolated worker process.

The host must still launch this package through the hardened sandbox adapter.
The runner adds a second, process-local defense: static source preflight,
restricted builtins/imports, source-digest binding, and typed SDK output
validation before an intent can reach host allocation and risk.
"""

from strategy_runtime.protocol import (
    BATCH_WIRE_PROTOCOL_VERSION,
    WIRE_PROTOCOL_VERSION,
    deserialize_invocation,
    deserialize_invocation_batch,
    deserialize_invocation_batch_result,
    deserialize_invocation_result,
    serialize_invocation,
    serialize_invocation_batch,
    serialize_invocation_batch_result,
    serialize_invocation_result,
)
from strategy_runtime.runner import (
    RUNTIME_ERROR_EVIDENCE_VERSION,
    InvocationStatus,
    StrategyInvocationResult,
    StrategyInvocationSession,
    main,
    run_strategy_event,
    run_strategy_events,
)

__all__ = [
    "InvocationStatus",
    "RUNTIME_ERROR_EVIDENCE_VERSION",
    "StrategyInvocationResult",
    "StrategyInvocationSession",
    "BATCH_WIRE_PROTOCOL_VERSION",
    "WIRE_PROTOCOL_VERSION",
    "deserialize_invocation_batch",
    "deserialize_invocation_batch_result",
    "deserialize_invocation",
    "deserialize_invocation_result",
    "main",
    "run_strategy_event",
    "run_strategy_events",
    "serialize_invocation_batch",
    "serialize_invocation_batch_result",
    "serialize_invocation",
    "serialize_invocation_result",
]
