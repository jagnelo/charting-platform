"""Verified local source-package loading for isolated Strategy Lab workers.

The package contract stores a content-addressed source archive. This resolver
defines the v1 source-archive layout and checks the archive, embedded SDK
manifest, exact dependency lock, strategy source, and requested runtime ABI
before returning executable source to the existing trial assembler. It never
extracts files to disk or installs dependencies.
"""

from __future__ import annotations

import stat
from dataclasses import dataclass
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile

from app.strategy_lab_v2.artifact_store import ArtifactStoreCorruptionError, LocalArtifactStore
from app.strategy_lab_v2.artifacts import artifact_content_digest
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import (
    ArtifactManifest,
    ArtifactRetention,
    StrategyPackage,
    StrategyPackageFormat,
    StrategyVersion,
)
from app.strategy_lab_v2.sdk import StrategySdkManifest
from app.strategy_lab_v2.strategy_validation import validate_strategy_source
from strategy_runtime import deserialize_strategy_manifest

STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE = "application/vnd.charting.strategy-lab.source-package+zip"
STRATEGY_SOURCE_ARCHIVE_SCHEMA = "strategy-lab.source-package.v1"
STRATEGY_PACKAGE_MANIFEST_MEMBER = "manifest.json"
STRATEGY_PACKAGE_LOCK_MEMBER = "dependencies.lock"
DEFAULT_MAX_STRATEGY_ARCHIVE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_STRATEGY_MEMBER_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_ARCHIVE_COMPRESSION_RATIO = 200


class StrategyPackageResolutionError(ValueError):
    """A persisted strategy package cannot be safely resolved for execution."""


@dataclass(frozen=True, slots=True)
class ResolvedStrategyPackage:
    """Verified material needed by the engine-neutral strategy runtime."""

    package_fingerprint: str
    strategy_fingerprint: str
    source: str
    manifest: StrategySdkManifest
    dependency_lock: bytes
    archive_manifest: ArtifactManifest

    def __post_init__(self) -> None:
        require_sha256_digest(self.package_fingerprint, field_name="package_fingerprint")
        require_sha256_digest(self.strategy_fingerprint, field_name="strategy_fingerprint")
        if not isinstance(self.source, str) or not self.source:
            raise ValueError("resolved strategy source must not be empty")
        if not isinstance(self.manifest, StrategySdkManifest):
            raise TypeError("manifest must use StrategySdkManifest")
        if not isinstance(self.dependency_lock, bytes) or not self.dependency_lock:
            raise ValueError("resolved dependency lock must be non-empty bytes")
        if not isinstance(self.archive_manifest, ArtifactManifest):
            raise TypeError("archive_manifest must be an ArtifactManifest")
        if self.manifest.strategy.fingerprint != self.strategy_fingerprint:
            raise ValueError("resolved manifest references a different strategy")
        if content_digest(self.source) != self.manifest.strategy.source_digest:
            raise ValueError("resolved source does not match its strategy digest")

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "archive_manifest": self.archive_manifest,
                "dependency_lock_digest": artifact_content_digest(self.dependency_lock),
                "manifest_fingerprint": self.manifest.fingerprint,
                "package_fingerprint": self.package_fingerprint,
                "source_digest": content_digest(self.source),
                "strategy_fingerprint": self.strategy_fingerprint,
            }
        )


class StrategyPackageArtifactResolver:
    """Read and validate a v1 source archive from the local artifact store."""

    def __init__(
        self,
        store: LocalArtifactStore,
        *,
        runtime_abi: str,
        max_archive_bytes: int = DEFAULT_MAX_STRATEGY_ARCHIVE_BYTES,
        max_member_bytes: int = DEFAULT_MAX_STRATEGY_MEMBER_BYTES,
        max_compression_ratio: int = DEFAULT_MAX_ARCHIVE_COMPRESSION_RATIO,
    ) -> None:
        if not isinstance(store, LocalArtifactStore):
            raise TypeError("store must be a LocalArtifactStore")
        if not isinstance(runtime_abi, str) or not runtime_abi.strip():
            raise ValueError("runtime_abi must not be empty")
        for name, value in (
            ("max_archive_bytes", max_archive_bytes),
            ("max_member_bytes", max_member_bytes),
            ("max_compression_ratio", max_compression_ratio),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        self._store = store
        self._runtime_abi = runtime_abi.strip()
        self._max_archive_bytes = max_archive_bytes
        self._max_member_bytes = max_member_bytes
        self._max_compression_ratio = max_compression_ratio

    @property
    def store(self) -> LocalArtifactStore:
        """The content store that owns the exact package bytes."""

        return self._store

    def resolve(
        self,
        package: StrategyPackage,
        strategy: StrategyVersion,
    ) -> ResolvedStrategyPackage:
        """Resolve exact source/manifest/lock bytes without extracting or installing."""

        if not isinstance(package, StrategyPackage):
            raise TypeError("package must be a StrategyPackage")
        if not isinstance(strategy, StrategyVersion):
            raise TypeError("strategy must be a StrategyVersion")
        if package.package_format is not StrategyPackageFormat.SOURCE_ARCHIVE:
            raise StrategyPackageResolutionError(
                "the isolated strategy runtime currently accepts source archives only"
            )
        if package.strategy_fingerprint != strategy.fingerprint:
            raise StrategyPackageResolutionError(
                "strategy package references a different strategy version"
            )
        if package.sdk_version != strategy.sdk_version:
            raise StrategyPackageResolutionError(
                "strategy package SDK version differs from its strategy"
            )
        if package.runtime_abi != self._runtime_abi:
            raise StrategyPackageResolutionError(
                "strategy package runtime ABI differs from the isolated worker"
            )
        if package.archive_byte_length > self._max_archive_bytes:
            raise StrategyPackageResolutionError("strategy source archive exceeds its size limit")

        archive_manifest = ArtifactManifest(
            content_digest=package.archive_digest,
            byte_length=package.archive_byte_length,
            media_type=STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE,
            schema_version=STRATEGY_SOURCE_ARCHIVE_SCHEMA,
            storage_key=package.archive_digest,
            retention_class=ArtifactRetention.PINNED_INPUT,
        )
        try:
            archive_bytes, _integrity = self._store.read_manifest(
                archive_manifest,
                max_bytes=self._max_archive_bytes,
            )
        except (ArtifactStoreCorruptionError, FileNotFoundError, OSError, ValueError) as error:
            raise StrategyPackageResolutionError(
                "strategy source archive is missing or failed integrity verification"
            ) from error
        if len(archive_bytes) > self._max_archive_bytes:
            raise StrategyPackageResolutionError("strategy source archive exceeds its size limit")

        source_path = _source_member_for_entrypoint(package.entrypoint)
        try:
            members = _read_archive_members(
                archive_bytes,
                source_member=source_path,
                max_member_bytes=self._max_member_bytes,
                max_compression_ratio=self._max_compression_ratio,
            )
        except StrategyPackageResolutionError:
            raise
        except (BadZipFile, EOFError, OSError, RuntimeError, ValueError) as error:
            raise StrategyPackageResolutionError("strategy source archive is malformed") from error

        manifest_bytes = members[STRATEGY_PACKAGE_MANIFEST_MEMBER]
        lock_bytes = members[STRATEGY_PACKAGE_LOCK_MEMBER]
        source_bytes = members[source_path]
        if artifact_content_digest(manifest_bytes) != package.manifest_digest:
            raise StrategyPackageResolutionError(
                "embedded strategy SDK manifest digest differs from package metadata"
            )
        if artifact_content_digest(lock_bytes) != package.dependency_lock_digest:
            raise StrategyPackageResolutionError(
                "embedded dependency lock digest differs from package metadata"
            )
        try:
            manifest_text = manifest_bytes.decode("utf-8", errors="strict")
            source = source_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise StrategyPackageResolutionError(
                "strategy source archive text members must be UTF-8"
            ) from error
        if not source:
            raise StrategyPackageResolutionError("strategy source must not be empty")
        try:
            manifest = deserialize_strategy_manifest(manifest_text)
        except ValueError as error:
            raise StrategyPackageResolutionError(
                "embedded strategy SDK manifest is invalid"
            ) from error
        if not isinstance(manifest, StrategySdkManifest):
            raise StrategyPackageResolutionError("embedded strategy SDK manifest is invalid")
        if manifest.strategy.fingerprint != strategy.fingerprint:
            raise StrategyPackageResolutionError(
                "embedded strategy SDK manifest references a different strategy"
            )
        if artifact_content_digest(lock_bytes) != content_digest(strategy.dependencies):
            raise StrategyPackageResolutionError(
                "dependency lock does not match the strategy's exact dependency set"
            )
        if content_digest(source) != strategy.source_digest:
            raise StrategyPackageResolutionError("strategy source digest differs from its version")
        source_validation = validate_strategy_source(source)
        if not source_validation.accepted:
            raise StrategyPackageResolutionError(
                "strategy source failed the engine-neutral SDK static validation"
            )

        return ResolvedStrategyPackage(
            package_fingerprint=package.fingerprint,
            strategy_fingerprint=strategy.fingerprint,
            source=source,
            manifest=manifest,
            dependency_lock=lock_bytes,
            archive_manifest=archive_manifest,
        )


def _source_member_for_entrypoint(entrypoint: str) -> str:
    if not isinstance(entrypoint, str) or ":" not in entrypoint:
        raise StrategyPackageResolutionError("strategy package entrypoint is malformed")
    module_name, _separator, _callable = entrypoint.partition(":")
    if not module_name or any(not part.isidentifier() for part in module_name.split(".")):
        raise StrategyPackageResolutionError("strategy package entrypoint module is malformed")
    return "/".join(module_name.split(".")) + ".py"


def _read_archive_members(
    archive_bytes: bytes,
    *,
    source_member: str,
    max_member_bytes: int,
    max_compression_ratio: int,
) -> dict[str, bytes]:
    required = {
        STRATEGY_PACKAGE_MANIFEST_MEMBER,
        STRATEGY_PACKAGE_LOCK_MEMBER,
        source_member,
    }
    with ZipFile(BytesIO(archive_bytes), mode="r") as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)):
            raise StrategyPackageResolutionError("strategy archive contains duplicate members")
        if set(names) != required:
            raise StrategyPackageResolutionError(
                "strategy source archive must contain exactly its manifest, lock, and entrypoint"
            )
        result: dict[str, bytes] = {}
        for entry in entries:
            if entry.is_dir() or entry.flag_bits & 0x1:
                raise StrategyPackageResolutionError(
                    "strategy archive members must be unencrypted regular files"
                )
            if entry.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                raise StrategyPackageResolutionError(
                    "strategy archive uses an unsupported compression method"
                )
            mode = entry.external_attr >> 16
            if stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
                raise StrategyPackageResolutionError(
                    "strategy archive members must not be links or special files"
                )
            if entry.file_size > max_member_bytes:
                raise StrategyPackageResolutionError(
                    "strategy archive member exceeds its configured size limit"
                )
            if entry.file_size > max(1, entry.compress_size) * max_compression_ratio:
                raise StrategyPackageResolutionError(
                    "strategy archive member exceeds its configured compression ratio"
                )
            member = archive.read(entry)
            if len(member) != entry.file_size:
                raise StrategyPackageResolutionError(
                    "strategy archive member length differs from its directory entry"
                )
            result[entry.filename] = member
        return result


__all__ = [
    "DEFAULT_MAX_ARCHIVE_COMPRESSION_RATIO",
    "DEFAULT_MAX_STRATEGY_ARCHIVE_BYTES",
    "DEFAULT_MAX_STRATEGY_MEMBER_BYTES",
    "ResolvedStrategyPackage",
    "STRATEGY_PACKAGE_LOCK_MEMBER",
    "STRATEGY_PACKAGE_MANIFEST_MEMBER",
    "STRATEGY_SOURCE_ARCHIVE_MEDIA_TYPE",
    "STRATEGY_SOURCE_ARCHIVE_SCHEMA",
    "StrategyPackageArtifactResolver",
    "StrategyPackageResolutionError",
]
