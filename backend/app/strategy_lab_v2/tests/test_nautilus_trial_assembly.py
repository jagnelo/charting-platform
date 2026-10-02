from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO

import pytest

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    preflight_capabilities,
)
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    AttemptState,
    DataSeriesManifest,
    DataSnapshot,
    EvaluationWindow,
    EventGranularity,
    ExperimentDefinition,
    PortfolioComponent,
    PortfolioComposition,
    ProductClass,
    RunAttempt,
    ScientificTrial,
    StrategyPackage,
    StrategyPackageFormat,
    StrategyVersion,
)
from app.strategy_lab_v2.event_tape import FrozenEventTape
from app.strategy_lab_v2.nautilus_engine_input import (
    NautilusCashDefinition,
    NautilusInstrumentDefinition,
    NautilusVenueDefinition,
)
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    load_materialized_nautilus_runtime_bundle,
)
from app.strategy_lab_v2.nautilus_trial_assembly import (
    NautilusTrialAssemblyError,
    assemble_nautilus_trial_runtime_input,
)
from app.strategy_lab_v2.sdk import MarketEvent, StrategyDataDependency, StrategySdkManifest
from strategy_runtime import deserialize_invocation_context_stream

BASE = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
SOURCE = "class Strategy:\n    def on_event(self, context):\n        return []\n"
FIELDS = ("open", "high", "low", "close", "volume")


def _inputs(*, scenario=None, evaluation_window=None):
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=BASE - timedelta(days=1),
        end=BASE + timedelta(days=3),
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="regular",
        feed="consolidated",
        execution_model="bar-close-v1",
        account_model="cash-equity-v1",
        corporate_action_semantics="split-adjusted-v1",
    )
    cell = CapabilityCell(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularities=frozenset({EventGranularity.BAR}),
        event_types=frozenset({"ohlcv"}),
        timeframes=frozenset({"1d"}),
        adjustments=frozenset({AdjustmentMode.SPLIT_ADJUSTED}),
        sessions=frozenset({"regular"}),
        feeds=frozenset({"consolidated"}),
        execution_models=frozenset({"bar-close-v1"}),
        account_models=frozenset({"cash-equity-v1"}),
        corporate_action_semantics=frozenset({"split-adjusted-v1"}),
        history_start=BASE - timedelta(days=2),
        history_end=BASE + timedelta(days=4),
        evidence_digest=content_digest("capability-evidence"),
    )
    report = preflight_capabilities((requirement,), (cell,))
    snapshot = DataSnapshot(
        "snapshot-1",
        "provider-snapshot-1",
        report,
        (
            DataSeriesManifest(
                instrument_id="US.AAPL",
                event_type="ohlcv",
                event_granularity=EventGranularity.BAR,
                timeframe="1d",
                session="regular",
                feed="consolidated",
                start=requirement.start,
                end=requirement.end,
                adjustment=AdjustmentMode.SPLIT_ADJUSTED,
                corporate_action_semantics="split-adjusted-v1",
                coverage_evidence_digest=content_digest("coverage-evidence"),
                content_digest=content_digest("daily-bars"),
                row_count=2,
            ),
        ),
        BASE,
    )
    strategy = StrategyVersion(
        "strategy-1",
        "v1",
        "2.0.0",
        content_digest(SOURCE),
        parameter_schema={"window": {"type": "integer", "minimum": 1}},
        default_parameters={"window": 20},
    )
    manifest = StrategySdkManifest(
        strategy,
        (StrategyDataDependency("daily-bars", requirement, FIELDS, lookback_periods=2),),
    )
    event_tape = FrozenEventTape(
        snapshot.fingerprint,
        tuple(
            MarketEvent(
                "daily-bars",
                f"bar-{sequence}",
                "US.AAPL",
                BASE + timedelta(days=sequence - 1),
                sequence,
                {
                    "open": Decimal("100") + sequence,
                    "high": Decimal("102") + sequence,
                    "low": Decimal("99") + sequence,
                    "close": Decimal("101") + sequence,
                    "volume": Decimal("100000"),
                },
            )
            for sequence in (1, 2)
        ),
    )
    component = PortfolioComponent("component-1", strategy.fingerprint, ("US.AAPL",), Decimal("1"))
    portfolio = PortfolioComposition(
        "portfolio-1",
        "v1",
        Decimal("100000"),
        "USD",
        (component,),
    )
    package = StrategyPackage(
        "package-1",
        strategy.fingerprint,
        StrategyPackageFormat.SOURCE_ARCHIVE,
        content_digest("archive"),
        content_digest("manifest"),
        content_digest("dependency-lock"),
        128,
        "strategy.main:Strategy",
        strategy.sdk_version,
        "cp312-linux-x86_64",
    )
    experiment = ExperimentDefinition(
        "experiment-1",
        portfolio.fingerprint,
        (strategy.fingerprint,),
        snapshot.fingerprint,
        snapshot.capability_contract_digest,
        7,
        "metrics-v1",
        strategy_package_fingerprints={strategy.fingerprint: package.fingerprint},
    )
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=snapshot.fingerprint,
        preflight_report=report,
        parameter_set={"window": 20},
        scenario=scenario,
        seed=13,
        evaluation_window=evaluation_window,
    )
    attempt = RunAttempt("attempt-1", trial.trial_id, 1, AttemptState.QUEUED, BASE)
    instrument = NautilusInstrumentDefinition(
        "US.AAPL",
        "AAPL",
        "SIM",
        ProductClass.EQUITY,
        "USD",
        2,
        0,
        Decimal("0.01"),
        Decimal("1"),
        bar_type="AAPL.SIM-1-DAY-LAST",
    )
    venue = NautilusVenueDefinition(
        "SIM",
        "netting",
        "cash",
        (NautilusCashDefinition("USD", Decimal("100000")),),
        "USD",
    )
    return {
        "attempt": attempt,
        "trial": trial,
        "experiment": experiment,
        "portfolio": portfolio,
        "snapshot": snapshot,
        "event_tape": event_tape,
        "strategy_package": package,
        "strategy_manifest": manifest,
        "strategy_source": SOURCE,
        "instruments": (instrument,),
        "venue": venue,
    }


def test_trial_assembly_materializes_reproducible_pinned_bundle(tmp_path) -> None:
    values = _inputs()
    store = LocalArtifactStore(tmp_path / "artifacts")

    assembly = assemble_nautilus_trial_runtime_input(
        **values,
        artifact_store=store,
    )
    bundle = load_materialized_nautilus_runtime_bundle(
        assembly.runtime_input_artifact,
        store,
        max_input_bytes=1_000_000,
    )
    assert bundle.context_stream is not None
    source, manifest, decoded_contexts, entrypoint, max_intents = (
        deserialize_invocation_context_stream(
            BytesIO(store.read(bundle.context_stream.artifact.storage_key)),
            expected_context_count=bundle.context_stream.context_count,
        )
    )
    contexts = tuple(decoded_contexts)

    assert assembly.runtime_input_artifact.attempt_id == values["attempt"].attempt_id
    assert assembly.trial_fingerprint == values["trial"].trial_id
    assert assembly.portfolio_fingerprint == values["portfolio"].fingerprint
    assert bundle.input_bundle_digest == assembly.runtime_input_artifact.input_bundle_digest
    assert bundle.attempt_id == values["attempt"].attempt_id
    assert source == SOURCE
    assert manifest == values["strategy_manifest"]
    assert len(contexts) == 2
    assert entrypoint == "strategy.main:Strategy"
    assert max_intents == 100


def test_trial_assembly_applies_immutable_strategy_defaults(tmp_path) -> None:
    values = _inputs()
    prior_trial = values["trial"]
    trial = ScientificTrial.create(
        experiment_fingerprint=prior_trial.experiment_fingerprint,
        snapshot_fingerprint=prior_trial.snapshot_fingerprint,
        preflight_report=prior_trial.preflight_report,
        parameter_set={},
        seed=prior_trial.seed,
    )
    values["trial"] = trial
    values["attempt"] = replace(values["attempt"], trial_id=trial.trial_id)
    store = LocalArtifactStore(tmp_path / "artifacts")

    assembly = assemble_nautilus_trial_runtime_input(
        **values,
        artifact_store=store,
    )
    bundle = load_materialized_nautilus_runtime_bundle(
        assembly.runtime_input_artifact,
        store,
        max_input_bytes=1_000_000,
    )
    assert bundle.context_stream is not None
    _source, _manifest, contexts, _entrypoint, _max_intents = deserialize_invocation_context_stream(
        BytesIO(store.read(bundle.context_stream.artifact.storage_key)),
        expected_context_count=bundle.context_stream.context_count,
    )

    assert all(context.parameters == {"window": 20} for context in contexts)


def test_trial_assembly_rejects_cross_attempt_and_wrong_source(tmp_path) -> None:
    values = _inputs()
    values["attempt"] = replace(values["attempt"], trial_id=content_digest("another trial"))
    with pytest.raises(NautilusTrialAssemblyError, match="different scientific trial"):
        assemble_nautilus_trial_runtime_input(
            **values,
            artifact_store=LocalArtifactStore(tmp_path / "attempt-artifacts"),
        )

    values = _inputs()
    values["strategy_source"] = SOURCE + "# drift\n"
    with pytest.raises(NautilusTrialAssemblyError, match="immutable digest"):
        assemble_nautilus_trial_runtime_input(
            **values,
            artifact_store=LocalArtifactStore(tmp_path / "source-artifacts"),
        )


def test_trial_assembly_rejects_a_package_not_pinned_by_the_experiment(tmp_path) -> None:
    values = _inputs()
    values["strategy_package"] = replace(
        values["strategy_package"],
        archive_digest=content_digest("different-strategy-package"),
    )

    with pytest.raises(NautilusTrialAssemblyError, match="immutable experiment binding"):
        assemble_nautilus_trial_runtime_input(
            **values,
            artifact_store=LocalArtifactStore(tmp_path / "package-artifacts"),
        )


def test_trial_assembly_rejects_an_executable_experiment_without_package_binding(tmp_path) -> None:
    values = _inputs()
    experiment = replace(values["experiment"], strategy_package_fingerprints={})
    prior_trial = values["trial"]
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=prior_trial.snapshot_fingerprint,
        preflight_report=prior_trial.preflight_report,
        parameter_set=prior_trial.parameter_set,
        scenario=prior_trial.scenario,
        seed=prior_trial.seed,
        randomization=prior_trial.randomization,
        evaluation_window=prior_trial.evaluation_window,
    )
    values["experiment"] = experiment
    values["trial"] = trial
    values["attempt"] = replace(values["attempt"], trial_id=trial.trial_id)

    with pytest.raises(NautilusTrialAssemblyError, match="immutable experiment binding"):
        assemble_nautilus_trial_runtime_input(
            **values,
            artifact_store=LocalArtifactStore(tmp_path / "unbound-package-artifacts"),
        )


@pytest.mark.parametrize(
    ("trial_overrides", "message"),
    [
        ({"scenario": {"volatility_scale": 2}}, "scenario transforms"),
        (
            {"evaluation_window": EvaluationWindow(BASE, BASE + timedelta(days=1), "test")},
            "evaluation windows",
        ),
    ],
)
def test_trial_assembly_rejects_unapplied_scenario_and_evaluation_window(
    tmp_path, trial_overrides, message
) -> None:
    values = _inputs(**trial_overrides)

    with pytest.raises(NautilusTrialAssemblyError, match=message):
        assemble_nautilus_trial_runtime_input(
            **values,
            artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        )


def test_trial_assembly_fails_closed_for_multi_component_portfolios(tmp_path) -> None:
    values = _inputs()
    portfolio = values["portfolio"]
    component = portfolio.components[0]
    values["portfolio"] = PortfolioComposition(
        portfolio.portfolio_id,
        portfolio.version_id,
        portfolio.initial_capital,
        portfolio.base_currency,
        (
            replace(component, component_id="component-1a", capital_weight=Decimal("0.5")),
            replace(component, component_id="component-1b", capital_weight=Decimal("0.5")),
        ),
    )

    with pytest.raises(NautilusTrialAssemblyError, match="exactly one portfolio component"):
        assemble_nautilus_trial_runtime_input(
            **values,
            artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        )
