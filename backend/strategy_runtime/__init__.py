"""Minimal strategy invocation runtime for an already-isolated worker process.

The host must still launch this package through the hardened sandbox adapter.
The runner adds a second, process-local defense: static source preflight,
restricted builtins/imports, source-digest binding, and typed SDK output
validation before an intent can reach host allocation and risk.
"""

from typing import Any

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

_CUSTOM_METRIC_EXPORTS = frozenset(
    {
        "CUSTOM_METRIC_BATCH_WIRE_PROTOCOL_VERSION",
        "CUSTOM_METRIC_WIRE_PROTOCOL_VERSION",
        "deserialize_custom_metric_invocation",
        "deserialize_custom_metric_invocation_batch",
        "deserialize_custom_metric_result",
        "deserialize_custom_metric_result_batch",
        "serialize_custom_metric_invocation",
        "serialize_custom_metric_invocation_batch",
        "serialize_custom_metric_result",
        "serialize_custom_metric_result_batch",
    }
)


def __getattr__(name: str) -> Any:
    """Lazily expose custom-metric wire helpers without package import cycles."""

    if name not in _CUSTOM_METRIC_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from strategy_runtime import custom_metric_protocol

    value = getattr(custom_metric_protocol, name)
    globals()[name] = value
    return value

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
    "CUSTOM_METRIC_BATCH_WIRE_PROTOCOL_VERSION",
    "CUSTOM_METRIC_WIRE_PROTOCOL_VERSION",
    "deserialize_custom_metric_invocation",
    "deserialize_custom_metric_invocation_batch",
    "deserialize_custom_metric_result",
    "deserialize_custom_metric_result_batch",
    "serialize_custom_metric_invocation",
    "serialize_custom_metric_invocation_batch",
    "serialize_custom_metric_result",
    "serialize_custom_metric_result_batch",
]
