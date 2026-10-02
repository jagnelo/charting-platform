from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import canonical_json
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    ScientificTrial,
    StrategyPackage,
)
from app.strategy_lab_v2.nautilus_trial_assembly import (
    assemble_nautilus_trial_runtime_input_from_package,
)
from app.strategy_lab_v2.strategy_package_resolution import (
    STRATEGY_PACKAGE_LOCK_MEMBER,
    STRATEGY_PACKAGE_MANIFEST_MEMBER,
    STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE,
    STRATEGY_SOURCE_ARCHIVE_SCHEMA,
    StrategyPackageArtifactResolver,
)
from app.strategy_lab_v2.tests.test_nautilus_trial_assembly import _inputs
from strategy_runtime import serialize_strategy_manifest


def test_runtime_assembly_resolves_package_from_the_shared_artifact_store(tmp_path) -> None:
    values = _inputs()
    strategy = values["strategy_manifest"].strategy
    source = values["strategy_source"]
    manifest_bytes = serialize_strategy_manifest(values["strategy_manifest"]).encode("utf-8")
    dependency_lock = canonical_json(strategy.dependencies).encode("utf-8")
    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(STRATEGY_PACKAGE_MANIFEST_MEMBER, manifest_bytes)
        archive.writestr(STRATEGY_PACKAGE_LOCK_MEMBER, dependency_lock)
        archive.writestr("strategy/main.py", source.encode("utf-8"))
    archive_bytes = archive_buffer.getvalue()
    package = StrategyPackage(
        package_id="package-verified",
        strategy_fingerprint=strategy.fingerprint,
        package_format=values["strategy_package"].package_format,
        archive_digest=artifact_content_digest(archive_bytes),
        manifest_digest=artifact_content_digest(manifest_bytes),
        dependency_lock_digest=artifact_content_digest(dependency_lock),
        archive_byte_length=len(archive_bytes),
        entrypoint=values["strategy_package"].entrypoint,
        sdk_version=strategy.sdk_version,
        runtime_abi="worker-abi-v1",
    )
    experiment = replace(
        values["experiment"],
        strategy_package_fingerprints={strategy.fingerprint: package.fingerprint},
    )
    trial = values["trial"]
    pinned_trial = ScientificTrial.create(
        experiment_fingerprint=experiment.fingerprint,
        snapshot_fingerprint=trial.snapshot_fingerprint,
        preflight_report=trial.preflight_report,
        parameter_set=trial.parameter_set,
        scenario=trial.scenario,
        seed=trial.seed,
        randomization=trial.randomization,
        evaluation_window=trial.evaluation_window,
    )
    attempt = replace(values["attempt"], trial_id=pinned_trial.trial_id)
    store = LocalArtifactStore(tmp_path / "artifacts")
    archive_manifest = ArtifactManifest(
        package.archive_digest,
        package.archive_byte_length,
        STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE,
        STRATEGY_SOURCE_ARCHIVE_SCHEMA,
        package.archive_digest,
        ArtifactRetention.PINNED_INPUT,
    )
    store.publish(archive_manifest, archive_bytes)

    assembly_inputs = dict(values)
    assembly_inputs["experiment"] = experiment
    assembly_inputs["trial"] = pinned_trial
    assembly_inputs["attempt"] = attempt
    assembly_inputs.pop("strategy_manifest")
    assembly_inputs.pop("strategy_source")
    assembly_inputs["strategy_package"] = package
    assembly = assemble_nautilus_trial_runtime_input_from_package(
        **assembly_inputs,
        strategy=strategy,
        strategy_package_resolver=StrategyPackageArtifactResolver(
            store,
            runtime_abi="worker-abi-v1",
        ),
        artifact_store=store,
    )

    assert assembly.strategy_package_fingerprint == package.fingerprint
    assert assembly.runtime_input_artifact.attempt_id == values["attempt"].attempt_id
    assert store.read(assembly.runtime_input_artifact.artifact.storage_key)


def test_runtime_assembly_rejects_a_different_runtime_artifact_store(tmp_path) -> None:
    values = _inputs()
    strategy = values["strategy_manifest"].strategy
    values.pop("strategy_manifest")
    values.pop("strategy_source")
    store = LocalArtifactStore(tmp_path / "package-artifacts")
    with pytest.raises(ValueError, match="share one artifact store"):
        assemble_nautilus_trial_runtime_input_from_package(
            **values,
            strategy=strategy,
            strategy_package_resolver=StrategyPackageArtifactResolver(
                store,
                runtime_abi="worker-abi-v1",
            ),
            artifact_store=LocalArtifactStore(tmp_path / "runtime-artifacts"),
        )
