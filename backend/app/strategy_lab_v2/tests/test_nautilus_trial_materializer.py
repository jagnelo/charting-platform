from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import canonical_json
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    DataSeriesManifest,
    ScientificTrial,
)
from app.strategy_lab_v2.nautilus_runtime_bundle import load_materialized_nautilus_runtime_bundle
from app.strategy_lab_v2.nautilus_trial_assembly import NautilusTrialAssemblyError
from app.strategy_lab_v2.nautilus_trial_materializer import (
    NautilusTrialMarketContext,
    NautilusTrialRuntimeInputMaterializer,
)
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
    bundle = load_materialized_nautilus_runtime_bundle(
        result.assembly.runtime_input_artifact,
        store,
        max_input_bytes=1_000_000,
    )
    assert bundle.input_bundle_digest == result.assembly.runtime_input_artifact.input_bundle_digest


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
