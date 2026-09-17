"""Restricted engine-neutral strategy invocation for sandbox worker images.

This module deliberately does not create a process or provide a security
boundary on its own.  A worker must call it inside the pinned no-network
container produced by :mod:`app.strategy_lab_v2.sandbox`.  It nevertheless
uses a restricted builtins/import surface and repeats source validation so a
direct caller cannot accidentally treat a digest as proof of safety.
"""

from __future__ import annotations

import argparse
import builtins
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
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


def _context_matches_manifest(
    manifest: StrategySdkManifest,
    context: StrategyContext,
) -> bool:
    """Check manifest scope without discarding already-typed optional fields."""

    declared = {item.dependency_id: item for item in manifest.data_dependencies}
    if set(context.market_events) != set(declared):
        return False
    allowed_instruments = {item.requirement.instrument_id for item in declared.values()}
    if not set(context.positions).issubset(allowed_instruments):
        return False
    for dependency_id, events in context.market_events.items():
        dependency = declared[dependency_id]
        if not isinstance(events, Sequence) or isinstance(events, str | bytes):
            return False
        if len(events) > dependency.lookback_periods + 1:
            return False
        required_fields = set(dependency.fields)
        for event in events:
            if not isinstance(event, MarketEvent):
                return False
            if event.dependency_id != dependency_id:
                return False
            if event.instrument_id != dependency.requirement.instrument_id:
                return False
            if not required_fields.issubset(set(event.values)):
                return False
            if not dependency.requirement.start <= event.event_time < dependency.requirement.end:
                return False
    return True


class StrategyInvocationSession:
    """Stateful, source-bound strategy invocation within one worker lifetime.

    A one-shot invocation is useful for protocol smoke tests, but a real replay
    must preserve strategy instance state across event boundaries. This class
    loads and validates the source once, then admits only manifest-compatible,
    monotonically advancing contexts. It remains process-local; the containing
    worker is still responsible for the isolated no-network resource boundary.
    """

    __slots__ = (
        "_entrypoint",
        "_failure_digest",
        "_initialization_error",
        "_last_context_key",
        "_manifest",
        "_max_intents_per_event",
        "_parameters_digest",
        "_random_seed",
        "_rejection_reasons",
        "_source_digest",
        "_strategy",
    )

    def __init__(
        self,
        source: str,
        *,
        manifest: StrategySdkManifest,
        entrypoint: str,
        max_intents_per_event: int = 100,
    ) -> None:
        if not isinstance(source, str):
            raise TypeError("source must be a string")
        if not isinstance(manifest, StrategySdkManifest):
            raise TypeError("manifest must use StrategySdkManifest")
        if not isinstance(entrypoint, str) or not entrypoint.strip():
            raise ValueError("entrypoint must not be empty")
        if (
            not isinstance(max_intents_per_event, int)
            or isinstance(max_intents_per_event, bool)
            or max_intents_per_event < 1
        ):
            raise ValueError("max_intents_per_event must be a positive integer")

        self._source_digest = content_digest(source)
        self._manifest = manifest
        self._entrypoint = entrypoint
        self._max_intents_per_event = max_intents_per_event
        self._last_context_key: tuple[Any, int] | None = None
        self._parameters_digest: str | None = None
        self._random_seed: int | None = None
        self._strategy: EngineNeutralStrategy | None = None
        self._rejection_reasons: tuple[str, ...] = ()
        self._initialization_error: BaseException | None = None
        self._failure_digest: str | None = None

        if self._source_digest != manifest.strategy.source_digest:
            self._rejection_reasons = ("source_digest_mismatch",)
            return
        validation = validate_strategy_source(source)
        if not validation.accepted:
            self._rejection_reasons = tuple(
                sorted(f"source:{violation}" for violation in validation.violations)
            )
            return
        try:
            self._strategy = _load_strategy(source, entrypoint, self._source_digest)
        except BaseException as error:
            if isinstance(error, KeyboardInterrupt | SystemExit):
                raise
            self._initialization_error = error

    @property
    def source_digest(self) -> str:
        return self._source_digest

    @property
    def entrypoint(self) -> str:
        return self._entrypoint

    @property
    def ready(self) -> bool:
        """Whether source loading and static preflight admitted the session."""

        return not self._rejection_reasons and self._initialization_error is None

    def invoke(self, context: StrategyContext) -> StrategyInvocationResult:
        """Invoke the same loaded strategy instance for one next context."""

        if not isinstance(context, StrategyContext):
            raise TypeError("context must use StrategyContext")
        if self._rejection_reasons:
            return _rejected(
                self._source_digest,
                context,
                self._entrypoint,
                *self._rejection_reasons,
            )
        if self._failure_digest is not None:
            return self._failed_digest(context, self._failure_digest)
        if self._initialization_error is not None or self._strategy is None:
            error = self._initialization_error or RuntimeError("strategy session is unavailable")
            return _failed(self._source_digest, context, self._entrypoint, error)

        # Re-run the SDK boundary for contexts constructed by direct callers;
        # a typed StrategyContext alone does not prove manifest scope. Optional
        # event fields remain available to the strategy, while every declared
        # field, instrument, lookback, and interval is still enforced.
        if not _context_matches_manifest(self._manifest, context):
            return _rejected(
                self._source_digest,
                context,
                self._entrypoint,
                "context_manifest_mismatch",
            )

        context_key = (context.event_time, context.event_sequence)
        if self._last_context_key is not None and context_key <= self._last_context_key:
            return _rejected(
                self._source_digest,
                context,
                self._entrypoint,
                "context_not_monotonic",
            )
        parameters_digest = content_digest(context.parameters)
        if self._parameters_digest is not None and parameters_digest != self._parameters_digest:
            return _rejected(
                self._source_digest,
                context,
                self._entrypoint,
                "context_parameters_changed",
            )
        if self._random_seed is not None and context.random_seed != self._random_seed:
            return _rejected(
                self._source_digest,
                context,
                self._entrypoint,
                "context_seed_changed",
            )

        try:
            raw_intents = self._strategy.on_event(context)
            intents = validate_strategy_output(
                self._manifest,
                raw_intents,
                max_intents_per_event=self._max_intents_per_event,
            )
        except BaseException as error:
            if isinstance(error, KeyboardInterrupt | SystemExit):
                raise
            self._failure_digest = _error_digest(error)
            return self._failed_digest(context, self._failure_digest)

        self._last_context_key = context_key
        self._parameters_digest = parameters_digest
        self._random_seed = context.random_seed
        return StrategyInvocationResult(
            source_digest=self._source_digest,
            context_fingerprint=content_digest(context),
            entrypoint=self._entrypoint,
            status=InvocationStatus.SUCCEEDED,
            intents=intents,
        )

    def _failed_digest(self, context: StrategyContext, error_digest: str) -> StrategyInvocationResult:
        return StrategyInvocationResult(
            source_digest=self._source_digest,
            context_fingerprint=content_digest(context),
            entrypoint=self._entrypoint,
            status=InvocationStatus.FAILED,
            error_digest=error_digest,
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

    if not isinstance(context, StrategyContext):
        raise TypeError("context must use StrategyContext")
    session = StrategyInvocationSession(
        source,
        manifest=manifest,
        entrypoint=entrypoint,
        max_intents_per_event=max_intents_per_event,
    )
    return session.invoke(context)


def run_strategy_events(
    source: str,
    *,
    manifest: StrategySdkManifest,
    contexts: Sequence[StrategyContext],
    entrypoint: str,
    max_intents_per_event: int = 100,
) -> tuple[StrategyInvocationResult, ...]:
    """Run a bounded chronological context sequence through one session.

    The session is created exactly once and invocation stops at the first
    typed rejection or failure.  This is the runtime-side primitive used by a
    replay adapter or an isolated worker; it intentionally does not know about
    snapshots, engines, orders, or persistence.
    """

    if not isinstance(contexts, Sequence) or isinstance(contexts, str | bytes):
        raise TypeError("contexts must be a sequence of StrategyContext values")
    contexts_tuple = tuple(contexts)
    if not contexts_tuple:
        raise ValueError("contexts must contain at least one StrategyContext")
    if any(not isinstance(context, StrategyContext) for context in contexts_tuple):
        raise TypeError("contexts must contain StrategyContext values")
    session = StrategyInvocationSession(
        source,
        manifest=manifest,
        entrypoint=entrypoint,
        max_intents_per_event=max_intents_per_event,
    )
    results: list[StrategyInvocationResult] = []
    for context in contexts_tuple:
        result = session.invoke(context)
        results.append(result)
        if result.status is not InvocationStatus.SUCCEEDED:
            break
    return tuple(results)


def _atomic_write(path: Path, payload: str) -> None:
    """Write a result beside the requested destination and publish it atomically."""

    parent = path.parent
    if not parent.is_dir():
        raise OSError("result parent directory does not exist")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _absolute_path(value: str, field_name: str) -> Path:
    path = Path(value)
    if not path.is_absolute() or "\x00" in value:
        raise ValueError(f"{field_name} must be an absolute path")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    """Run a mounted single-event or batch request and publish typed results.

    Exit status ``0`` means every context produced accepted intents.  Status
    ``2`` means the typed runtime result is rejected or failed.  Malformed
    input/output setup returns ``1`` without exposing exception text. Batch
    requests are attempted first; a valid single-event envelope remains fully
    backward compatible.
    """

    parser = argparse.ArgumentParser(description="run one Strategy Lab runtime invocation")
    parser.add_argument("--request", required=True, help="absolute mounted invocation JSON")
    parser.add_argument("--result", required=True, help="absolute result JSON destination")
    args = parser.parse_args(argv)
    try:
        request_path = _absolute_path(args.request, "request path")
        result_path = _absolute_path(args.result, "result path")
        from strategy_runtime.protocol import (
            deserialize_invocation,
            deserialize_invocation_batch,
            serialize_invocation_batch_result,
            serialize_invocation_result,
        )

        payload = request_path.read_text(encoding="utf-8")
        try:
            source, manifest, contexts, entrypoint, max_intents = deserialize_invocation_batch(
                payload
            )
        except (TypeError, ValueError):
            source, manifest, context, entrypoint, max_intents = deserialize_invocation(payload)
            result = run_strategy_event(
                source,
                manifest=manifest,
                context=context,
                entrypoint=entrypoint,
                max_intents_per_event=max_intents,
            )
            _atomic_write(result_path, serialize_invocation_result(result))
            return 0 if result.status is InvocationStatus.SUCCEEDED else 2

        results = run_strategy_events(
            source,
            manifest=manifest,
            contexts=contexts,
            entrypoint=entrypoint,
            max_intents_per_event=max_intents,
        )
        _atomic_write(result_path, serialize_invocation_batch_result(results))
        return 0 if len(results) == len(contexts) and all(
            item.status is InvocationStatus.SUCCEEDED for item in results
        ) else 2
    except (OSError, TypeError, UnicodeError, ValueError):
        return 1


__all__ = [
    "InvocationStatus",
    "StrategyInvocationResult",
    "StrategyInvocationSession",
    "main",
    "run_strategy_event",
    "run_strategy_events",
]
