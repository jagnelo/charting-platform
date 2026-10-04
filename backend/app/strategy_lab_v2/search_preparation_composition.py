"""Application-owned assembly for the isolated search-preparation process.

The host contributes only the provider-owned frozen-series decoder and
canonical market/runtime context resolver. PostgreSQL hydration, worker-state
reads, artifact verification, package resolution, runtime materialization, and
Nautilus RC evidence binding are composed here so a host plugin cannot replace
or broaden those platform-owned boundaries.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.conformance_fixtures import NautilusRcConformanceResolution
from app.strategy_lab_v2.engine_execution import NautilusExecutionScope
from app.strategy_lab_v2.event_tape_artifacts import FrozenSeriesDecoder
from app.strategy_lab_v2.nautilus_trial_materializer import (
    NautilusTrialRuntimeInputMaterializer,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.search_dispatch_preparation import (
    NautilusTrialPreparationContext,
    NautilusTrialSearchDispatchEvidenceResolver,
    PreparationContextResolver,
    SearchDispatchPreparationRequest,
)
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.trial_hydration import NautilusTrialDomainHydrator


@dataclass(frozen=True, slots=True)
class SearchPreparationHostBindings:
    """The narrow host-owned inputs not yet supplied by shared platform contracts."""

    runtime_abi: str
    series_decoder: FrozenSeriesDecoder
    context_resolver: PreparationContextResolver

    def __post_init__(self) -> None:
        if not isinstance(self.runtime_abi, str) or not self.runtime_abi.strip():
            raise ValueError("runtime_abi must not be empty")
        object.__setattr__(self, "runtime_abi", self.runtime_abi.strip())
        if not callable(getattr(self.series_decoder, "iter_rows", None)):
            raise TypeError("series_decoder must provide iter_rows(series, source)")
        if not callable(self.context_resolver):
            raise TypeError("context_resolver must be callable")


SearchPreparationHostBindingsFactory = Callable[
    [PostgresStrategyLabV2Persistence, Path, NautilusRcConformanceResolution],
    SearchPreparationHostBindings | Awaitable[SearchPreparationHostBindings],
]
BoundPreparationContextResolver = Callable[
    [SearchDispatchPreparationRequest, Any],
    Awaitable[NautilusTrialPreparationContext],
]


def bind_context_to_rc_evidence(
    context_resolver: PreparationContextResolver,
    *,
    conformance_resolution: NautilusRcConformanceResolution,
    runtime_abi: str,
) -> BoundPreparationContextResolver:
    """Reject host contexts that drift from the exact verified local RC source."""

    if not callable(context_resolver):
        raise TypeError("context_resolver must be callable")
    if not isinstance(conformance_resolution, NautilusRcConformanceResolution):
        raise TypeError("conformance_resolution must be a NautilusRcConformanceResolution")
    if not isinstance(runtime_abi, str) or not runtime_abi.strip():
        raise ValueError("runtime_abi must not be empty")
    release_pin = conformance_resolution.evidence.release_pin
    if release_pin is None:
        raise ValueError("local Nautilus RC evidence does not contain an exact runtime release pin")

    async def resolve_pinned_context(
        request: SearchDispatchPreparationRequest,
        graph: Any,
    ) -> NautilusTrialPreparationContext:
        result = context_resolver(request, graph)
        context = await result if inspect.isawaitable(result) else result
        if not isinstance(context, NautilusTrialPreparationContext):
            raise TypeError("context_resolver must return NautilusTrialPreparationContext")
        if context.conformance_evidence != conformance_resolution.evidence:
            raise ValueError("preparation context differs from the operator-pinned RC evidence")
        if context.conformance_report != conformance_resolution.report:
            raise ValueError("preparation context differs from the operator-pinned RC report")
        if context.runtime_profile.runtime_image_digest != release_pin.runtime_image_digest:
            raise ValueError(
                "preparation runtime profile differs from the operator-pinned RC image"
            )
        if context.runtime_profile.runtime_abi != runtime_abi:
            raise ValueError("preparation runtime ABI differs from the host binding")
        if context.execution_scope not in {
            NautilusExecutionScope.BACKTEST_COMPATIBILITY,
            NautilusExecutionScope.BACKTEST_AUTHORITATIVE,
        }:
            raise ValueError("RC search preparation is restricted to local backtest scopes")
        if context.requested_authoritative != (
            context.execution_scope is NautilusExecutionScope.BACKTEST_AUTHORITATIVE
        ):
            raise ValueError("RC search preparation authority must match its backtest scope")
        return context

    return resolve_pinned_context


def create_search_preparation_evidence_resolver(
    persistence: PostgresStrategyLabV2Persistence,
    artifact_root: Path,
    *,
    host_bindings: SearchPreparationHostBindings,
    conformance_resolution: NautilusRcConformanceResolution,
) -> NautilusTrialSearchDispatchEvidenceResolver:
    """Compose local persistence/materialization and enforce the exact RC pin.

    The host context resolver cannot substitute another conformance artifact or
    image. Canonical market metadata remains owned by the provider-platform
    contract and must be supplied by a local adapter implementing that contract.
    """

    if not isinstance(persistence, PostgresStrategyLabV2Persistence):
        raise TypeError("persistence must be a PostgresStrategyLabV2Persistence")
    if not isinstance(artifact_root, Path) or not artifact_root.is_absolute():
        raise ValueError("artifact_root must be an absolute Path")
    if not isinstance(host_bindings, SearchPreparationHostBindings):
        raise TypeError("host_bindings must be SearchPreparationHostBindings")
    if not isinstance(conformance_resolution, NautilusRcConformanceResolution):
        raise TypeError("conformance_resolution must be a NautilusRcConformanceResolution")
    artifact_store = LocalArtifactStore(artifact_root)
    strategy_package_resolver = StrategyPackageArtifactResolver(
        artifact_store,
        runtime_abi=host_bindings.runtime_abi,
    )
    runtime_materializer = NautilusTrialRuntimeInputMaterializer(
        artifact_store=artifact_store,
        strategy_package_resolver=strategy_package_resolver,
        series_decoder=host_bindings.series_decoder,
    )

    return NautilusTrialSearchDispatchEvidenceResolver(
        domain_hydrator=NautilusTrialDomainHydrator(persistence.resources),
        runtime_materializer=runtime_materializer,
        strategy_package_resolver=strategy_package_resolver,
        artifact_store=artifact_store,
        worker_state_reader=persistence.worker_state,
        context_resolver=bind_context_to_rc_evidence(
            host_bindings.context_resolver,
            conformance_resolution=conformance_resolution,
            runtime_abi=host_bindings.runtime_abi,
        ),
    )


__all__ = [
    "SearchPreparationHostBindings",
    "SearchPreparationHostBindingsFactory",
    "BoundPreparationContextResolver",
    "bind_context_to_rc_evidence",
    "create_search_preparation_evidence_resolver",
]
