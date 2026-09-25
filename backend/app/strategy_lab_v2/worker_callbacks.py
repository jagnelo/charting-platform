"""Application-owned callback composition for the dedicated Strategy Lab worker."""

from __future__ import annotations

import inspect
import os
from collections.abc import Awaitable, Callable
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from app.strategy_lab_v2.search_worker_handoff import (
    create_authenticated_search_dispatch_materializer,
)
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision, WorkerHandleResult
from app.strategy_lab_v2.worker_evidence_resolution import (
    create_sandbox_artifact_plan_resolver,
)
from app.strategy_lab_v2.worker_handoff import materialize_worker_handoff
from app.strategy_lab_v2.worker_service import WorkerServiceCallbacks, WorkerTerminalWriter
from app.strategy_lab_v2.worker_terminal_adapter import WorkerTerminalEvidenceResolver

EvidenceResolverFactory = Callable[
    [Any, Path], WorkerTerminalEvidenceResolver | Awaitable[WorkerTerminalEvidenceResolver]
]


async def create(persistence: Any, artifact_root: Path) -> WorkerServiceCallbacks:
    """Build typed handoff/terminal callbacks for one worker process."""

    if not callable(getattr(persistence, "worker_terminal_writer", None)):
        raise TypeError("persistence must expose worker_terminal_writer()")
    if not isinstance(artifact_root, Path):
        raise TypeError("artifact_root must be a Path")
    resolver_factory = _load_resolver_factory(
        os.environ.get("STRATEGY_LAB_V2_EVIDENCE_RESOLVER")
    )
    resolver = resolver_factory(persistence, artifact_root)
    if inspect.isawaitable(resolver):
        resolver = await resolver
    if not callable(resolver):
        raise TypeError("evidence resolver factory must return a callable")
    terminal_writer = persistence.worker_terminal_writer(
        cast(WorkerTerminalEvidenceResolver, resolver)
    )
    if not callable(terminal_writer):
        raise TypeError("persistence.worker_terminal_writer() must return a callable")
    return WorkerServiceCallbacks(
        materialize_worker_handoff,
        _terminal_only_completion,
        terminal_writer=cast(WorkerTerminalWriter, terminal_writer),
    )


async def create_search_dispatch(
    persistence: Any, artifact_root: Path
) -> WorkerServiceCallbacks:
    """Build callbacks that authenticate search dispatches before decoding.

    This is an explicit callback-factory variant for a worker whose queue is
    populated by the search-dispatch transaction.  The ordinary ``create``
    factory remains available for submission-backed queues; selecting this
    factory is a host configuration decision and requires the queue identity
    to be declared through the same ``STRATEGY_LAB_V2_QUEUE`` setting as the
    worker entrypoint.
    """

    callbacks = await create(persistence, artifact_root)
    dispatch_store = getattr(persistence, "search_dispatch", None)
    queue_name = os.environ.get("STRATEGY_LAB_V2_QUEUE")
    if dispatch_store is None:
        raise TypeError("persistence must expose search_dispatch")
    if queue_name is None or not queue_name.strip():
        raise ValueError("STRATEGY_LAB_V2_QUEUE must be configured for search dispatch workers")
    materializer = create_authenticated_search_dispatch_materializer(
        dispatch_store,
        queue_name=queue_name,
    )
    return WorkerServiceCallbacks(
        materializer,
        callbacks.completion_writer,
        heartbeat_writer=callbacks.heartbeat_writer,
        terminal_writer=callbacks.terminal_writer,
    )


def default_evidence_resolver_factory(
    persistence: Any, artifact_root: Path
) -> WorkerTerminalEvidenceResolver:
    """Compose the package-owned single-output evidence path.

    The callback remains opt-in through ``STRATEGY_LAB_V2_EVIDENCE_RESOLVER``;
    this factory only supplies the explicit composition once the host chooses
    it. Authentication/attempt lookup stays in the persistence bundle and
    artifact source policy stays in the sandbox mapper.
    """

    if not isinstance(artifact_root, Path):
        raise TypeError("artifact_root must be a Path")
    artifact_publication = getattr(persistence, "artifact_publication", None)
    evidence_resolver = getattr(persistence, "worker_terminal_evidence_resolver", None)
    if not callable(artifact_publication):
        raise TypeError("persistence must expose artifact_publication()")
    if not callable(evidence_resolver):
        raise TypeError("persistence must expose worker_terminal_evidence_resolver()")
    publisher = artifact_publication(artifact_root)
    artifact_plan_resolver = create_sandbox_artifact_plan_resolver(publisher)
    resolver = evidence_resolver(artifact_plan_resolver)
    if not callable(resolver):
        raise TypeError("persistence returned an invalid terminal evidence resolver")
    return cast(WorkerTerminalEvidenceResolver, resolver)


async def _terminal_only_completion(entry: Any, _process: Any) -> WorkerHandleResult:
    """Guard the legacy writer path; terminal_writer must own completion."""

    fingerprint = getattr(entry, "fingerprint", None)
    if not isinstance(fingerprint, str):
        raise TypeError("worker entry must expose a fingerprint")
    return WorkerHandleResult(
        fingerprint,
        WorkerHandleDecision.RETRY,
        rejection_reason="typed terminal writer is required for Strategy Lab completion",
    )


def _load_resolver_factory(spec: str | None) -> EvidenceResolverFactory:
    if spec is None or not spec.strip():
        raise ValueError("STRATEGY_LAB_V2_EVIDENCE_RESOLVER must be configured")
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name.strip() or not attribute.strip():
        raise ValueError("evidence resolver must use module:attribute syntax")
    module = import_module(module_name.strip())
    factory = getattr(module, attribute.strip(), None)
    if not callable(factory):
        raise TypeError("evidence resolver target must be callable")
    return cast(EvidenceResolverFactory, factory)


__all__ = [
    "EvidenceResolverFactory",
    "create",
    "create_search_dispatch",
    "default_evidence_resolver_factory",
]
