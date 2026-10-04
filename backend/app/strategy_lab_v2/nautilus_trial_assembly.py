"""Assemble immutable Strategy Lab trial inputs for the isolated Nautilus worker.

This producer deliberately implements only the account shape the current
native bridge can execute correctly: one fully funded strategy component,
without an evaluation cut or scenario transform. It validates that narrow
engine capability against the complete domain records before publishing any
worker artifact. Unsupported portfolio shapes remain explicit errors rather
than being flattened into a misleading single-strategy simulation.
Materialization itself does not dispatch a worker or authorize order routing;
allocation/risk integration and authoritative publication remain separate gates.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    AttemptState,
    DataSnapshot,
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
    materialize_nautilus_context_stream_artifact,
    materialize_nautilus_native_event_stream_artifact,
    materialize_nautilus_runtime_bundle,
)
from app.strategy_lab_v2.replay import iter_event_tape_contexts
from app.strategy_lab_v2.sdk import MarketEvent, StrategySdkManifest
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver


class NautilusTrialAssemblyError(ValueError):
    """A durable trial cannot be represented by the current Nautilus input contract."""


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
    strategy_package: StrategyPackage,
    strategy_manifest: StrategySdkManifest,
    strategy_source: str,
    instruments: Sequence[NautilusInstrumentDefinition],
    venue: NautilusVenueDefinition,
    artifact_store: LocalArtifactStore,
    max_intents_per_event: int = 100,
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
        ("strategy_package", strategy_package, StrategyPackage),
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
    if not isinstance(strategy_source, str):
        raise TypeError("strategy_source must be a string")
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

    # Do not pretend that the current single-strategy bridge is a portfolio
    # execution layer. Multi-component portfolios are rejected before artifact
    # publication until component attribution and the shared risk route are
    # implemented in the native callback path.
    if len(portfolio.components) != 1:
        raise NautilusTrialAssemblyError(
            "current Nautilus runtime assembly requires exactly one portfolio component"
        )
    component = portfolio.components[0]
    if component.capital_weight != Decimal(1):
        raise NautilusTrialAssemblyError(
            "current Nautilus runtime assembly requires a fully funded portfolio component"
        )
    if portfolio.rebalance_policy is not None:
        raise NautilusTrialAssemblyError(
            "Nautilus runtime assembly does not yet apply portfolio rebalance schedules"
        )
    if trial.scenario:
        raise NautilusTrialAssemblyError(
            "Nautilus runtime assembly does not yet apply scenario transforms"
        )
    if trial.evaluation_window is not None:
        raise NautilusTrialAssemblyError(
            "Nautilus runtime assembly does not yet gate warm-up and evaluation windows"
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

    strategy = strategy_manifest.strategy
    if strategy.fingerprint != component.strategy_fingerprint:
        raise NautilusTrialAssemblyError(
            "portfolio component references a different strategy version"
        )
    if experiment.strategy_fingerprints != (strategy.fingerprint,):
        raise NautilusTrialAssemblyError(
            "experiment strategy set differs from the supported portfolio component"
        )
    if strategy_package.strategy_fingerprint != strategy.fingerprint:
        raise NautilusTrialAssemblyError("strategy package references a different strategy version")
    if experiment.strategy_package_fingerprints.get(strategy.fingerprint) != (
        strategy_package.fingerprint
    ):
        raise NautilusTrialAssemblyError(
            "strategy package does not match its immutable experiment binding"
        )
    if strategy_package.sdk_version != strategy.sdk_version:
        raise NautilusTrialAssemblyError("strategy package SDK version differs from its strategy")
    if content_digest(strategy_source) != strategy.source_digest:
        raise NautilusTrialAssemblyError(
            "resolved strategy source differs from its immutable digest"
        )

    component_instruments = set(component.instrument_ids)
    manifest_instruments = {
        dependency.requirement.instrument_id for dependency in strategy_manifest.data_dependencies
    }
    definition_instruments = {item.instrument_id for item in instrument_definitions}
    if manifest_instruments != component_instruments:
        raise NautilusTrialAssemblyError(
            "strategy data instruments differ from the portfolio component scope"
        )
    if definition_instruments != component_instruments:
        raise NautilusTrialAssemblyError(
            "native instrument catalog differs from the portfolio component scope"
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

    effective_parameters = dict(strategy.default_parameters)
    effective_parameters.update(trial.parameter_set)
    try:
        native_records: Iterable[NautilusEventRecord]
        context_events: Iterable[MarketEvent]
        if isinstance(event_tape, FrozenEventTape):
            native_tape = materialize_nautilus_event_tape(
                event_tape,
                snapshot,
                strategy_manifest,
            )
            native_records = native_tape.events
            event_count = len(native_tape.events)
            context_events = event_tape.events
        else:
            native_tape = NautilusEventTape(event_tape.tape_fingerprint, ())
            native_records = iter_materialized_nautilus_event_records(
                event_tape,
                snapshot,
                strategy_manifest,
                artifact_store,
            )
            event_count = event_tape.event_count
            context_events = iter_verified_event_tape_stream(event_tape, artifact_store)
        native_event_stream = materialize_nautilus_native_event_stream_artifact(
            artifact_store,
            events=native_records,
            source_tape_fingerprint=native_tape.source_tape_fingerprint,
            adapter_version=native_tape.adapter_version,
            event_count=event_count,
        )
        contexts = iter_event_tape_contexts(
            context_events,
            strategy_manifest,
            random_seed=trial.seed,
            parameters=effective_parameters,
        )
        context_stream = materialize_nautilus_context_stream_artifact(
            artifact_store,
            source=strategy_source,
            manifest=strategy_manifest,
            contexts=contexts,
            entrypoint=strategy_package.entrypoint,
            max_intents_per_event=max_intents_per_event,
        )
        engine_input = build_nautilus_engine_input(
            trial_id=trial.trial_id,
            attempt_id=attempt.attempt_id,
            data_snapshot_fingerprint=snapshot.fingerprint,
            event_tape=native_tape,
            instruments=instrument_definitions,
            venue=venue,
            portfolio=portfolio,
            strategy_source_digest=strategy.source_digest,
            strategy_manifest_fingerprint=strategy_manifest.fingerprint,
            entrypoint=strategy_package.entrypoint,
            parameters=effective_parameters,
            random_seed=trial.seed,
        )
        bundle = build_nautilus_runtime_bundle(
            engine_input,
            context_stream=context_stream,
            native_event_stream=native_event_stream,
        )
        engine_input_fingerprint = content_digest(
            {"engine_input": engine_input.fingerprint, "native_event_stream": native_event_stream}
        )
        trial_binding = NautilusTrialInputBinding(
            attempt_id=attempt.attempt_id,
            trial_fingerprint=trial.trial_id,
            experiment_fingerprint=experiment.fingerprint,
            portfolio_fingerprint=portfolio.fingerprint,
            snapshot_fingerprint=snapshot.fingerprint,
            strategy_package_fingerprint=strategy_package.fingerprint,
            engine_input_fingerprint=engine_input_fingerprint,
            invocation_input_digest=context_stream.artifact.content_digest,
        )
        artifact_reference = materialize_nautilus_runtime_bundle(
            bundle,
            artifact_store,
            trial_binding=trial_binding,
        )
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
        strategy_package_fingerprint=strategy_package.fingerprint,
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
    )


__all__ = [
    "NautilusTrialAssemblyError",
    "NautilusTrialRuntimeAssembly",
    "assemble_nautilus_trial_runtime_input",
    "assemble_nautilus_trial_runtime_input_from_package",
]
