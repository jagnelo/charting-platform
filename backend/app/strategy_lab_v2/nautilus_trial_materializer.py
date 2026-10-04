"""Resolve a hydrated trial graph into one immutable Nautilus worker input.

The host supplies the owner-hydrated graph, provider-owned series decoder, and
canonical instrument/venue context. This module composes those with verified
content-addressed package and data reads and the existing validated runtime
assembler. It never fetches market data or imports Nautilus.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import StrategyDependency
from app.strategy_lab_v2.event_tape_artifacts import (
    FrozenEventTapeArtifactResolver,
    FrozenSeriesDecoder,
)
from app.strategy_lab_v2.nautilus_engine_input import (
    NautilusInstrumentDefinition,
    NautilusVenueDefinition,
)
from app.strategy_lab_v2.nautilus_trial_assembly import (
    NautilusComponentTrialInput,
    NautilusTrialAssemblyError,
    NautilusTrialRuntimeAssembly,
    assemble_nautilus_trial_runtime_input,
    strategy_runtime_identity,
)
from app.strategy_lab_v2.rebalance import SessionCalendarSnapshot
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile, RuntimeIsolationRequest
from app.strategy_lab_v2.runtime_execution import (
    StrategyRuntimePreflight,
    StrategyRuntimeRequest,
    preflight_strategy_runtime,
)
from app.strategy_lab_v2.sdk import StrategyDataDependency, StrategySdkManifest
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.strategy_validation import (
    StrategySourceValidation,
    combine_strategy_source_validations,
)
from app.strategy_lab_v2.trial_hydration import (
    HydratedNautilusTrial,
)


@dataclass(frozen=True, slots=True)
class NautilusTrialMarketContext:
    """Canonical engine metadata resolved for one snapshot and portfolio."""

    instruments: tuple[NautilusInstrumentDefinition, ...]
    venue: NautilusVenueDefinition
    session_calendar: SessionCalendarSnapshot | None = None
    session_periods_per_year: int | None = None

    def __post_init__(self) -> None:
        instruments = tuple(self.instruments)
        if not instruments or any(
            not isinstance(item, NautilusInstrumentDefinition) for item in instruments
        ):
            raise TypeError("instruments must contain NautilusInstrumentDefinition values")
        if not isinstance(self.venue, NautilusVenueDefinition):
            raise TypeError("venue must be a NautilusVenueDefinition")
        if self.session_calendar is not None and not isinstance(
            self.session_calendar, SessionCalendarSnapshot
        ):
            raise TypeError("session_calendar must be a SessionCalendarSnapshot")
        if self.session_periods_per_year is not None and (
            self.session_calendar is None
            or not isinstance(self.session_periods_per_year, int)
            or isinstance(self.session_periods_per_year, bool)
            or self.session_periods_per_year < 1
        ):
            raise ValueError(
                "session_periods_per_year requires a calendar and must be a positive integer"
            )
        instrument_ids = tuple(item.instrument_id for item in instruments)
        if len(set(instrument_ids)) != len(instrument_ids):
            raise ValueError("market context instrument ids must be unique")
        if any(item.venue_id != self.venue.venue_id for item in instruments):
            raise ValueError("market context instruments must use the resolved venue")
        object.__setattr__(self, "instruments", instruments)


def _build_frozen_tape_manifest(
    graph: HydratedNautilusTrial,
    component_manifests: list[StrategySdkManifest],
) -> StrategySdkManifest:
    """Create the canonical union data binding used to resolve the shared tape."""

    if not component_manifests:
        raise NautilusTrialAssemblyError("trial has no resolved component data manifests")
    dependencies_by_id: dict[str, StrategyDataDependency] = {}
    model_dependencies: set[StrategyDependency] = set()
    for manifest in component_manifests:
        for dependency in manifest.data_dependencies:
            previous = dependencies_by_id.get(dependency.dependency_id)
            if previous is not None and (
                previous.requirement != dependency.requirement
                or previous.fields != dependency.fields
            ):
                raise NautilusTrialAssemblyError(
                    f"strategies reuse data dependency id {dependency.dependency_id!r} with conflicting semantics"
                )
            if previous is None or dependency.lookback_periods > previous.lookback_periods:
                dependencies_by_id[dependency.dependency_id] = dependency
        model_dependencies.update(manifest.model_dependencies)
    primary_strategy = graph.strategies[0]
    return StrategySdkManifest(
        strategy=primary_strategy,
        data_dependencies=tuple(dependencies_by_id.values()),
        model_dependencies=tuple(model_dependencies),
    )


@dataclass(frozen=True, slots=True)
class MaterializedNautilusTrialInput:
    """Owner-hydrated graph and its exact content-addressed runtime bundle."""

    graph: HydratedNautilusTrial
    assembly: NautilusTrialRuntimeAssembly
    source_validation: StrategySourceValidation

    def __post_init__(self) -> None:
        if not isinstance(self.graph, HydratedNautilusTrial):
            raise TypeError("graph must be a HydratedNautilusTrial")
        if not isinstance(self.assembly, NautilusTrialRuntimeAssembly):
            raise TypeError("assembly must be a NautilusTrialRuntimeAssembly")
        if not isinstance(self.source_validation, StrategySourceValidation):
            raise TypeError("source_validation must be a StrategySourceValidation")
        bindings = (
            (self.assembly.attempt_id, self.graph.attempt.attempt_id),
            (self.assembly.trial_fingerprint, self.graph.trial.trial_id),
            (self.assembly.experiment_fingerprint, self.graph.experiment.fingerprint),
            (self.assembly.portfolio_fingerprint, self.graph.portfolio.fingerprint),
            (self.assembly.snapshot_fingerprint, self.graph.snapshot.fingerprint),
        )
        if any(actual != expected for actual, expected in bindings):
            raise ValueError("materialized runtime input differs from the hydrated trial graph")
        if self.assembly.runtime_input_artifact.trial_binding != self.assembly.trial_binding:
            raise ValueError("runtime artifact is missing its exact trial assembly binding")
        identity = strategy_runtime_identity(self.graph.strategies, self.graph.packages)
        if self.assembly.strategy_package_fingerprint != identity.package_fingerprint:
            raise ValueError("materialized runtime package set differs from the experiment")
        if self.source_validation.source_digest != identity.source_digest:
            raise ValueError("materialized source validation differs from the strategy package set")
        if not self.source_validation.accepted:
            raise ValueError("materialized strategy source set did not pass static validation")

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "assembly": self.assembly,
                "domain_graph_fingerprint": self.graph.fingerprint,
                "source_validation": self.source_validation,
            }
        )


@dataclass(frozen=True, slots=True)
class NautilusTrialRuntimeEvidence:
    """Isolation preflight derived from one exact materialized trial input."""

    materialized_input: MaterializedNautilusTrialInput
    runtime_request: StrategyRuntimeRequest
    runtime_preflight: StrategyRuntimePreflight

    def __post_init__(self) -> None:
        if not isinstance(self.materialized_input, MaterializedNautilusTrialInput):
            raise TypeError("materialized_input must be a MaterializedNautilusTrialInput")
        if not isinstance(self.runtime_request, StrategyRuntimeRequest):
            raise TypeError("runtime_request must be a StrategyRuntimeRequest")
        if not isinstance(self.runtime_preflight, StrategyRuntimePreflight):
            raise TypeError("runtime_preflight must be a StrategyRuntimePreflight")
        assembly = self.materialized_input.assembly
        graph = self.materialized_input.graph
        if self.runtime_request.attempt_id != assembly.attempt_id:
            raise ValueError("runtime request must reference the materialized attempt")
        if self.runtime_request.package_fingerprint != assembly.strategy_package_fingerprint:
            raise ValueError("runtime request package differs from the materialized input")
        identity = strategy_runtime_identity(graph.strategies, graph.packages)
        if self.runtime_request.package_fingerprint != identity.package_fingerprint:
            raise ValueError("runtime request package set differs from the hydrated trial graph")
        if self.runtime_request.source_digest != identity.source_digest:
            raise ValueError("runtime request sources differ from the hydrated trial graph")
        if self.runtime_request.entrypoint != identity.entrypoint:
            raise ValueError("runtime request entrypoint differs from the package set")
        if self.runtime_request.isolation_request.dependency_digests != identity.dependency_digests:
            raise ValueError("runtime request dependencies differ from the strategy package set")
        if (
            self.runtime_request.input_bundle_digest
            != assembly.runtime_input_artifact.input_bundle_digest
        ):
            raise ValueError("runtime request bundle differs from the materialized input")
        if self.runtime_preflight.request_fingerprint != self.runtime_request.fingerprint:
            raise ValueError("runtime preflight must reference the derived runtime request")
        if (
            self.runtime_preflight.profile_fingerprint
            != self.runtime_request.runtime_profile_fingerprint
        ):
            raise ValueError("runtime preflight profile differs from the runtime request")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def build_nautilus_trial_runtime_evidence(
    materialized_input: MaterializedNautilusTrialInput,
    runtime_profile: RuntimeIsolationProfile,
    *,
    request_id: str,
    submitted_at: datetime,
) -> NautilusTrialRuntimeEvidence:
    """Derive runtime request and isolation preflight from verified trial bytes.

    This synchronous composition belongs in the dedicated backtest preparation
    process. Its result is suitable for the host's existing atomic search
    dispatch evidence resolver; it must not run inline on an API event loop.
    """

    if not isinstance(materialized_input, MaterializedNautilusTrialInput):
        raise TypeError("materialized_input must be a MaterializedNautilusTrialInput")
    if not isinstance(runtime_profile, RuntimeIsolationProfile):
        raise TypeError("runtime_profile must be a RuntimeIsolationProfile")
    graph = materialized_input.graph
    assembly = materialized_input.assembly
    identity = strategy_runtime_identity(graph.strategies, graph.packages)
    if runtime_profile.runtime_abi != identity.runtime_abi:
        raise ValueError("runtime isolation ABI differs from the pinned strategy package")
    runtime_request = StrategyRuntimeRequest(
        request_id=request_id,
        attempt_id=assembly.attempt_id,
        package_fingerprint=identity.package_fingerprint,
        source_digest=identity.source_digest,
        input_bundle_digest=assembly.runtime_input_artifact.input_bundle_digest,
        runtime_profile_fingerprint=runtime_profile.fingerprint,
        entrypoint=identity.entrypoint,
        isolation_request=RuntimeIsolationRequest(
            attempt_id=assembly.attempt_id,
            dependency_digests=identity.dependency_digests,
        ),
        submitted_at=submitted_at,
    )
    runtime_preflight = preflight_strategy_runtime(runtime_request, runtime_profile)
    return NautilusTrialRuntimeEvidence(
        materialized_input,
        runtime_request,
        runtime_preflight,
    )


class NautilusTrialRuntimeInputMaterializer:
    """Materialize verified package/data bytes for an owner's queued attempt."""

    def __init__(
        self,
        *,
        artifact_store: LocalArtifactStore,
        strategy_package_resolver: StrategyPackageArtifactResolver,
        series_decoder: FrozenSeriesDecoder,
        max_intents_per_event: int = 100,
    ) -> None:
        if not isinstance(artifact_store, LocalArtifactStore):
            raise TypeError("artifact_store must be a LocalArtifactStore")
        if not isinstance(strategy_package_resolver, StrategyPackageArtifactResolver):
            raise TypeError("strategy_package_resolver must be a StrategyPackageArtifactResolver")
        if strategy_package_resolver.store is not artifact_store:
            raise ValueError("strategy package and runtime input must share one artifact store")
        if not callable(getattr(series_decoder, "iter_rows", None)):
            raise TypeError("series_decoder must provide iter_rows(series, source)")
        if (
            not isinstance(max_intents_per_event, int)
            or isinstance(max_intents_per_event, bool)
            or max_intents_per_event < 1
        ):
            raise ValueError("max_intents_per_event must be a positive integer")
        self._artifact_store = artifact_store
        self._strategy_package_resolver = strategy_package_resolver
        self._event_tape_resolver = FrozenEventTapeArtifactResolver(
            artifact_store,
            series_decoder,
        )
        self._max_intents_per_event = max_intents_per_event

    @property
    def artifact_store(self) -> LocalArtifactStore:
        """The content-addressed store shared by package and runtime inputs."""

        return self._artifact_store

    @property
    def strategy_package_resolver(self) -> StrategyPackageArtifactResolver:
        """The exact resolver used to authenticate the trial's source package."""

        return self._strategy_package_resolver

    def materialize(
        self,
        *,
        graph: HydratedNautilusTrial,
        market_context: NautilusTrialMarketContext,
    ) -> MaterializedNautilusTrialInput:
        """Build one bundle from owner-hydrated records and exact adapters.

        Frozen-series decoding and runtime artifact generation are disk-backed,
        blocking operations. Call this from the dedicated backtest preparation
        process, never from an API or worker-heartbeat event loop.
        """

        if not isinstance(graph, HydratedNautilusTrial):
            raise TypeError("graph must be a HydratedNautilusTrial")
        if not isinstance(market_context, NautilusTrialMarketContext):
            raise TypeError("market_context must be a NautilusTrialMarketContext")
        self._require_portfolio_instruments(graph, market_context)
        strategies_by_fingerprint = {item.fingerprint: item for item in graph.strategies}
        resolved_component_inputs: list[NautilusComponentTrialInput] = []
        resolved_manifests: list[StrategySdkManifest] = []
        resolved_validations: dict[str, StrategySourceValidation] = {}
        for component in graph.portfolio.components:
            strategy = strategies_by_fingerprint.get(component.strategy_fingerprint)
            strategy_package = graph.packages.get(component.strategy_fingerprint)
            if strategy is None or strategy_package is None:
                raise NautilusTrialAssemblyError(
                    f"portfolio component {component.component_id!r} has no hydrated strategy package"
                )
            resolved_package = self._strategy_package_resolver.resolve(
                strategy_package,
                strategy,
            )
            resolved_component_inputs.append(
                NautilusComponentTrialInput(
                    component_id=component.component_id,
                    strategy_package=strategy_package,
                    strategy_manifest=resolved_package.manifest,
                    strategy_source=resolved_package.source,
                    max_intents_per_event=self._max_intents_per_event,
                )
            )
            resolved_manifests.append(resolved_package.manifest)
            resolved_validations[strategy.fingerprint] = resolved_package.source_validation
        source_validation = combine_strategy_source_validations(resolved_validations)
        if not source_validation.accepted:
            raise NautilusTrialAssemblyError(
                "one or more strategy sources failed engine-neutral static validation"
            )
        tape_manifest = _build_frozen_tape_manifest(graph, resolved_manifests)
        expected_instruments = {
            dependency.requirement.instrument_id for dependency in tape_manifest.data_dependencies
        }
        observed_instruments = {item.instrument_id for item in market_context.instruments}
        if observed_instruments != expected_instruments:
            raise NautilusTrialAssemblyError(
                "canonical market context must resolve every frozen-tape instrument exactly"
            )
        event_tape = self._event_tape_resolver.resolve(graph.snapshot, tape_manifest)
        assembly = assemble_nautilus_trial_runtime_input(
            attempt=graph.attempt,
            trial=graph.trial,
            experiment=graph.experiment,
            portfolio=graph.portfolio,
            snapshot=graph.snapshot,
            event_tape=event_tape,
            strategy_manifest=tape_manifest,
            instruments=market_context.instruments,
            venue=market_context.venue,
            artifact_store=self._artifact_store,
            max_intents_per_event=self._max_intents_per_event,
            component_inputs=tuple(resolved_component_inputs),
            session_calendar=market_context.session_calendar,
            session_periods_per_year=market_context.session_periods_per_year,
        )
        return MaterializedNautilusTrialInput(graph, assembly, source_validation)

    @staticmethod
    def _require_portfolio_instruments(
        graph: HydratedNautilusTrial,
        market_context: NautilusTrialMarketContext,
    ) -> None:
        expected = {
            instrument_id
            for component in graph.portfolio.components
            for instrument_id in component.instrument_ids
        }
        observed = {item.instrument_id for item in market_context.instruments}
        if not expected.issubset(observed):
            raise NautilusTrialAssemblyError(
                "canonical market context must resolve every portfolio instrument"
            )


__all__ = [
    "MaterializedNautilusTrialInput",
    "NautilusTrialRuntimeEvidence",
    "NautilusTrialMarketContext",
    "NautilusTrialRuntimeInputMaterializer",
    "build_nautilus_trial_runtime_evidence",
]
