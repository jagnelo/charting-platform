from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import canonical_json, content_digest
from app.strategy_lab_v2.capabilities import CapabilityRequirement
from app.strategy_lab_v2.contracts import (
    AdjustmentMode,
    ArtifactManifest,
    ArtifactRetention,
    EventGranularity,
    ProductClass,
    StrategyPackage,
    StrategyPackageFormat,
    StrategyVersion,
)
from app.strategy_lab_v2.sdk import StrategyDataDependency, StrategySdkManifest
from app.strategy_lab_v2.strategy_package_resolution import (
    STRATEGY_PACKAGE_LOCK_MEMBER,
    STRATEGY_PACKAGE_MANIFEST_MEMBER,
    STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE,
    STRATEGY_SOURCE_ARCHIVE_SCHEMA,
    StrategyPackageArtifactResolver,
    StrategyPackageResolutionError,
)
from strategy_runtime import serialize_strategy_manifest

NOW = datetime(2024, 1, 1, tzinfo=UTC)
RUNTIME_ABI = "cp312-linux-x86_64-v1"
ENTRYPOINT = "strategy.main:Strategy"
SOURCE = "class Strategy:\n    def on_event(self, context):\n        return []\n"


def _fixture(
    tmp_path,
    *,
    source: str = SOURCE,
    lock: bytes | None = None,
    extra_members: dict[str, bytes] | None = None,
):
    strategy = StrategyVersion(
        "strategy-1",
        "v1",
        "2.0.0",
        content_digest(source),
    )
    requirement = CapabilityRequirement(
        instrument_id="US.AAPL",
        product_class=ProductClass.EQUITY,
        event_granularity=EventGranularity.BAR,
        event_type="ohlcv",
        timeframe="1d",
        start=NOW,
        end=NOW + timedelta(days=1),
        adjustment=AdjustmentMode.SPLIT_ADJUSTED,
        session="regular",
        feed="consolidated",
        execution_model="bar-close-v1",
        account_model="cash-equity-v1",
        corporate_action_semantics="split-adjusted-v1",
    )
    sdk_manifest = StrategySdkManifest(
        strategy,
        (StrategyDataDependency("daily-bars", requirement, ("close",)),),
    )
    manifest_bytes = serialize_strategy_manifest(sdk_manifest).encode("utf-8")
    expected_lock = canonical_json(strategy.dependencies).encode("utf-8")
    lock_bytes = expected_lock if lock is None else lock
    members = {
        STRATEGY_PACKAGE_MANIFEST_MEMBER: manifest_bytes,
        STRATEGY_PACKAGE_LOCK_MEMBER: lock_bytes,
        "strategy/main.py": source.encode("utf-8"),
        **(extra_members or {}),
    }
    archive_stream = BytesIO()
    with ZipFile(archive_stream, mode="w", compression=ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    archive_bytes = archive_stream.getvalue()
    package = StrategyPackage(
        package_id="package-1",
        strategy_fingerprint=strategy.fingerprint,
        package_format=StrategyPackageFormat.SOURCE_ARCHIVE,
        archive_digest=artifact_content_digest(archive_bytes),
        manifest_digest=artifact_content_digest(manifest_bytes),
        dependency_lock_digest=artifact_content_digest(lock_bytes),
        archive_byte_length=len(archive_bytes),
        entrypoint=ENTRYPOINT,
        sdk_version=strategy.sdk_version,
        runtime_abi=RUNTIME_ABI,
    )
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
    return store, package, strategy, sdk_manifest, archive_bytes


def test_resolver_reconstructs_verified_source_manifest_and_lock(tmp_path) -> None:
    store, package, strategy, sdk_manifest, _archive = _fixture(tmp_path)

    resolved = StrategyPackageArtifactResolver(store, runtime_abi=RUNTIME_ABI).resolve(
        package,
        strategy,
    )

    assert resolved.source == SOURCE
    assert resolved.manifest == sdk_manifest
    assert resolved.dependency_lock == canonical_json(strategy.dependencies).encode("utf-8")
    assert resolved.archive_manifest.content_digest == package.archive_digest
    assert resolved.archive_manifest.retention_class is ArtifactRetention.PINNED_INPUT


def test_resolver_rejects_manifest_and_dependency_lock_digest_drift(tmp_path) -> None:
    store, package, strategy, _manifest, _archive = _fixture(tmp_path)
    drifted_manifest = StrategyPackage(
        **{
            **{field: getattr(package, field) for field in package.__dataclass_fields__},
            "manifest_digest": content_digest("different-manifest"),
        }
    )

    with pytest.raises(StrategyPackageResolutionError, match="manifest digest"):
        StrategyPackageArtifactResolver(store, runtime_abi=RUNTIME_ABI).resolve(
            drifted_manifest,
            strategy,
        )

    store, package, strategy, _manifest, _archive = _fixture(
        tmp_path / "other",
        lock=b"not-the-canonical-dependency-lock",
    )
    with pytest.raises(StrategyPackageResolutionError, match="dependency lock does not match"):
        StrategyPackageArtifactResolver(store, runtime_abi=RUNTIME_ABI).resolve(package, strategy)


def test_resolver_rejects_non_exact_runtime_abi_and_wheel_packages(tmp_path) -> None:
    store, package, strategy, _manifest, _archive = _fixture(tmp_path)
    with pytest.raises(StrategyPackageResolutionError, match="runtime ABI"):
        StrategyPackageArtifactResolver(store, runtime_abi="different-abi").resolve(
            package,
            strategy,
        )

    wheel_package = StrategyPackage(
        package.package_id,
        package.strategy_fingerprint,
        StrategyPackageFormat.WHEEL,
        package.archive_digest,
        package.manifest_digest,
        package.dependency_lock_digest,
        package.archive_byte_length,
        package.entrypoint,
        package.sdk_version,
        package.runtime_abi,
    )
    with pytest.raises(StrategyPackageResolutionError, match="source archives only"):
        StrategyPackageArtifactResolver(store, runtime_abi=RUNTIME_ABI).resolve(
            wheel_package,
            strategy,
        )


def test_resolver_rejects_source_digest_drift_and_extra_archive_members(tmp_path) -> None:
    store, package, strategy, _manifest, _archive = _fixture(
        tmp_path,
        source="class Strategy:\n    def on_event(self, context):\n        return [1]\n",
    )
    wrong_strategy = StrategyVersion(
        strategy.strategy_id,
        strategy.version_id,
        strategy.sdk_version,
        content_digest(SOURCE),
    )
    with pytest.raises(StrategyPackageResolutionError, match="different strategy"):
        StrategyPackageArtifactResolver(store, runtime_abi=RUNTIME_ABI).resolve(
            package,
            wrong_strategy,
        )

    store, package, strategy, _manifest, _archive = _fixture(
        tmp_path / "extra",
        extra_members={"../escape.py": b"bad"},
    )
    with pytest.raises(StrategyPackageResolutionError, match="exactly its manifest"):
        StrategyPackageArtifactResolver(store, runtime_abi=RUNTIME_ABI).resolve(package, strategy)


def test_resolver_rejects_source_that_fails_static_sdk_validation(tmp_path) -> None:
    source = (
        "class Strategy:\n    def on_event(self, context):\n        return open('/etc/passwd')\n"
    )
    store, package, strategy, _manifest, _archive = _fixture(tmp_path, source=source)

    with pytest.raises(StrategyPackageResolutionError, match="static validation"):
        StrategyPackageArtifactResolver(store, runtime_abi=RUNTIME_ABI).resolve(package, strategy)


def test_resolver_enforces_archive_and_member_size_limits(tmp_path) -> None:
    store, package, strategy, _manifest, _archive = _fixture(tmp_path)

    with pytest.raises(StrategyPackageResolutionError, match="archive exceeds its size limit"):
        StrategyPackageArtifactResolver(
            store,
            runtime_abi=RUNTIME_ABI,
            max_archive_bytes=package.archive_byte_length - 1,
        ).resolve(package, strategy)

    with pytest.raises(StrategyPackageResolutionError, match="member exceeds"):
        StrategyPackageArtifactResolver(
            store,
            runtime_abi=RUNTIME_ABI,
            max_member_bytes=8,
        ).resolve(package, strategy)

    repetitive_source = SOURCE + "\n# " + ("reproducible-source-comment " * 2_000) + "\n"
    store, package, strategy, _manifest, _archive = _fixture(
        tmp_path / "ratio",
        source=repetitive_source,
    )
    with pytest.raises(StrategyPackageResolutionError, match="compression ratio"):
        StrategyPackageArtifactResolver(
            store,
            runtime_abi=RUNTIME_ABI,
            max_compression_ratio=1,
        ).resolve(package, strategy)
