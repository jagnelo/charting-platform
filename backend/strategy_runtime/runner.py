"""Restricted engine-neutral strategy invocation for sandbox worker images.

This module deliberately does not create a process or provide a security
boundary on its own.  A worker must call it inside the pinned no-network
container produced by :mod:`app.strategy_lab_v2.sandbox`.  It nevertheless
uses a restricted builtins/import surface and repeats source validation so a
direct caller cannot accidentally treat a digest as proof of safety.
"""

from __future__ import annotations

import builtins
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import ModuleType
from typing import Any

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.sdk import (
    Decimal,
    EngineNeutralStrategy,
    MarketEvent,
    OrderIntent,
    OrderSide,
    OrderType,
    PositionSnapshot,
    StrategyContext,
    StrategyIntent,
    StrategySdkManifest,
    TargetPositionIntent,
    TimeInForce,
    validate_strategy_output,
)
from app.strategy_lab_v2.strategy_validation import (
    DEFAULT_ALLOWED_IMPORT_ROOTS,
    validate_strategy_source,
)


class InvocationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class StrategyInvocationResult:
    """Content-addressed result of one strategy event invocation."""

    source_digest: str
    context_fingerprint: str
    entrypoint: str
    status: InvocationStatus
    intents: tuple[StrategyIntent, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    error_digest: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.source_digest, field_name="source_digest")
        require_sha256_digest(self.context_fingerprint, field_name="context_fingerprint")
        if not isinstance(self.entrypoint, str) or not self.entrypoint.strip():
            raise ValueError("entrypoint must not be empty")
        if not isinstance(self.status, InvocationStatus):
            raise TypeError("status must be an InvocationStatus")
        intents = tuple(self.intents)
        if any(not isinstance(item, OrderIntent | TargetPositionIntent) for item in intents):
            raise TypeError("intents must contain typed StrategyIntent values")
        reasons = tuple(self.rejection_reasons)
        if len(reasons) != len(set(reasons)) or any(
            not isinstance(reason, str) or not reason.strip() for reason in reasons
        ):
            raise ValueError("invocation rejection reasons must be unique and non-empty")
        if self.error_digest is not None:
            require_sha256_digest(self.error_digest, field_name="error_digest")
        if self.status is InvocationStatus.SUCCEEDED:
            if reasons or self.error_digest is not None:
                raise ValueError("successful invocations cannot contain rejection or error evidence")
        elif self.status is InvocationStatus.REJECTED:
            if not reasons or intents or self.error_digest is not None:
                raise ValueError("rejected invocations require reasons and no intents or error")
        elif not self.error_digest or reasons:
            raise ValueError("failed invocations require an error digest and no rejection reasons")
        object.__setattr__(self, "intents", intents)
        object.__setattr__(self, "rejection_reasons", reasons)

    @property
    def accepted(self) -> bool:
        return self.status is InvocationStatus.SUCCEEDED

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def _safe_import(
    name: str,
    globals: Mapping[str, Any] | None = None,
    locals: Mapping[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> ModuleType:
    """Import only the standard-library roots accepted by static preflight."""

    if level or not isinstance(name, str) or not name:
        raise ImportError("relative or empty imports are unavailable in the strategy runtime")
    root = name.partition(".")[0]
    if root not in DEFAULT_ALLOWED_IMPORT_ROOTS:
        raise ImportError(f"strategy import root {root!r} is not allowed")
    return builtins.__import__(name, globals, locals, fromlist, level)


def _restricted_builtins() -> dict[str, Any]:
    """Return the small builtin surface available to trusted strategy code."""

    names = (
        "__build_class__",
        "abs",
        "all",
        "any",
        "AssertionError",
        "bool",
        "dict",
        "enumerate",
        "Exception",
        "float",
        "IndexError",
        "isinstance",
        "issubclass",
        "KeyError",
        "iter",
        "len",
        "list",
        "max",
        "min",
        "next",
        "object",
        "property",
        "range",
        "reversed",
        "set",
        "sorted",
        "staticmethod",
        "classmethod",
        "str",
        "sum",
        "super",
        "tuple",
        "type",
        "RuntimeError",
        "TypeError",
        "ValueError",
        "zip",
    )
    result = {name: getattr(builtins, name) for name in names}
    result["__import__"] = _safe_import
    return result


def _error_digest(error: BaseException) -> str:
    return content_digest({"type": type(error).__name__, "message": str(error)})


def _rejected(
    source_digest: str,
    context: StrategyContext,
    entrypoint: str,
    *reasons: str,
) -> StrategyInvocationResult:
    return StrategyInvocationResult(
        source_digest=source_digest,
        context_fingerprint=content_digest(context),
        entrypoint=entrypoint,
        status=InvocationStatus.REJECTED,
        rejection_reasons=tuple(sorted(set(reasons))),
    )


def _failed(
    source_digest: str,
    context: StrategyContext,
    entrypoint: str,
    error: BaseException,
) -> StrategyInvocationResult:
    return StrategyInvocationResult(
        source_digest=source_digest,
        context_fingerprint=content_digest(context),
        entrypoint=entrypoint,
        status=InvocationStatus.FAILED,
        error_digest=_error_digest(error),
    )


def _load_strategy(source: str, entrypoint: str, source_digest: str) -> EngineNeutralStrategy:
    module_name, separator, callable_name = entrypoint.partition(":")
    if not separator or not module_name or not callable_name:
        raise ValueError("entrypoint must use module.path:callable syntax")
    if any(not token.isidentifier() for token in module_name.split(".")):
        raise ValueError("entrypoint module path is invalid")
    if not callable_name.isidentifier():
        raise ValueError("entrypoint callable name is invalid")

    namespace: dict[str, Any] = {
        "__name__": module_name,
        "__package__": module_name.rpartition(".")[0],
        "__file__": f"<strategy:{source_digest}>",
        "__builtins__": _restricted_builtins(),
        "Decimal": Decimal,
        "EngineNeutralStrategy": EngineNeutralStrategy,
        "MarketEvent": MarketEvent,
        "OrderIntent": OrderIntent,
        "OrderSide": OrderSide,
        "OrderType": OrderType,
        "PositionSnapshot": PositionSnapshot,
        "StrategyContext": StrategyContext,
        "TargetPositionIntent": TargetPositionIntent,
        "TimeInForce": TimeInForce,
    }
    code = compile(source, namespace["__file__"], "exec")
    exec(code, namespace, namespace)
    candidate = namespace.get(callable_name)
    if candidate is None:
        raise LookupError(f"strategy entrypoint {callable_name!r} was not defined")
    strategy = candidate() if isinstance(candidate, type) else candidate
    handler = getattr(strategy, "on_event", None)
    if not callable(handler):
        raise TypeError("strategy entrypoint must provide a callable on_event method")
    return strategy


def run_strategy_event(
    source: str,
    *,
    manifest: StrategySdkManifest,
    context: StrategyContext,
    entrypoint: str,
    max_intents_per_event: int = 100,
) -> StrategyInvocationResult:
    """Run one source-bound strategy event and validate its typed output.

    Static violations and source identity drift are explicit rejections.  A
    strategy exception or output contract violation becomes a typed failed
    invocation with only an error digest; exception text is never returned as
    runtime evidence.
    """

    if not isinstance(source, str):
        raise TypeError("source must be a string")
    if not isinstance(manifest, StrategySdkManifest):
        raise TypeError("manifest must use StrategySdkManifest")
    if not isinstance(context, StrategyContext):
        raise TypeError("context must use StrategyContext")
    if not isinstance(entrypoint, str) or not entrypoint.strip():
        raise ValueError("entrypoint must not be empty")
    if (
        not isinstance(max_intents_per_event, int)
        or isinstance(max_intents_per_event, bool)
        or max_intents_per_event < 1
    ):
        raise ValueError("max_intents_per_event must be a positive integer")

    source_digest = content_digest(source)
    if source_digest != manifest.strategy.source_digest:
        return _rejected(source_digest, context, entrypoint, "source_digest_mismatch")
    validation = validate_strategy_source(source)
    if not validation.accepted:
        return _rejected(
            source_digest,
            context,
            entrypoint,
            *(f"source:{violation}" for violation in validation.violations),
        )

    try:
        strategy = _load_strategy(source, entrypoint, source_digest)
        raw_intents = strategy.on_event(context)
        intents = validate_strategy_output(
            manifest,
            raw_intents,
            max_intents_per_event=max_intents_per_event,
        )
    except BaseException as error:
        if isinstance(error, KeyboardInterrupt | SystemExit):
            raise
        return _failed(source_digest, context, entrypoint, error)
    return StrategyInvocationResult(
        source_digest=source_digest,
        context_fingerprint=content_digest(context),
        entrypoint=entrypoint,
        status=InvocationStatus.SUCCEEDED,
        intents=intents,
    )


__all__ = ["InvocationStatus", "StrategyInvocationResult", "run_strategy_event"]
