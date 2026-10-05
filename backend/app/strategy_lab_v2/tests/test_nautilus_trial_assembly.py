from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import BinaryIO

import pytest

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.capabilities import (
    CapabilityCell,
    CapabilityRequirement,
    preflight_capabilities,
)
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    ArtifactManifest,
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
from app.strategy_lab_v2.event_tape_artifacts import (
    FrozenEventTapeArtifactResolver,
    FrozenEventTapeStreamResolution,
    FrozenSeriesRow,
)
from app.strategy_lab_v2.nautilus_engine_input import (
    NautilusCashDefinition,
    NautilusInstrumentDefinition,
    NautilusVenueDefinition,
)
from app.strategy_lab_v2.nautilus_native_event_stream import (
    deserialize_nautilus_native_event_stream,
)
from app.strategy_lab_v2.nautilus_rebalance_wire import rebalance_execution_plan_from_wire
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    load_materialized_nautilus_runtime_bundle,
)
from app.strategy_lab_v2.nautilus_trial_assembly import (
    NautilusComponentTrialInput,
    NautilusTrialAssemblyError,
    assemble_nautilus_trial_runtime_input,
    strategy_package_set_fingerprint,
)
from app.strategy_lab_v2.rebalance import (
    CalendarDay,
    CalendarDayStatus,
    CalendarRebalancePolicy,
    RebalanceCadence,
    RebalanceTrigger,
    SessionCalendarSnapshot,
    SessionSegment,
    TradingSession,
)
from app.strategy_lab_v2.sdk import MarketEvent, StrategyDataDependency, StrategySdkManifest
from strategy_runtime import (
    deserialize_component_invocation_context_stream,
    deserialize_invocation_context_stream,
)

BASE = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
SOURCE = "class Strategy:\n    def on_event(self, context):\n        return []\n"
FIELDS = ("open", "high", "low", "close", "volume")


class JsonFrozenSeriesDecoder:
    """Test decoder for the provider-owned snapshot series boundary."""

    def iter_rows(
        self,
        series: DataSeriesManifest,
        source: BinaryIO,
    ) -> Iterable[FrozenSeriesRow]:
        del series
        for row in json.load(source):
            yield FrozenSeriesRow(
                event_id=row["event_id"],
                event_time=datetime.fromisoformat(row["event_time"]),
                sequence=row["sequence"],
                values=row["values"],
            )


def _inputs(*, scenario=None, evaluation_window=None):
    requirement = CapabilityRequirement(
        instrument_id="AAPL.SIM",
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
        instrument_id="AAPL.SIM",
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
                instrument_id="AAPL.SIM",
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
                "AAPL.SIM",
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
    component = PortfolioComponent("component-1", strategy.fingerprint, ("AAPL.SIM",), Decimal("1"))
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
        "AAPL.SIM",
        "AAPL",
        "SIM",
        ProductClass.EQUITY,
        "USD",
        2,
        0,
        Decimal("0.01"),
        Decimal("1"),
        bar_type="AAPL.SIM-1-DAY-LAST-EXTERNAL",
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


def _calendar_snapshot() -> SessionCalendarSnapshot:
    first = BASE.date() - timedelta(days=1)
    last = BASE.date() + timedelta(days=3)
    days: list[CalendarDay] = []
    label = first
    while label <= last:
        if label.weekday() < 5:
            opening = datetime(label.year, label.month, label.day, 14, 30, tzinfo=UTC)
            closing = datetime(label.year, label.month, label.day, 21, 0, tzinfo=UTC)
            session = TradingSession(
                f"session-{label.isoformat()}",
                label,
                (SessionSegment(opening, closing),),
            )
            days.append(CalendarDay(label, CalendarDayStatus.TRADING, session))
        else:
            days.append(CalendarDay(label, CalendarDayStatus.CLOSED))
        label += timedelta(days=1)
    return SessionCalendarSnapshot(
        calendar_id="TEST-UTC",
        definition_version="test-calendar-v1",
        timezone_name="UTC",
        timezone_database_version="test-fixed-utc",
        coverage_start=first,
        coverage_end=last,
        days=tuple(days),
        source_evidence_digest=content_digest("test-session-calendar"),
    )


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
    native_event_stream = assembly.runtime_input_artifact.native_event_stream
    assert native_event_stream is not None
    bundle_payload = json.loads(bundle.wire_bytes)
    assert "events" not in bundle_payload["engine_input"]["event_tape"]
    assert bundle_payload["engine_input"]["event_tape"]["event_count"] == 2
    events = tuple(
        deserialize_nautilus_native_event_stream(
            BytesIO(store.read(native_event_stream.artifact.storage_key)),
            expected_source_tape_fingerprint=native_event_stream.source_tape_fingerprint,
            expected_adapter_version=native_event_stream.adapter_version,
            expected_event_count=native_event_stream.event_count,
        )
    )
    assert [event["sequence"] for event in events] == [1, 2]


def test_trial_assembly_freezes_rebalance_plan_to_evaluation_window(tmp_path) -> None:
    values = _inputs(
        evaluation_window=EvaluationWindow(
            start=BASE + timedelta(days=1),
            end=BASE + timedelta(days=2),
            purpose="out_of_sample",
            warmup_start=BASE,
        )
    )
    calendar = _calendar_snapshot()
    policy = CalendarRebalancePolicy(
        calendar_id=calendar.calendar_id,
        calendar_fingerprint=calendar.fingerprint,
        cadence=RebalanceCadence.EACH_SESSION,
        trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
    )
    portfolio = replace(values["portfolio"], rebalance_policy=policy)
    experiment = replace(values["experiment"], portfolio_fingerprint=portfolio.fingerprint)
    previous_trial = values["trial"]
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=previous_trial.snapshot_fingerprint,
        preflight_report=previous_trial.preflight_report,
        parameter_set=previous_trial.parameter_set,
        scenario=previous_trial.scenario,
        seed=previous_trial.seed,
        randomization=previous_trial.randomization,
        evaluation_window=previous_trial.evaluation_window,
    )
    values.update(
        portfolio=portfolio,
        experiment=experiment,
        trial=trial,
        attempt=replace(values["attempt"], trial_id=trial.trial_id),
    )
    store = LocalArtifactStore(tmp_path / "artifacts")

    assembly = assemble_nautilus_trial_runtime_input(
        **values,
        artifact_store=store,
        session_calendar=calendar,
        session_periods_per_year=252,
    )
    bundle = load_materialized_nautilus_runtime_bundle(
        assembly.runtime_input_artifact,
        store,
        max_input_bytes=1_000_000,
    )
    engine_input = json.loads(bundle.wire_bytes)["engine_input"]

    assert len(engine_input["rebalance_plan"]["occurrences"]) == 1
    assert engine_input["rebalance_plan"]["calendar_fingerprint"] == calendar.fingerprint
    decoded_plan = rebalance_execution_plan_from_wire(engine_input["rebalance_plan"])
    assert decoded_plan is not None
    assert decoded_plan.occurrences[0].event_time == BASE + timedelta(days=1)
    assert bundle.session_calendar == calendar
    assert bundle.session_periods_per_year == 252


def test_trial_assembly_rejects_rebalance_without_trusted_calendar(tmp_path) -> None:
    values = _inputs(
        evaluation_window=EvaluationWindow(
            start=BASE,
            end=BASE + timedelta(days=1),
            purpose="out_of_sample",
        )
    )
    calendar = _calendar_snapshot()
    policy = CalendarRebalancePolicy(
        calendar_id=calendar.calendar_id,
        calendar_fingerprint=calendar.fingerprint,
        cadence=RebalanceCadence.EACH_SESSION,
        trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
    )
    portfolio = replace(values["portfolio"], rebalance_policy=policy)
    experiment = replace(values["experiment"], portfolio_fingerprint=portfolio.fingerprint)
    previous_trial = values["trial"]
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=previous_trial.snapshot_fingerprint,
        preflight_report=previous_trial.preflight_report,
        parameter_set=previous_trial.parameter_set,
        scenario=previous_trial.scenario,
        seed=previous_trial.seed,
        randomization=previous_trial.randomization,
        evaluation_window=previous_trial.evaluation_window,
    )
    values.update(
        portfolio=portfolio,
        experiment=experiment,
        trial=trial,
        attempt=replace(values["attempt"], trial_id=trial.trial_id),
    )

    with pytest.raises(NautilusTrialAssemblyError, match="trusted frozen session calendar"):
        assemble_nautilus_trial_runtime_input(
            **values,
            artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        )


def test_trial_assembly_consumes_default_disk_spooled_event_tape(tmp_path) -> None:
    values = _inputs(
        evaluation_window=EvaluationWindow(
            start=BASE + timedelta(days=1),
            end=BASE + timedelta(days=3),
            purpose="out_of_sample",
            warmup_start=BASE + timedelta(hours=12),
        )
    )
    source_events = values["event_tape"].events
    source_rows = [
        {
            "event_id": event.event_id,
            "event_time": event.event_time.isoformat(),
            "sequence": event.sequence,
            "values": {name: str(value) for name, value in event.values.items()},
        }
        for event in source_events
    ]
    source_payload = json.dumps(source_rows, separators=(",", ":"), sort_keys=True).encode()
    old_snapshot = values["snapshot"]
    series = replace(
        old_snapshot.series[0],
        content_digest=artifact_content_digest(source_payload),
    )
    snapshot = replace(old_snapshot, series=(series,))
    store = LocalArtifactStore(tmp_path / "artifacts")
    store.publish(
        ArtifactManifest(
            content_digest=series.content_digest,
            byte_length=len(source_payload),
            media_type="application/vnd.apache.parquet",
            schema_version="provider.market-series.v1",
            storage_key=series.content_digest,
        ),
        source_payload,
    )

    resolution = FrozenEventTapeArtifactResolver(store, JsonFrozenSeriesDecoder()).resolve(
        snapshot,
        values["strategy_manifest"],
    )
    assert isinstance(resolution, FrozenEventTapeStreamResolution)
    assert not hasattr(resolution, "tape")

    old_experiment = values["experiment"]
    experiment = replace(old_experiment, snapshot_fingerprint=snapshot.fingerprint)
    old_trial = values["trial"]
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=snapshot.fingerprint,
        preflight_report=old_trial.preflight_report,
        parameter_set=old_trial.parameter_set,
        scenario=old_trial.scenario,
        seed=old_trial.seed,
        randomization=old_trial.randomization,
        evaluation_window=old_trial.evaluation_window,
    )
    values.update(
        snapshot=snapshot,
        event_tape=resolution,
        experiment=experiment,
        trial=trial,
        attempt=replace(values["attempt"], trial_id=trial.trial_id),
    )

    assembly = assemble_nautilus_trial_runtime_input(
        **values,
        artifact_store=store,
    )
    bundle = load_materialized_nautilus_runtime_bundle(
        assembly.runtime_input_artifact,
        store,
        max_input_bytes=1_000_000,
    )
    assert bundle.native_event_stream is not None
    payload = json.loads(bundle.wire_bytes)
    assert set(payload["engine_input"]["event_tape"]) == {
        "source_tape_fingerprint",
        "adapter_version",
        "event_count",
    }
    assert payload["engine_input"]["event_tape"]["event_count"] == 1
    native_events = tuple(
        deserialize_nautilus_native_event_stream(
            BytesIO(store.read(bundle.native_event_stream.artifact.storage_key)),
            expected_source_tape_fingerprint=bundle.native_event_stream.source_tape_fingerprint,
            expected_adapter_version=bundle.native_event_stream.adapter_version,
            expected_event_count=bundle.native_event_stream.event_count,
        )
    )
    assert [event["sequence"] for event in native_events] == [2]


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


def test_trial_assembly_rejects_unapplied_scenario_transforms(tmp_path) -> None:
    values = _inputs(scenario={"volatility_scale": 2})

    with pytest.raises(NautilusTrialAssemblyError, match="scenario transforms"):
        assemble_nautilus_trial_runtime_input(
            **values,
            artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        )


def test_trial_assembly_replays_warmup_but_binds_only_the_evaluation_window(tmp_path) -> None:
    window = EvaluationWindow(
        start=BASE + timedelta(days=1),
        end=BASE + timedelta(days=3),
        purpose="out_of_sample",
        warmup_start=BASE,
    )
    values = _inputs(evaluation_window=window)
    store = LocalArtifactStore(tmp_path / "artifacts")

    assembly = assemble_nautilus_trial_runtime_input(**values, artifact_store=store)
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
    payload = json.loads(bundle.wire_bytes)
    engine_input = payload["engine_input"]
    assert engine_input["evaluation_window"] == {
        "fingerprint": window.fingerprint,
        "purpose": "out_of_sample",
        "warmup_start_ns": 1_704_205_800_000_000_000,
        "start_ns": 1_704_292_200_000_000_000,
        "end_ns": 1_704_465_000_000_000_000,
    }
    assert engine_input["event_tape"]["event_count"] == 2
    assert len(tuple(contexts)) == 2
    assert bundle.native_event_stream is not None
    native_events = tuple(
        deserialize_nautilus_native_event_stream(
            BytesIO(store.read(bundle.native_event_stream.artifact.storage_key)),
            expected_source_tape_fingerprint=bundle.native_event_stream.source_tape_fingerprint,
            expected_adapter_version=bundle.native_event_stream.adapter_version,
            expected_event_count=bundle.native_event_stream.event_count,
        )
    )
    assert [event["sequence"] for event in native_events] == [1, 2]


def test_trial_assembly_rejects_evaluation_window_without_scoring_events(tmp_path) -> None:
    window = EvaluationWindow(
        start=BASE + timedelta(days=2),
        end=BASE + timedelta(days=3),
        purpose="out_of_sample",
        warmup_start=BASE,
    )

    with pytest.raises(NautilusTrialAssemblyError, match="no scoring events"):
        assemble_nautilus_trial_runtime_input(
            **_inputs(evaluation_window=window),
            artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        )


def test_trial_assembly_binds_each_component_strategy_and_context_stream(tmp_path) -> None:
    values = _inputs()
    base_strategy = values["strategy_manifest"].strategy
    first_package = values["strategy_package"]
    second_strategy = replace(base_strategy, version_id="v2")
    second_manifest = StrategySdkManifest(
        second_strategy,
        values["strategy_manifest"].data_dependencies,
    )
    second_package = replace(
        first_package,
        package_id="package-2",
        strategy_fingerprint=second_strategy.fingerprint,
        archive_digest=content_digest("archive-2"),
        manifest_digest=content_digest("manifest-2"),
        dependency_lock_digest=content_digest("dependency-lock-2"),
    )
    base_component = values["portfolio"].components[0]
    first_component = replace(
        base_component,
        component_id="component-1a",
        capital_weight=Decimal("0.5"),
    )
    second_component = replace(
        base_component,
        component_id="component-1b",
        strategy_fingerprint=second_strategy.fingerprint,
        capital_weight=Decimal("0.5"),
    )
    portfolio = PortfolioComposition(
        values["portfolio"].portfolio_id,
        values["portfolio"].version_id,
        values["portfolio"].initial_capital,
        values["portfolio"].base_currency,
        (first_component, second_component),
    )
    experiment = replace(
        values["experiment"],
        portfolio_fingerprint=portfolio.fingerprint,
        strategy_fingerprints=(base_strategy.fingerprint, second_strategy.fingerprint),
        strategy_package_fingerprints={
            base_strategy.fingerprint: first_package.fingerprint,
            second_strategy.fingerprint: second_package.fingerprint,
        },
    )
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=values["snapshot"].fingerprint,
        preflight_report=values["snapshot"].preflight_report,
        parameter_set={"window": 20},
        scenario={},
        seed=13,
    )
    component_inputs = (
        NautilusComponentTrialInput(
            "component-1a",
            first_package,
            values["strategy_manifest"],
            values["strategy_source"],
        ),
        NautilusComponentTrialInput(
            "component-1b",
            second_package,
            second_manifest,
            SOURCE,
        ),
    )
    values["portfolio"] = portfolio
    values["experiment"] = experiment
    values["trial"] = trial
    values["attempt"] = replace(values["attempt"], trial_id=trial.trial_id)
    values["strategy_package"] = None
    values["strategy_source"] = None
    assembly = assemble_nautilus_trial_runtime_input(
        **values,
        component_inputs=component_inputs,
        artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
    )
    store = LocalArtifactStore(tmp_path / "artifacts")
    bundle = load_materialized_nautilus_runtime_bundle(
        assembly.runtime_input_artifact,
        store=store,
        max_input_bytes=1_000_000,
    )
    assert bundle.context_stream is not None
    expected_counts = {"component-1a": 2, "component-1b": 2}
    assert dict(bundle.context_stream.component_counts) == expected_counts
    bindings, contexts = deserialize_component_invocation_context_stream(
        BytesIO(store.read(bundle.context_stream.artifact.storage_key)),
        expected_component_counts=expected_counts,
    )
    assert set(bindings) == set(expected_counts)
    assert {component_id for component_id, _context in contexts} == set(expected_counts)
    assert assembly.strategy_package_fingerprint == strategy_package_set_fingerprint(
        experiment.strategy_package_fingerprints
    )


def test_trial_assembly_requires_per_component_inputs_for_multi_component_portfolios(
    tmp_path,
) -> None:
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

    with pytest.raises(
        NautilusTrialAssemblyError,
        match="multi-component runtime assembly requires one resolved input per component",
    ):
        assemble_nautilus_trial_runtime_input(
            **values,
            artifact_store=LocalArtifactStore(tmp_path / "artifacts"),
        )
