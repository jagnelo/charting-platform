from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import canonical_json, content_digest
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    DataSeriesManifest,
    EvaluationWindow,
    ScientificTrial,
)
from app.strategy_lab_v2.nautilus_runtime_bundle import load_materialized_nautilus_runtime_bundle
from app.strategy_lab_v2.nautilus_trial_assembly import NautilusTrialAssemblyError
from app.strategy_lab_v2.nautilus_trial_materializer import (
    NautilusTrialMarketContext,
    NautilusTrialRuntimeInputMaterializer,
    build_frozen_tape_manifest,
    build_nautilus_trial_runtime_evidence,
)
from app.strategy_lab_v2.rebalance import (
    CalendarRebalancePolicy,
    RebalanceCadence,
    RebalanceTrigger,
)
from app.strategy_lab_v2.runtime import RuntimeIsolationProfile
from app.strategy_lab_v2.sdk import StrategySdkManifest
from app.strategy_lab_v2.strategy_package_resolution import (
    STRATEGY_PACKAGE_LOCK_MEMBER,
    STRATEGY_PACKAGE_MANIFEST_MEMBER,
    STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE,
    STRATEGY_SOURCE_ARCHIVE_SCHEMA,
    StrategyPackageArtifactResolver,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import (
    BASE,
    JsonFrozenSeriesDecoder,
    _calendar_snapshot,
    _inputs,
)
from app.strategy_lab_v2.trial_hydration import HydratedNautilusTrial
from strategy_runtime import serialize_strategy_manifest

RUNTIME_ABI = "worker-abi-v1"


def _build_inputs(tmp_path: Path):
    values = _inputs()
    strategy = values["strategy_manifest"].strategy
    strategy_manifest = values["strategy_manifest"]
    source = values["strategy_source"]
    manifest_bytes = serialize_strategy_manifest(strategy_manifest).encode("utf-8")
    lock_bytes = canonical_json(strategy.dependencies).encode("utf-8")

    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(STRATEGY_PACKAGE_MANIFEST_MEMBER, manifest_bytes)
        archive.writestr(STRATEGY_PACKAGE_LOCK_MEMBER, lock_bytes)
        archive.writestr("strategy/main.py", source.encode("utf-8"))
    archive_bytes = archive_buffer.getvalue()
    package = replace(
        values["strategy_package"],
        package_id="package-materializer-test",
        archive_digest=artifact_content_digest(archive_bytes),
        manifest_digest=artifact_content_digest(manifest_bytes),
        dependency_lock_digest=artifact_content_digest(lock_bytes),
        archive_byte_length=len(archive_bytes),
        runtime_abi=RUNTIME_ABI,
    )

    rows = json.dumps(
        [
            {
                "event_id": f"bar-{sequence}",
                "event_time": (BASE + timedelta(days=sequence - 1)).isoformat(),
                "sequence": sequence,
                "values": {
                    "open": 100 + sequence,
                    "high": 102 + sequence,
                    "low": 99 + sequence,
                    "close": 101 + sequence,
                    "volume": 100000,
                },
            }
            for sequence in (1, 2)
        ],
        separators=(",", ":"),
    ).encode("utf-8")
    series: DataSeriesManifest = values["snapshot"].series[0]
    series = replace(series, content_digest=artifact_content_digest(rows))
    snapshot = replace(values["snapshot"], series=(series,))
    experiment = replace(
        values["experiment"],
        snapshot_fingerprint=snapshot.fingerprint,
        strategy_package_fingerprints={strategy.fingerprint: package.fingerprint},
    )
    old_trial: ScientificTrial = values["trial"]
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
    attempt = replace(values["attempt"], trial_id=trial.trial_id)
    graph = HydratedNautilusTrial(
        attempt=attempt,
        trial=trial,
        experiment=experiment,
        portfolio=values["portfolio"],
        snapshot=snapshot,
        strategies=(strategy,),
        packages={strategy.fingerprint: package},
    )

    store = LocalArtifactStore(tmp_path / "artifacts")
    package_manifest = ArtifactManifest(
        package.archive_digest,
        len(archive_bytes),
        STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE,
        STRATEGY_SOURCE_ARCHIVE_SCHEMA,
        package.archive_digest,
        ArtifactRetention.PINNED_INPUT,
    )
    series_manifest = ArtifactManifest(
        series.content_digest,
        len(rows),
        "application/json",
        "test-series.v1",
        series.content_digest,
        ArtifactRetention.PINNED_INPUT,
    )
    store.publish(package_manifest, archive_bytes)
    store.publish(series_manifest, rows)
    return values, graph, store


def _add_second_strategy(values, graph, store):
    first_strategy = graph.strategies[0]
    first_package = graph.packages[first_strategy.fingerprint]
    second_strategy = replace(first_strategy, version_id="v2")
    second_manifest = StrategySdkManifest(
        second_strategy,
        values["strategy_manifest"].data_dependencies,
    )
    manifest_bytes = serialize_strategy_manifest(second_manifest).encode("utf-8")
    lock_bytes = canonical_json(second_strategy.dependencies).encode("utf-8")
    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(STRATEGY_PACKAGE_MANIFEST_MEMBER, manifest_bytes)
        archive.writestr(STRATEGY_PACKAGE_LOCK_MEMBER, lock_bytes)
        archive.writestr("strategy/main.py", values["strategy_source"].encode("utf-8"))
    archive_bytes = archive_buffer.getvalue()
    second_package = replace(
        first_package,
        package_id="package-materializer-test-v2",
        strategy_fingerprint=second_strategy.fingerprint,
        archive_digest=artifact_content_digest(archive_bytes),
        manifest_digest=artifact_content_digest(manifest_bytes),
        dependency_lock_digest=artifact_content_digest(lock_bytes),
        archive_byte_length=len(archive_bytes),
    )
    store.publish(
        ArtifactManifest(
            second_package.archive_digest,
            len(archive_bytes),
            STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE,
            STRATEGY_SOURCE_ARCHIVE_SCHEMA,
            second_package.archive_digest,
            ArtifactRetention.PINNED_INPUT,
        ),
        archive_bytes,
    )
    base_component = graph.portfolio.components[0]
    portfolio = replace(
        graph.portfolio,
        components=(
            replace(
                base_component,
                component_id="component-a",
                capital_weight=Decimal("0.5"),
            ),
            replace(
                base_component,
                component_id="component-b",
                strategy_fingerprint=second_strategy.fingerprint,
                capital_weight=Decimal("0.5"),
            ),
        ),
    )
    experiment = replace(
        graph.experiment,
        portfolio_fingerprint=portfolio.fingerprint,
        strategy_fingerprints=(first_strategy.fingerprint, second_strategy.fingerprint),
        strategy_package_fingerprints={
            first_strategy.fingerprint: first_package.fingerprint,
            second_strategy.fingerprint: second_package.fingerprint,
        },
    )
    prior_trial = graph.trial
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=graph.snapshot.fingerprint,
        preflight_report=prior_trial.preflight_report,
        parameter_set=prior_trial.parameter_set,
        scenario=prior_trial.scenario,
        seed=prior_trial.seed,
        randomization=prior_trial.randomization,
        evaluation_window=prior_trial.evaluation_window,
    )
    multi_graph = HydratedNautilusTrial(
        attempt=replace(graph.attempt, trial_id=trial.trial_id),
        trial=trial,
        experiment=experiment,
        portfolio=portfolio,
        snapshot=graph.snapshot,
        strategies=(first_strategy, second_strategy),
        packages={
            first_strategy.fingerprint: first_package,
            second_strategy.fingerprint: second_package,
        },
    )
    return multi_graph


def test_shared_frozen_tape_manifest_unions_strictest_lookback() -> None:
    source_manifest = _inputs()["strategy_manifest"]
    dependency = source_manifest.data_dependencies[0]
    longer = replace(dependency, lookback_periods=dependency.lookback_periods + 5)
    component_manifest = replace(source_manifest, data_dependencies=(longer,))

    combined = build_frozen_tape_manifest(
        source_manifest.strategy,
        (source_manifest, component_manifest),
    )

    assert combined.strategy == source_manifest.strategy
    assert combined.data_dependencies == (longer,)
    assert combined.model_dependencies == source_manifest.model_dependencies


def test_shared_frozen_tape_manifest_rejects_conflicting_dependency_identity() -> None:
    source_manifest = _inputs()["strategy_manifest"]
    dependency = source_manifest.data_dependencies[0]
    conflicting = replace(dependency, fields=("close",))
    component_manifest = replace(source_manifest, data_dependencies=(conflicting,))

    with pytest.raises(ValueError, match="conflicting semantics"):
        build_frozen_tape_manifest(
            source_manifest.strategy,
            (source_manifest, component_manifest),
        )


def test_materializer_resolves_owner_graph_and_verified_inputs(tmp_path: Path) -> None:
    values, graph, store = _build_inputs(tmp_path)
    market_context = NautilusTrialMarketContext(values["instruments"], values["venue"])
    materializer = NautilusTrialRuntimeInputMaterializer(
        artifact_store=store,
        strategy_package_resolver=StrategyPackageArtifactResolver(
            store,
            runtime_abi=RUNTIME_ABI,
        ),
        series_decoder=JsonFrozenSeriesDecoder(),
    )

    result = materializer.materialize(graph=graph, market_context=market_context)

    assert result.graph == graph
    assert result.assembly.attempt_id == graph.attempt.attempt_id
    assert result.assembly.trial_fingerprint == graph.trial.trial_id
    assert result.assembly.strategy_package_fingerprint == next(
        iter(graph.experiment.strategy_package_fingerprints.values())
    )
    assert result.assembly.runtime_input_artifact.trial_binding == result.assembly.trial_binding
    assert result.assembly.trial_binding.snapshot_fingerprint == graph.snapshot.fingerprint
    bundle = load_materialized_nautilus_runtime_bundle(
        result.assembly.runtime_input_artifact,
        store,
        max_input_bytes=1_000_000,
    )
    assert bundle.input_bundle_digest == result.assembly.runtime_input_artifact.input_bundle_digest


def test_materializer_passes_trusted_calendar_into_frozen_trial_plan(tmp_path: Path) -> None:
    values, graph, store = _build_inputs(tmp_path)
    calendar = _calendar_snapshot()
    policy = CalendarRebalancePolicy(
        calendar_id=calendar.calendar_id,
        calendar_fingerprint=calendar.fingerprint,
        cadence=RebalanceCadence.EACH_SESSION,
        trigger=RebalanceTrigger.SESSION_OPEN_BEFORE_EVENTS,
    )
    portfolio = replace(graph.portfolio, rebalance_policy=policy)
    experiment = replace(graph.experiment, portfolio_fingerprint=portfolio.fingerprint)
    previous_trial = graph.trial
    trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=previous_trial.snapshot_fingerprint,
        preflight_report=previous_trial.preflight_report,
        parameter_set=previous_trial.parameter_set,
        scenario=previous_trial.scenario,
        seed=previous_trial.seed,
        randomization=previous_trial.randomization,
        evaluation_window=EvaluationWindow(
            start=BASE + timedelta(days=1),
            end=BASE + timedelta(days=2),
            purpose="out_of_sample",
            warmup_start=BASE,
        ),
    )
    graph = replace(
        graph,
        attempt=replace(graph.attempt, trial_id=trial.trial_id),
        trial=trial,
        experiment=experiment,
        portfolio=portfolio,
    )
    materializer = NautilusTrialRuntimeInputMaterializer(
        artifact_store=store,
        strategy_package_resolver=StrategyPackageArtifactResolver(
            store,
            runtime_abi=RUNTIME_ABI,
        ),
        series_decoder=JsonFrozenSeriesDecoder(),
    )

    materialized = materializer.materialize(
        graph=graph,
        market_context=NautilusTrialMarketContext(
            values["instruments"],
            values["venue"],
            session_calendar=calendar,
            session_periods_per_year=252,
        ),
    )
    bundle = load_materialized_nautilus_runtime_bundle(
        materialized.assembly.runtime_input_artifact,
        store,
        max_input_bytes=1_000_000,
    )

    payload = json.loads(bundle.wire_bytes)
    assert len(payload["engine_input"]["rebalance_plan"]["occurrences"]) == 1
    assert payload["engine_input"]["rebalance_plan"]["calendar_fingerprint"] == calendar.fingerprint
    assert bundle.session_calendar == calendar
    assert bundle.session_periods_per_year == 252


def test_materializer_resolves_every_strategy_in_a_shared_portfolio(tmp_path: Path) -> None:
    values, single_graph, store = _build_inputs(tmp_path)
    graph = _add_second_strategy(values, single_graph, store)
    materializer = NautilusTrialRuntimeInputMaterializer(
        artifact_store=store,
        strategy_package_resolver=StrategyPackageArtifactResolver(
            store,
            runtime_abi=RUNTIME_ABI,
        ),
        series_decoder=JsonFrozenSeriesDecoder(),
    )

    materialized = materializer.materialize(
        graph=graph,
        market_context=NautilusTrialMarketContext(values["instruments"], values["venue"]),
    )
    bundle = load_materialized_nautilus_runtime_bundle(
        materialized.assembly.runtime_input_artifact,
        store,
        max_input_bytes=1_000_000,
    )

    assert bundle.context_stream is not None
    assert dict(bundle.context_stream.component_counts) == {"component-a": 2, "component-b": 2}
    assert materialized.assembly.strategy_package_fingerprint != next(
        iter(graph.experiment.strategy_package_fingerprints.values())
    )
    strategies_by_fingerprint = {item.fingerprint: item for item in graph.strategies}
    packages_by_fingerprint = graph.packages
    primary_strategy_fingerprint = graph.experiment.strategy_fingerprints[0]
    profile = RuntimeIsolationProfile(
        runtime_image_digest=content_digest("multi-strategy-runtime-image"),
        runtime_abi=RUNTIME_ABI,
        allowed_dependency_digests=frozenset(
            dependency.artifact_digest
            for strategy in graph.strategies
            for dependency in strategy.dependencies
        ),
    )
    evidence = build_nautilus_trial_runtime_evidence(
        materialized,
        profile,
        request_id=content_digest("multi-strategy-runtime-request"),
        submitted_at=BASE,
    )
    assert (
        evidence.runtime_request.entrypoint
        == packages_by_fingerprint[primary_strategy_fingerprint].entrypoint
    )
    assert (
        evidence.runtime_request.source_digest
        != strategies_by_fingerprint[primary_strategy_fingerprint].source_digest
    )
    assert evidence.runtime_preflight.accepted is True


def test_runtime_evidence_is_derived_from_materialized_package_and_bundle(tmp_path: Path) -> None:
    _values, graph, store = _build_inputs(tmp_path)
    materializer = NautilusTrialRuntimeInputMaterializer(
        artifact_store=store,
        strategy_package_resolver=StrategyPackageArtifactResolver(
            store,
            runtime_abi=RUNTIME_ABI,
        ),
        series_decoder=JsonFrozenSeriesDecoder(),
    )
    materialized = materializer.materialize(
        graph=graph,
        market_context=NautilusTrialMarketContext(_values["instruments"], _values["venue"]),
    )
    strategy = graph.strategies[0]
    profile = RuntimeIsolationProfile(
        runtime_image_digest=content_digest("runtime-image"),
        runtime_abi=RUNTIME_ABI,
        allowed_dependency_digests=frozenset(
            dependency.artifact_digest for dependency in strategy.dependencies
        ),
    )

    evidence = build_nautilus_trial_runtime_evidence(
        materialized,
        profile,
        request_id=content_digest("runtime-request"),
        submitted_at=BASE,
    )

    assert evidence.runtime_request.attempt_id == graph.attempt.attempt_id
    assert (
        evidence.runtime_request.package_fingerprint
        == materialized.assembly.strategy_package_fingerprint
    )
    assert (
        evidence.runtime_request.input_bundle_digest
        == materialized.assembly.runtime_input_artifact.input_bundle_digest
    )
    assert evidence.runtime_preflight.accepted is True

    with pytest.raises(ValueError, match="ABI differs"):
        build_nautilus_trial_runtime_evidence(
            materialized,
            replace(profile, runtime_abi="different-worker-abi"),
            request_id=content_digest("runtime-request"),
            submitted_at=BASE,
        )


def test_materializer_rejects_incomplete_canonical_market_context(tmp_path: Path) -> None:
    values, graph, store = _build_inputs(tmp_path)
    other_instrument = replace(values["instruments"][0], instrument_id="US.MSFT")
    materializer = NautilusTrialRuntimeInputMaterializer(
        artifact_store=store,
        strategy_package_resolver=StrategyPackageArtifactResolver(
            store,
            runtime_abi=RUNTIME_ABI,
        ),
        series_decoder=JsonFrozenSeriesDecoder(),
    )

    with pytest.raises(NautilusTrialAssemblyError, match="resolve every portfolio instrument"):
        materializer.materialize(
            graph=graph,
            market_context=NautilusTrialMarketContext((other_instrument,), values["venue"]),
        )


def test_materializer_requires_one_shared_verified_artifact_store(tmp_path: Path) -> None:
    values, graph, store = _build_inputs(tmp_path)
    other_store = LocalArtifactStore(tmp_path / "other-artifacts")

    with pytest.raises(ValueError, match="share one artifact store"):
        NautilusTrialRuntimeInputMaterializer(
            artifact_store=other_store,
            strategy_package_resolver=StrategyPackageArtifactResolver(
                store,
                runtime_abi=RUNTIME_ABI,
            ),
            series_decoder=JsonFrozenSeriesDecoder(),
        )
