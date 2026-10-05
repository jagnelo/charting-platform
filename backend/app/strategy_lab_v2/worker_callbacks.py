"""Application-owned callback composition for the dedicated Strategy Lab worker."""

from __future__ import annotations

import inspect
import os
from collections.abc import Awaitable, Callable
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from app.strategy_lab_v2.nautilus_worker_terminal import (
    create_nautilus_oos_worker_terminal_evidence_resolver,
)
from app.strategy_lab_v2.persistence import SearchDispatchBindingResolver
from app.strategy_lab_v2.postgres_search_dispatch import SearchDispatchRecord
from app.strategy_lab_v2.search_dispatch_rpc import UnixSocketSearchDispatchClient
from app.strategy_lab_v2.search_worker_handoff import (
    create_authenticated_search_dispatch_materializer,
)
from app.strategy_lab_v2.trial_hydration import (
    NautilusTrialDomainHydrator,
    OwnerScopedDomainReader,
)
from app.strategy_lab_v2.worker_consumer import WorkerHandleDecision, WorkerHandleResult
from app.strategy_lab_v2.worker_evidence import WorkerSubmissionBinding
from app.strategy_lab_v2.worker_handoff import materialize_worker_handoff
from app.strategy_lab_v2.worker_process import WorkerExecutionRequest
from app.strategy_lab_v2.worker_recovery_application import (
    create_worker_recovery_application,
)
from app.strategy_lab_v2.worker_service import (
    WorkerServiceCallbacks,
    WorkerTerminalWriter,
)
from app.strategy_lab_v2.worker_terminal_adapter import WorkerTerminalEvidenceResolver

EvidenceResolverFactory = Callable[
    ..., WorkerTerminalEvidenceResolver | Awaitable[WorkerTerminalEvidenceResolver]
]


async def create(
    persistence: Any,
    artifact_root: Path,
    *,
    search_dispatch_binding_resolver: SearchDispatchBindingResolver | None = None,
) -> WorkerServiceCallbacks:
    """Build typed handoff/terminal callbacks for one worker process."""

    if not callable(getattr(persistence, "worker_terminal_writer", None)):
        raise TypeError("persistence must expose worker_terminal_writer()")
    if not isinstance(artifact_root, Path):
        raise TypeError("artifact_root must be a Path")
    resolver_factory = _load_resolver_factory(os.environ.get("STRATEGY_LAB_V2_EVIDENCE_RESOLVER"))
    resolver = _invoke_evidence_resolver_factory(
        resolver_factory,
        persistence,
        artifact_root,
        search_dispatch_binding_resolver=search_dispatch_binding_resolver,
    )
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


async def create_search_dispatch(persistence: Any, artifact_root: Path) -> WorkerServiceCallbacks:
    """Build callbacks that authenticate search dispatches before decoding.

    This is an explicit callback-factory variant for a worker whose queue is
    populated by the search-dispatch transaction.  The ordinary ``create``
    factory remains available for submission-backed queues; selecting this
    factory is a host configuration decision and requires the queue identity
    to be declared through the same ``STRATEGY_LAB_V2_QUEUE`` setting as the
    worker entrypoint.
    """

    dispatch_store = getattr(persistence, "search_dispatch", None)
    queue_name = os.environ.get("STRATEGY_LAB_V2_QUEUE")
    if dispatch_store is None:
        raise TypeError("persistence must expose search_dispatch")
    if queue_name is None or not queue_name.strip():
        raise ValueError("STRATEGY_LAB_V2_QUEUE must be configured for search dispatch workers")
    resources = getattr(persistence, "resources", None)
    if resources is None or not all(
        callable(getattr(resources, method, None))
        for method in (
            "get_domain_contract",
            "get_domain_contract_by_fingerprint",
            "get_domain_contracts_by_fingerprint",
        )
    ):
        raise TypeError("persistence must expose owner-scoped domain resource reads")
    binding_resolver = create_default_search_dispatch_binding_resolver(persistence)
    callbacks = await create(
        persistence,
        artifact_root,
        search_dispatch_binding_resolver=binding_resolver,
    )
    materializer = create_authenticated_search_dispatch_materializer(
        dispatch_store,
        queue_name=queue_name,
        domain_hydrator=NautilusTrialDomainHydrator(cast(OwnerScopedDomainReader, resources)),
    )
    worker_state = getattr(persistence, "worker_state", None)
    if worker_state is None or not callable(getattr(worker_state, "load_lease", None)):
        raise TypeError("persistence.worker_state must expose load_lease()")
    recovery_application = create_worker_recovery_application(
        persistence,
        queue_name=queue_name,
        dispatch_client=UnixSocketSearchDispatchClient.from_environment(),
    )
    terminal_writer = callbacks.terminal_writer
    if terminal_writer is None:
        raise TypeError("search dispatch workers require a terminal writer")

    async def terminal_dispatch_writer(context: Any) -> WorkerHandleResult:
        result = await terminal_writer(context)
        if result.decision is not WorkerHandleDecision.COMPLETE:
            return result
        search_receipt = await recovery_application.complete_terminal_if_persisted(
            entry=context.entry,
            request=context.request,
            observed_at=context.observed_at,
        )
        return result if search_receipt is None else search_receipt

    async def lease_state_reader(request: WorkerExecutionRequest):
        return await worker_state.load_lease(request.lease_state.lease.lease_id)

    return WorkerServiceCallbacks(
        materializer,
        callbacks.completion_writer,
        heartbeat_writer=callbacks.heartbeat_writer,
        terminal_writer=terminal_dispatch_writer,
        recovery_writer=recovery_application,
        lease_state_reader=lease_state_reader,
    )


def default_evidence_resolver_factory(
    persistence: Any,
    artifact_root: Path,
    *,
    search_dispatch_binding_resolver: SearchDispatchBindingResolver | None = None,
) -> WorkerTerminalEvidenceResolver:
    """Compose owner-authenticated Nautilus OOS result publication.

    The configured resolver uses the durable owner/attempt lookup, rehydrates
    the exact typed trial graph, derives OOS metrics from verified native
    output, and creates the per-artifact publication evidence required by the
    terminal writer. Exact conformance evidence comes from the immutable
    parent-owned worker request and is checked against its execution plan.
    """

    if not isinstance(artifact_root, Path):
        raise TypeError("artifact_root must be a Path")
    artifact_publication = getattr(persistence, "artifact_publication", None)
    lookup_loader = getattr(persistence, "load_worker_terminal_evidence_for_request", None)
    resources = getattr(persistence, "resources", None)
    if not callable(artifact_publication):
        raise TypeError("persistence must expose artifact_publication()")
    if not callable(lookup_loader):
        raise TypeError("persistence must expose load_worker_terminal_evidence_for_request()")
    if resources is None or not all(
        callable(getattr(resources, method, None))
        for method in (
            "get_domain_contract",
            "get_domain_contract_by_fingerprint",
            "get_domain_contracts_by_fingerprint",
        )
    ):
        raise TypeError("persistence must expose owner-scoped domain resource reads")
    publisher = artifact_publication(artifact_root)
    hydrator = NautilusTrialDomainHydrator(cast(OwnerScopedDomainReader, resources))

    async def lookup(*, request_fingerprint: str, attempt_id: str):
        return await lookup_loader(
            request_fingerprint=request_fingerprint,
            attempt_id=attempt_id,
            search_dispatch_binding_resolver=search_dispatch_binding_resolver,
        )

    resolver = create_nautilus_oos_worker_terminal_evidence_resolver(
        lookup,
        publisher,
        hydrator,
    )
    if not callable(resolver):
        raise TypeError("Nautilus OOS resolver factory returned an invalid callback")
    return cast(WorkerTerminalEvidenceResolver, resolver)


def create_default_search_dispatch_binding_resolver(
    persistence: Any,
) -> SearchDispatchBindingResolver:
    """Bind search dispatches to the authoritative persisted submission."""

    submissions = getattr(persistence, "submissions", None)
    loader = getattr(submissions, "load_submission", None)
    if not callable(loader):
        raise TypeError("persistence.submissions must expose load_submission()")

    async def resolve(dispatch: SearchDispatchRecord) -> WorkerSubmissionBinding | None:
        if not isinstance(dispatch, SearchDispatchRecord):
            raise TypeError("dispatch must be a SearchDispatchRecord")
        receipt = await loader(
            principal=dispatch.owner_id,
            attempt_id=dispatch.request.attempt_id,
        )
        if receipt is None:
            return None
        return WorkerSubmissionBinding(dispatch.owner_id, receipt)

    return resolve


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


def _invoke_evidence_resolver_factory(
    factory: EvidenceResolverFactory,
    persistence: Any,
    artifact_root: Path,
    *,
    search_dispatch_binding_resolver: SearchDispatchBindingResolver | None,
) -> WorkerTerminalEvidenceResolver | Awaitable[WorkerTerminalEvidenceResolver]:
    if search_dispatch_binding_resolver is None:
        return factory(persistence, artifact_root)
    try:
        parameters = inspect.signature(factory).parameters.values()
    except (TypeError, ValueError) as error:
        raise TypeError(
            "search evidence resolver factory must expose the binding callback parameter"
        ) from error
    accepts_binding = any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        or parameter.name == "search_dispatch_binding_resolver"
        for parameter in parameters
    )
    if not accepts_binding:
        raise TypeError(
            "search evidence resolver factory must accept search_dispatch_binding_resolver"
        )
    return factory(
        persistence,
        artifact_root,
        search_dispatch_binding_resolver=search_dispatch_binding_resolver,
    )


__all__ = [
    "EvidenceResolverFactory",
    "create",
    "create_search_dispatch",
    "create_default_search_dispatch_binding_resolver",
    "default_evidence_resolver_factory",
]
