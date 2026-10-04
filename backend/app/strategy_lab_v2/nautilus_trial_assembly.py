"""Assemble immutable Strategy Lab trial inputs for the isolated Nautilus worker.

This producer validates the shared account shape and each component's pinned
strategy/data identity before publishing a worker artifact. Unsupported
portfolio transforms remain explicit errors rather than being flattened into
a misleading simulation.
Materialization itself does not dispatch a worker or authorize order routing;
allocation/risk integration and authoritative publication remain separate gates.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    AttemptState,
    DataSnapshot,
    EvaluationWindow,
    ExperimentDefinition,
    PortfolioComposition,
    RunAttempt,
    ScientificTrial,
    StrategyPackage,
    StrategyVersion,
)
from app.strategy_lab_v2.event_tape import FrozenEventTape
from app.strategy_lab_v2.event_tape_artifacts import (
    FrozenEventTapeStreamResolution,
    iter_verified_event_tape_stream,
)
from app.strategy_lab_v2.nautilus_engine_input import (
    NautilusComponentStrategyBinding,
    NautilusInstrumentDefinition,
    NautilusVenueDefinition,
    build_nautilus_engine_input,
)
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusEventRecord,
    NautilusEventTape,
    iter_materialized_nautilus_event_records,
    materialize_nautilus_event_tape,
)
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    NautilusRuntimeInputArtifactReference,
    NautilusTrialInputBinding,
    build_nautilus_runtime_bundle,
    materialize_nautilus_component_context_stream_artifact,
    materialize_nautilus_context_stream_artifact,
    materialize_nautilus_native_event_stream_artifact,
    materialize_nautilus_runtime_bundle,
)
from app.strategy_lab_v2.rebalance import (
    RebalanceExecutionPlan,
    SessionCalendarSnapshot,
    compile_rebalance_execution_plan,
)
from app.strategy_lab_v2.replay import iter_event_tape_contexts
from app.strategy_lab_v2.sdk import MarketEvent, StrategySdkManifest
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from strategy_runtime import InvocationContextStreamSource


class NautilusTrialAssemblyError(ValueError):
    """A durable trial cannot be represented by the current Nautilus input contract."""


def _timestamp_ns(value: datetime) -> int:
    normalized = value.astimezone(UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    delta = normalized - epoch
    return (delta.days * 86_400 + delta.seconds) * 1_000_000_000 + delta.microseconds * 1_000


def _in_evaluation_input_window(value: datetime, window: EvaluationWindow | None) -> bool:
    if window is None:
        return True
    lower = window.warmup_start or window.start
    return lower <= value < window.end


@dataclass(frozen=True, slots=True)
class NautilusStrategyRuntimeIdentity:
    """Runtime security/provenance identity for all strategies in one trial."""

    package_fingerprint: str
    source_digest: str
    entrypoint: str
    dependency_digests: tuple[str, ...]
    runtime_abi: str

    def __post_init__(self) -> None:
        require_sha256_digest(self.package_fingerprint, field_name="package_fingerprint")
        require_sha256_digest(self.source_digest, field_name="source_digest")
        if not isinstance(self.entrypoint, str) or not self.entrypoint.strip():
            raise ValueError("entrypoint must not be empty")
        dependencies = tuple(self.dependency_digests)
        for digest in dependencies:
            require_sha256_digest(digest, field_name="dependency_digest")
        if len(dependencies) != len(set(dependencies)):
            raise ValueError("runtime dependency digests must be unique")
        if not isinstance(self.runtime_abi, str) or not self.runtime_abi.strip():
            raise ValueError("runtime_abi must not be empty")
        object.__setattr__(self, "dependency_digests", dependencies)


def strategy_package_set_fingerprint(package_bindings: Mapping[str, str]) -> str:
    """Return the stable identity for one or more experiment-pinned packages."""

    if not isinstance(package_bindings, Mapping) or not package_bindings:
        raise ValueError("strategy package bindings must be a non-empty mapping")
    bindings = tuple(sorted(package_bindings.items()))
    for strategy_fingerprint, package_fingerprint in bindings:
        require_sha256_digest(strategy_fingerprint, field_name="strategy_fingerprint")
        require_sha256_digest(package_fingerprint, field_name="package_fingerprint")
    if len(bindings) == 1:
        return bindings[0][1]
    return content_digest(
        {
            "schema": "strategy-lab.strategy-package-set.v1",
            "bindings": bindings,
        }
    )


def strategy_source_set_digest(strategies: Sequence[StrategyVersion]) -> str:
    """Bind the exact source set embedded in a multi-component runtime bundle."""

    if (
        not isinstance(strategies, Sequence)
        or not strategies
        or any(not isinstance(item, StrategyVersion) for item in strategies)
    ):
        raise ValueError("strategies must be a non-empty sequence of StrategyVersion values")
    sources = tuple(sorted({(item.fingerprint, item.source_digest) for item in strategies}))
    if len(sources) == 1:
        return sources[0][1]
    return content_digest(
        {
            "schema": "strategy-lab.strategy-source-set.v1",
            "sources": sources,
        }
    )


def strategy_runtime_identity(
    strategies: Sequence[StrategyVersion],
    packages: Mapping[str, StrategyPackage],
) -> NautilusStrategyRuntimeIdentity:
    """Derive one exact worker identity from a complete strategy/package set."""

    if (
        not isinstance(strategies, Sequence)
        or not strategies
        or any(not isinstance(item, StrategyVersion) for item in strategies)
    ):
        raise ValueError("strategies must be a non-empty sequence of StrategyVersion values")
    if not isinstance(packages, Mapping) or any(
        not isinstance(item, StrategyPackage) for item in packages.values()
    ):
        raise TypeError("packages must map strategy fingerprints to StrategyPackage values")
    strategies_by_fingerprint = {item.fingerprint: item for item in strategies}
    if len(strategies_by_fingerprint) != len(strategies) or set(packages) != set(
        strategies_by_fingerprint
    ):
        raise ValueError("runtime strategy and package sets must match exactly")
    for strategy_fingerprint, strategy in strategies_by_fingerprint.items():
        package = packages[strategy_fingerprint]
        if package.strategy_fingerprint != strategy_fingerprint:
            raise ValueError("runtime package references a different strategy")
        if package.sdk_version != strategy.sdk_version:
            raise ValueError("runtime package SDK version differs from its strategy")
    bindings = {
        strategy_fingerprint: package.fingerprint
        for strategy_fingerprint, package in packages.items()
    }
    ordered_strategies = tuple(
        strategies_by_fingerprint[fingerprint] for fingerprint in sorted(strategies_by_fingerprint)
    )
    ordered_packages = tuple(packages[strategy.fingerprint] for strategy in ordered_strategies)
    runtime_abis = {package.runtime_abi for package in ordered_packages}
    if len(runtime_abis) != 1:
        raise ValueError("all strategy packages in one Nautilus trial must share a runtime ABI")
    if len(ordered_strategies) == 1:
        dependency_digests = tuple(
            dependency.artifact_digest for dependency in ordered_strategies[0].dependencies
        )
    else:
        dependency_digests = tuple(
            sorted(
                {
                    dependency.artifact_digest
                    for strategy in ordered_strategies
                    for dependency in strategy.dependencies
                }
            )
        )
    return NautilusStrategyRuntimeIdentity(
        package_fingerprint=strategy_package_set_fingerprint(bindings),
        source_digest=strategy_source_set_digest(ordered_strategies),
        entrypoint=ordered_packages[0].entrypoint,
        dependency_digests=dependency_digests,
        runtime_abi=next(iter(runtime_abis)),
    )


@dataclass(frozen=True, slots=True)
class NautilusComponentTrialInput:
    """Resolved immutable strategy package and SDK inputs for one portfolio component."""

    component_id: str
    strategy_package: StrategyPackage
    strategy_manifest: StrategySdkManifest
    strategy_source: str
    max_intents_per_event: int = 100

    def __post_init__(self) -> None:
        if not isinstance(self.component_id, str) or not self.component_id.strip():
            raise ValueError("component_id must not be empty")
        if any(character in self.component_id for character in "\x00\r\n"):
            raise ValueError("component_id must not contain control characters")
        if not isinstance(self.strategy_package, StrategyPackage):
            raise TypeError("strategy_package must be a StrategyPackage")
        if not isinstance(self.strategy_manifest, StrategySdkManifest):
            raise TypeError("strategy_manifest must be a StrategySdkManifest")
        if not isinstance(self.strategy_source, str):
            raise TypeError("strategy_source must be a string")
        if (
            not isinstance(self.max_intents_per_event, int)
            or isinstance(self.max_intents_per_event, bool)
            or self.max_intents_per_event < 1
        ):
            raise ValueError("max_intents_per_event must be a positive integer")


@dataclass(frozen=True, slots=True)
class NautilusTrialRuntimeAssembly:
    """Provenance of a published runtime input, with no strategy source bytes."""

    attempt_id: str
    trial_fingerprint: str
    experiment_fingerprint: str
    portfolio_fingerprint: str
    snapshot_fingerprint: str
    strategy_package_fingerprint: str
    engine_input_fingerprint: str
    invocation_input_digest: str
    runtime_input_artifact: NautilusRuntimeInputArtifactReference

    def __post_init__(self) -> None:
        for name in ("attempt_id",):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        for name in (
            "trial_fingerprint",
            "experiment_fingerprint",
            "portfolio_fingerprint",
            "snapshot_fingerprint",
            "strategy_package_fingerprint",
            "engine_input_fingerprint",
            "invocation_input_digest",
        ):
            require_sha256_digest(getattr(self, name), field_name=name)
        if not isinstance(self.runtime_input_artifact, NautilusRuntimeInputArtifactReference):
            raise TypeError(
                "runtime_input_artifact must be a NautilusRuntimeInputArtifactReference"
            )
        if self.runtime_input_artifact.attempt_id != self.attempt_id:
            raise ValueError("runtime artifact must reference the assembled attempt")
        if (
            self.runtime_input_artifact.trial_binding is not None
            and self.runtime_input_artifact.trial_binding != self.trial_binding
        ):
            raise ValueError("runtime artifact trial binding differs from the assembly")

    @property
    def trial_binding(self) -> NautilusTrialInputBinding:
        """Return the non-circular domain lineage carried by the runtime artifact."""

        return NautilusTrialInputBinding(
            attempt_id=self.attempt_id,
            trial_fingerprint=self.trial_fingerprint,
            experiment_fingerprint=self.experiment_fingerprint,
            portfolio_fingerprint=self.portfolio_fingerprint,
            snapshot_fingerprint=self.snapshot_fingerprint,
            strategy_package_fingerprint=self.strategy_package_fingerprint,
            engine_input_fingerprint=self.engine_input_fingerprint,
            invocation_input_digest=self.invocation_input_digest,
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    @property
    def invocation_batch_digest(self) -> str:
        """Compatibility alias for older callers of the pre-stream assembly."""

        return self.invocation_input_digest


def assemble_nautilus_trial_runtime_input(
    *,
    attempt: RunAttempt,
    trial: ScientificTrial,
    experiment: ExperimentDefinition,
    portfolio: PortfolioComposition,
    snapshot: DataSnapshot,
    event_tape: FrozenEventTape | FrozenEventTapeStreamResolution,
    strategy_package: StrategyPackage | None = None,
    strategy_manifest: StrategySdkManifest,
    strategy_source: str | None = None,
    instruments: Sequence[NautilusInstrumentDefinition],
    venue: NautilusVenueDefinition,
    artifact_store: LocalArtifactStore,
    max_intents_per_event: int = 100,
    component_inputs: Sequence[NautilusComponentTrialInput] | None = None,
    session_calendar: SessionCalendarSnapshot | None = None,
) -> NautilusTrialRuntimeAssembly:
    """Bind one persisted trial's exact inputs and publish its pinned worker bundle.

    The function is pure with respect to domain decisions and performs no
    database, provider, Docker, Redis, or Nautilus I/O. Its only side effect is
    idempotent publication of the verified bundle bytes to ``artifact_store``.
    It does not dispatch a worker or authorize the orders produced by a strategy.
    """

    expected_types = (
        ("attempt", attempt, RunAttempt),
        ("trial", trial, ScientificTrial),
        ("experiment", experiment, ExperimentDefinition),
        ("portfolio", portfolio, PortfolioComposition),
        ("snapshot", snapshot, DataSnapshot),
        ("strategy_manifest", strategy_manifest, StrategySdkManifest),
        ("venue", venue, NautilusVenueDefinition),
        ("artifact_store", artifact_store, LocalArtifactStore),
    )
    for name, value, value_type in expected_types:
        if not isinstance(value, value_type):
            raise TypeError(f"{name} must be a {value_type.__name__}")
    if not isinstance(event_tape, FrozenEventTape | FrozenEventTapeStreamResolution):
        raise TypeError("event_tape must be a FrozenEventTape or FrozenEventTapeStreamResolution")
    if isinstance(event_tape, FrozenEventTapeStreamResolution) and (
        event_tape.snapshot_fingerprint != snapshot.fingerprint
        or event_tape.manifest_fingerprint != strategy_manifest.fingerprint
    ):
        raise NautilusTrialAssemblyError(
            "streamed event tape differs from the frozen snapshot or SDK manifest"
        )
    portfolio_components = {item.component_id: item for item in portfolio.components}
    resolved_component_inputs: tuple[NautilusComponentTrialInput, ...]
    if component_inputs is None:
        if not isinstance(strategy_package, StrategyPackage):
            raise TypeError("strategy_package must be a StrategyPackage")
        if not isinstance(strategy_source, str):
            raise TypeError("strategy_source must be a string")
        if len(portfolio.components) != 1:
            raise NautilusTrialAssemblyError(
                "multi-component runtime assembly requires one resolved input per component"
            )
        component = portfolio.components[0]
        resolved_component_inputs = (
            NautilusComponentTrialInput(
                component_id=component.component_id,
                strategy_package=strategy_package,
                strategy_manifest=strategy_manifest,
                strategy_source=strategy_source,
                max_intents_per_event=max_intents_per_event,
            ),
        )
    else:
        if not isinstance(component_inputs, Sequence) or isinstance(component_inputs, str | bytes):
            raise TypeError("component_inputs must be a sequence of NautilusComponentTrialInput")
        resolved_component_inputs = tuple(component_inputs)
        if not resolved_component_inputs or any(
            not isinstance(item, NautilusComponentTrialInput) for item in resolved_component_inputs
        ):
            raise ValueError("component_inputs must contain typed, non-empty component inputs")
        if strategy_package is not None or strategy_source is not None:
            raise ValueError(
                "component_inputs cannot be combined with the legacy package/source arguments"
            )
    component_ids = [item.component_id for item in resolved_component_inputs]
    if len(component_ids) != len(set(component_ids)):
        raise NautilusTrialAssemblyError("component runtime input ids must be unique")
    if set(component_ids) != set(portfolio_components):
        raise NautilusTrialAssemblyError(
            "component runtime inputs must cover the complete portfolio"
        )
    inputs_by_component = {item.component_id: item for item in resolved_component_inputs}
    if not isinstance(instruments, Sequence) or isinstance(instruments, str | bytes):
        raise TypeError("instruments must be a sequence")
    instrument_definitions = tuple(instruments)
    if not instrument_definitions or any(
        not isinstance(item, NautilusInstrumentDefinition) for item in instrument_definitions
    ):
        raise ValueError("instruments must contain NautilusInstrumentDefinition values")
    if (
        not isinstance(max_intents_per_event, int)
        or isinstance(max_intents_per_event, bool)
        or max_intents_per_event < 1
    ):
        raise ValueError("max_intents_per_event must be a positive integer")

    rebalance_plan: RebalanceExecutionPlan | None = None
    if portfolio.rebalance_policy is not None:
        if not isinstance(session_calendar, SessionCalendarSnapshot):
            raise NautilusTrialAssemblyError(
                "calendar rebalance policy requires a trusted frozen session calendar"
            )
        if trial.evaluation_window is None:
            raise NautilusTrialAssemblyError(
                "calendar rebalance policy requires an explicit trial evaluation window"
            )
        try:
            rebalance_plan = compile_rebalance_execution_plan(
                session_calendar,
                portfolio.rebalance_policy,
                from_session_label=session_calendar.coverage_start,
                through_session_label=session_calendar.coverage_end,
                interval_start=trial.evaluation_window.start,
                interval_end=trial.evaluation_window.end,
            )
        except (TypeError, ValueError) as error:
            raise NautilusTrialAssemblyError(
                "frozen session calendar cannot compile the trial rebalance plan"
            ) from error
    if trial.scenario:
        raise NautilusTrialAssemblyError(
            "Nautilus runtime assembly does not yet apply scenario transforms"
        )
    if attempt.trial_id != trial.trial_id:
        raise NautilusTrialAssemblyError("run attempt references a different scientific trial")
    if attempt.state not in {AttemptState.QUEUED, AttemptState.RUNNING}:
        raise NautilusTrialAssemblyError("terminal run attempts cannot be assembled for execution")
    if trial.experiment_fingerprint != experiment.fingerprint:
        raise NautilusTrialAssemblyError("scientific trial references a different experiment")
    if trial.snapshot_fingerprint != snapshot.fingerprint:
        raise NautilusTrialAssemblyError("scientific trial references a different data snapshot")
    if experiment.portfolio_fingerprint != portfolio.fingerprint:
        raise NautilusTrialAssemblyError("experiment references a different portfolio")
    if experiment.snapshot_fingerprint != snapshot.fingerprint:
        raise NautilusTrialAssemblyError("experiment references a different data snapshot")
    if experiment.capability_contract_digest != snapshot.capability_contract_digest:
        raise NautilusTrialAssemblyError("experiment capability contract differs from the snapshot")
    if trial.preflight_report.fingerprint != snapshot.preflight_report.fingerprint:
        raise NautilusTrialAssemblyError("trial preflight report differs from the snapshot")
    if event_tape.snapshot_fingerprint != snapshot.fingerprint:
        raise NautilusTrialAssemblyError("event tape references a different data snapshot")

    strategy_fingerprints = tuple(
        sorted({component.strategy_fingerprint for component in portfolio.components})
    )
    if experiment.strategy_fingerprints != strategy_fingerprints:
        raise NautilusTrialAssemblyError(
            "experiment strategy set differs from the portfolio component strategies"
        )
    for component_id, component in portfolio_components.items():
        component_input = inputs_by_component[component_id]
        strategy = component_input.strategy_manifest.strategy
        package = component_input.strategy_package
        if strategy.fingerprint != component.strategy_fingerprint:
            raise NautilusTrialAssemblyError(
                f"portfolio component {component_id!r} references a different strategy version"
            )
        if package.strategy_fingerprint != strategy.fingerprint:
            raise NautilusTrialAssemblyError(
                f"component {component_id!r} package references a different strategy version"
            )
        if experiment.strategy_package_fingerprints.get(strategy.fingerprint) != (
            package.fingerprint
        ):
            raise NautilusTrialAssemblyError(
                f"component {component_id!r} package does not match its immutable experiment binding"
            )
        if package.sdk_version != strategy.sdk_version:
            raise NautilusTrialAssemblyError(
                f"component {component_id!r} package SDK version differs from its strategy"
            )
        if content_digest(component_input.strategy_source) != strategy.source_digest:
            raise NautilusTrialAssemblyError(
                f"component {component_id!r} source differs from its immutable digest"
            )

    tape_dependencies = {
        dependency.dependency_id: dependency for dependency in strategy_manifest.data_dependencies
    }
    for component_id, component_input in inputs_by_component.items():
        component_dependencies = {
            dependency.dependency_id: dependency
            for dependency in component_input.strategy_manifest.data_dependencies
        }
        if not component_dependencies or any(
            dependency_id not in tape_dependencies
            or tape_dependencies[dependency_id].requirement != dependency.requirement
            or tape_dependencies[dependency_id].fields != dependency.fields
            for dependency_id, dependency in component_dependencies.items()
        ):
            raise NautilusTrialAssemblyError(
                f"component {component_id!r} dependencies are not covered by the frozen tape binding"
            )
        manifest_instruments = {
            dependency.requirement.instrument_id
            for dependency in component_input.strategy_manifest.data_dependencies
        }
        if not set(portfolio_components[component_id].instrument_ids).issubset(
            manifest_instruments
        ):
            raise NautilusTrialAssemblyError(
                f"component {component_id!r} trades an instrument outside its strategy data scope"
            )

    manifest_instruments = {
        dependency.requirement.instrument_id for dependency in strategy_manifest.data_dependencies
    }
    component_instruments = {
        instrument_id
        for component in portfolio.components
        for instrument_id in component.instrument_ids
    }
    definition_instruments = {item.instrument_id for item in instrument_definitions}
    if not component_instruments.issubset(manifest_instruments):
        raise NautilusTrialAssemblyError(
            "portfolio component instruments are not covered by the frozen tape data scope"
        )
    if definition_instruments != manifest_instruments:
        raise NautilusTrialAssemblyError(
            "native instrument catalog differs from the frozen tape data scope"
        )
    if venue.base_currency != portfolio.base_currency:
        raise NautilusTrialAssemblyError("native account base currency differs from the portfolio")
    if len(venue.cash) != 1 or venue.cash[0].currency != portfolio.base_currency:
        raise NautilusTrialAssemblyError(
            "current runtime assembly supports only the portfolio base-currency cash balance"
        )
    if venue.cash[0].amount != portfolio.initial_capital:
        raise NautilusTrialAssemblyError(
            "native account initial cash differs from portfolio initial capital"
        )

    effective_parameters_by_component: dict[str, dict[str, object]] = {}
    for component_id, component_input in inputs_by_component.items():
        parameters = dict(component_input.strategy_manifest.strategy.default_parameters)
        parameters.update(trial.parameter_set)
        effective_parameters_by_component[component_id] = parameters
    try:
        native_records: Iterable[NautilusEventRecord]
        if isinstance(event_tape, FrozenEventTape):
            native_tape = materialize_nautilus_event_tape(
                event_tape,
                snapshot,
                strategy_manifest,
            )
            if trial.evaluation_window is not None:
                lower = trial.evaluation_window.warmup_start or trial.evaluation_window.start
                lower_ns = _timestamp_ns(lower)
                start_ns = _timestamp_ns(trial.evaluation_window.start)
                end_ns = _timestamp_ns(trial.evaluation_window.end)
                selected_records = tuple(
                    record
                    for record in native_tape.events
                    if lower_ns <= record.event_time_ns < end_ns
                )
                if not any(record.event_time_ns >= start_ns for record in selected_records):
                    raise NautilusTrialAssemblyError(
                        "evaluation window contains no scoring events in the frozen tape"
                    )
                native_tape = NautilusEventTape(
                    native_tape.source_tape_fingerprint,
                    selected_records,
                    native_tape.adapter_version,
                )
            native_records = native_tape.events
            event_count = len(native_tape.events)
        else:
            native_tape = NautilusEventTape(event_tape.tape_fingerprint, ())

            def iter_windowed_native_records() -> Iterable[NautilusEventRecord]:
                records = iter_materialized_nautilus_event_records(
                    event_tape,
                    snapshot,
                    strategy_manifest,
                    artifact_store,
                )
                for record in records:
                    if trial.evaluation_window is None:
                        yield record
                    else:
                        lower = (
                            trial.evaluation_window.warmup_start or trial.evaluation_window.start
                        )
                        event_time = record.event_time_ns
                        if (
                            _timestamp_ns(lower)
                            <= event_time
                            < _timestamp_ns(trial.evaluation_window.end)
                        ):
                            yield record

            if trial.evaluation_window is None:
                event_count = event_tape.event_count
            else:
                event_count = 0
                scoring_event_count = 0
                scoring_start_ns = _timestamp_ns(trial.evaluation_window.start)
                for record in iter_windowed_native_records():
                    event_count += 1
                    if record.event_time_ns >= scoring_start_ns:
                        scoring_event_count += 1
                if scoring_event_count == 0:
                    raise NautilusTrialAssemblyError(
                        "evaluation window contains no scoring events in the frozen tape"
                    )
            native_records = iter_windowed_native_records()
        native_event_stream = materialize_nautilus_native_event_stream_artifact(
            artifact_store,
            events=native_records,
            source_tape_fingerprint=native_tape.source_tape_fingerprint,
            adapter_version=native_tape.adapter_version,
            event_count=event_count,
        )

        def component_events(
            component_input: NautilusComponentTrialInput,
        ) -> Iterable[MarketEvent]:
            source_events = (
                event_tape.events
                if isinstance(event_tape, FrozenEventTape)
                else iter_verified_event_tape_stream(event_tape, artifact_store)
            )
            dependency_ids = {
                dependency.dependency_id
                for dependency in component_input.strategy_manifest.data_dependencies
            }
            return (
                event
                for event in source_events
                if event.dependency_id in dependency_ids
                and _in_evaluation_input_window(event.event_time, trial.evaluation_window)
            )

        if len(inputs_by_component) == 1:
            component_id, component_input = next(iter(sorted(inputs_by_component.items())))
            context_stream = materialize_nautilus_context_stream_artifact(
                artifact_store,
                source=component_input.strategy_source,
                manifest=component_input.strategy_manifest,
                contexts=iter_event_tape_contexts(
                    component_events(component_input),
                    component_input.strategy_manifest,
                    random_seed=trial.seed,
                    parameters=effective_parameters_by_component[component_id],
                ),
                entrypoint=component_input.strategy_package.entrypoint,
                max_intents_per_event=component_input.max_intents_per_event,
            )
        else:
            component_streams = tuple(
                InvocationContextStreamSource(
                    component_id=component_id,
                    source=component_input.strategy_source,
                    manifest=component_input.strategy_manifest,
                    contexts=iter_event_tape_contexts(
                        component_events(component_input),
                        component_input.strategy_manifest,
                        random_seed=trial.seed,
                        parameters=effective_parameters_by_component[component_id],
                    ),
                    entrypoint=component_input.strategy_package.entrypoint,
                    max_intents_per_event=component_input.max_intents_per_event,
                )
                for component_id, component_input in sorted(inputs_by_component.items())
            )
            context_stream = materialize_nautilus_component_context_stream_artifact(
                artifact_store,
                components=component_streams,
            )
        primary_component_id = min(inputs_by_component)
        primary_input = inputs_by_component[primary_component_id]
        primary_parameters = effective_parameters_by_component[primary_component_id]
        strategy_bindings = tuple(
            NautilusComponentStrategyBinding(
                component_id=component_id,
                strategy_fingerprint=component_input.strategy_manifest.strategy.fingerprint,
                strategy_source_digest=component_input.strategy_manifest.strategy.source_digest,
                strategy_manifest_fingerprint=component_input.strategy_manifest.fingerprint,
                entrypoint=component_input.strategy_package.entrypoint,
                parameters_digest=content_digest(effective_parameters_by_component[component_id]),
                max_intents_per_event=component_input.max_intents_per_event,
            )
            for component_id, component_input in sorted(inputs_by_component.items())
        )
        engine_input = build_nautilus_engine_input(
            trial_id=trial.trial_id,
            attempt_id=attempt.attempt_id,
            data_snapshot_fingerprint=snapshot.fingerprint,
            event_tape=native_tape,
            instruments=instrument_definitions,
            venue=venue,
            portfolio=portfolio,
            strategy_source_digest=primary_input.strategy_manifest.strategy.source_digest,
            strategy_manifest_fingerprint=primary_input.strategy_manifest.fingerprint,
            entrypoint=primary_input.strategy_package.entrypoint,
            parameters=primary_parameters,
            random_seed=trial.seed,
            strategy_bindings=strategy_bindings,
            evaluation_window=trial.evaluation_window,
            rebalance_plan=rebalance_plan,
        )
        bundle = build_nautilus_runtime_bundle(
            engine_input,
            context_stream=context_stream,
            native_event_stream=native_event_stream,
        )
        engine_input_fingerprint = content_digest(
            {"engine_input": engine_input.fingerprint, "native_event_stream": native_event_stream}
        )
        package_set_fingerprint = strategy_package_set_fingerprint(
            experiment.strategy_package_fingerprints
        )
        trial_binding = NautilusTrialInputBinding(
            attempt_id=attempt.attempt_id,
            trial_fingerprint=trial.trial_id,
            experiment_fingerprint=experiment.fingerprint,
            portfolio_fingerprint=portfolio.fingerprint,
            snapshot_fingerprint=snapshot.fingerprint,
            strategy_package_fingerprint=package_set_fingerprint,
            engine_input_fingerprint=engine_input_fingerprint,
            invocation_input_digest=context_stream.artifact.content_digest,
        )
        artifact_reference = materialize_nautilus_runtime_bundle(
            bundle,
            artifact_store,
            trial_binding=trial_binding,
        )
    except NautilusTrialAssemblyError:
        raise
    except (TypeError, ValueError) as error:
        raise NautilusTrialAssemblyError(
            "immutable Nautilus trial inputs failed validation"
        ) from error

    return NautilusTrialRuntimeAssembly(
        attempt_id=attempt.attempt_id,
        trial_fingerprint=trial.trial_id,
        experiment_fingerprint=experiment.fingerprint,
        portfolio_fingerprint=portfolio.fingerprint,
        snapshot_fingerprint=snapshot.fingerprint,
        strategy_package_fingerprint=package_set_fingerprint,
        engine_input_fingerprint=engine_input_fingerprint,
        invocation_input_digest=context_stream.artifact.content_digest,
        runtime_input_artifact=artifact_reference,
    )


def assemble_nautilus_trial_runtime_input_from_package(
    *,
    attempt: RunAttempt,
    trial: ScientificTrial,
    experiment: ExperimentDefinition,
    portfolio: PortfolioComposition,
    snapshot: DataSnapshot,
    event_tape: FrozenEventTape | FrozenEventTapeStreamResolution,
    strategy: StrategyVersion,
    strategy_package: StrategyPackage,
    strategy_package_resolver: StrategyPackageArtifactResolver,
    instruments: Sequence[NautilusInstrumentDefinition],
    venue: NautilusVenueDefinition,
    artifact_store: LocalArtifactStore,
    max_intents_per_event: int = 100,
    session_calendar: SessionCalendarSnapshot | None = None,
) -> NautilusTrialRuntimeAssembly:
    """Resolve a pinned strategy package before building its worker input."""

    if not isinstance(strategy_package_resolver, StrategyPackageArtifactResolver):
        raise TypeError("strategy_package_resolver must be a StrategyPackageArtifactResolver")
    if strategy_package_resolver.store is not artifact_store:
        raise ValueError("strategy package and runtime input must share one artifact store")
    resolved_package = strategy_package_resolver.resolve(strategy_package, strategy)
    return assemble_nautilus_trial_runtime_input(
        attempt=attempt,
        trial=trial,
        experiment=experiment,
        portfolio=portfolio,
        snapshot=snapshot,
        event_tape=event_tape,
        strategy_package=strategy_package,
        strategy_manifest=resolved_package.manifest,
        strategy_source=resolved_package.source,
        instruments=instruments,
        venue=venue,
        artifact_store=artifact_store,
        max_intents_per_event=max_intents_per_event,
        session_calendar=session_calendar,
    )


__all__ = [
    "NautilusTrialAssemblyError",
    "NautilusComponentTrialInput",
    "NautilusStrategyRuntimeIdentity",
    "NautilusTrialRuntimeAssembly",
    "strategy_package_set_fingerprint",
    "strategy_source_set_digest",
    "strategy_runtime_identity",
    "assemble_nautilus_trial_runtime_input",
    "assemble_nautilus_trial_runtime_input_from_package",
]
