"""Local content-addressed artifact storage implementation.

The store is intentionally small and adapter-oriented: manifests and commit
ledgers remain authoritative domain records, while this class owns only raw
bytes. Publication uses a same-directory temporary file followed by an atomic
hard-link, so a concurrent writer cannot replace an existing digest. Payloads
are made read-only after publication and every read is re-verified.
"""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from app.strategy_lab_v2.artifact_retention import (
    ArtifactRetentionResolution,
    RetentionDecision,
)
from app.strategy_lab_v2.artifacts import (
    ArtifactIntegrityReceipt,
    artifact_content_digest,
    verify_artifact_payload,
)
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.contracts import ArtifactManifest


class ArtifactStoreDecision(StrEnum):
    WRITTEN = "written"
    REUSED = "reused"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ArtifactStoreResolution:
    """Result of one local artifact publication attempt."""

    decision: ArtifactStoreDecision
    storage_key: str
    byte_length: int
    integrity: ArtifactIntegrityReceipt | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ArtifactStoreDecision):
            raise TypeError("decision must be an ArtifactStoreDecision")
        require_sha256_digest(self.storage_key, field_name="storage_key")
        if not isinstance(self.byte_length, int) or isinstance(self.byte_length, bool) or self.byte_length < 0:
            raise ValueError("byte_length must be a non-negative integer")
        if self.integrity is not None and not isinstance(self.integrity, ArtifactIntegrityReceipt):
            raise TypeError("integrity must be an ArtifactIntegrityReceipt")
        if self.decision is ArtifactStoreDecision.REJECT and not self.rejection_reason:
            raise ValueError("rejected store resolutions require a reason")
        if self.decision is not ArtifactStoreDecision.REJECT and self.rejection_reason:
            raise ValueError("successful store resolutions cannot contain a reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ArtifactStoreCorruptionError(RuntimeError):
    """Raised when bytes at a content address no longer match that address."""


class ArtifactByteDecision(StrEnum):
    DELETED = "deleted"
    RETAINED = "retained"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class ArtifactByteResolution:
    """Evidence for one retention-authorized byte collection attempt."""

    decision: ArtifactByteDecision
    storage_key: str
    byte_length: int
    retention: ArtifactRetentionResolution
    integrity: ArtifactIntegrityReceipt | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ArtifactByteDecision):
            raise TypeError("decision must be an ArtifactByteDecision")
        require_sha256_digest(self.storage_key, field_name="storage_key")
        if not isinstance(self.byte_length, int) or isinstance(self.byte_length, bool) or self.byte_length < 0:
            raise ValueError("byte_length must be a non-negative integer")
        if not isinstance(self.retention, ArtifactRetentionResolution):
            raise TypeError("retention must be an ArtifactRetentionResolution")
        if self.integrity is not None and not isinstance(self.integrity, ArtifactIntegrityReceipt):
            raise TypeError("integrity must be an ArtifactIntegrityReceipt")
        if self.decision is ArtifactByteDecision.RETAINED and self.rejection_reason:
            raise ValueError("retained artifact bytes cannot contain a rejection reason")
        if self.decision is not ArtifactByteDecision.RETAINED and self.rejection_reason:
            raise ValueError("artifact byte resolutions cannot contain a rejection reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ArtifactCleanupKind(StrEnum):
    """Kind of uncommitted filesystem entry observed during cleanup."""

    CONTENT = "content"
    TEMPORARY = "temporary"


class ArtifactCleanupDecision(StrEnum):
    """Outcome for one safely discovered uncommitted entry."""

    DELETED = "deleted"
    RETAINED = "retained"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class ArtifactCleanupRecord:
    """Auditable result for one content or crash-left temporary file."""

    kind: ArtifactCleanupKind
    storage_key: str
    relative_path: str
    byte_length: int
    modified_at: datetime
    decision: ArtifactCleanupDecision
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ArtifactCleanupKind):
            raise TypeError("kind must be an ArtifactCleanupKind")
        require_sha256_digest(self.storage_key, field_name="storage_key")
        for name in ("relative_path", "reason"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.byte_length, int) or isinstance(self.byte_length, bool) or self.byte_length < 0:
            raise ValueError("byte_length must be a non-negative integer")
        if self.modified_at.tzinfo is None or self.modified_at.utcoffset() is None:
            raise ValueError("modified_at must be timezone-aware")
        if not isinstance(self.decision, ArtifactCleanupDecision):
            raise TypeError("decision must be an ArtifactCleanupDecision")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ArtifactCleanupResolution:
    """Deterministic bounded cleanup evidence for one explicit observation."""

    observed_at: datetime
    minimum_age: timedelta
    records: tuple[ArtifactCleanupRecord, ...] = ()

    def __post_init__(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if not isinstance(self.minimum_age, timedelta) or self.minimum_age.total_seconds() < 0:
            raise ValueError("minimum_age must be a non-negative timedelta")
        records = tuple(self.records)
        if any(not isinstance(record, ArtifactCleanupRecord) for record in records):
            raise TypeError("records must contain ArtifactCleanupRecord values")
        paths = [record.relative_path for record in records]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("cleanup records must be unique and deterministically ordered")
        object.__setattr__(self, "records", records)

    @property
    def deleted_count(self) -> int:
        return sum(record.decision is ArtifactCleanupDecision.DELETED for record in self.records)

    @property
    def retained_count(self) -> int:
        return sum(record.decision is ArtifactCleanupDecision.RETAINED for record in self.records)

    @property
    def not_found_count(self) -> int:
        return sum(record.decision is ArtifactCleanupDecision.NOT_FOUND for record in self.records)

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class LocalArtifactStore:
    """Filesystem-backed immutable store for raw content-addressed payloads."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        raw_root = os.fspath(root)
        if not isinstance(raw_root, str) or not raw_root.strip():
            raise ValueError("artifact store root must not be empty")
        path = Path(root)
        if path.is_symlink():
            raise ValueError("artifact store root must not be a symlink")
        if path.exists() and not path.is_dir():
            raise ValueError("artifact store root must be a directory")
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            raise ValueError("artifact store root must be a directory")
        self._root = path.resolve()

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, storage_key: str) -> Path:
        """Return the deterministic sharded path for one validated digest."""

        require_sha256_digest(storage_key, field_name="storage_key")
        digest_hex = storage_key.removeprefix("sha256:")
        shard = self._root / digest_hex[:2]
        if shard.exists() and shard.is_symlink():
            raise ArtifactStoreCorruptionError("artifact shard directory is a symlink")
        path = shard / digest_hex
        resolved_parent = shard.resolve(strict=False)
        try:
            resolved_parent.relative_to(self._root)
        except ValueError as error:
            raise ArtifactStoreCorruptionError("artifact path escapes the store root") from error
        return path

    def publish(self, manifest: ArtifactManifest, payload: bytes) -> ArtifactStoreResolution:
        """Atomically create or reuse an artifact after byte-level verification."""

        if not isinstance(manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        integrity = verify_artifact_payload(manifest, payload)
        if not integrity.verified:
            return ArtifactStoreResolution(
                ArtifactStoreDecision.REJECT,
                manifest.storage_key,
                len(payload),
                integrity,
                "artifact payload failed integrity verification",
            )

        target = self.path_for(manifest.storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.parent.is_symlink():
            raise ArtifactStoreCorruptionError("artifact shard directory is a symlink")
        existing = self._read_existing(target, manifest.storage_key)
        if existing is not None:
            existing_integrity = verify_artifact_payload(manifest, existing)
            if not existing_integrity.verified:
                raise ArtifactStoreCorruptionError(
                    "existing artifact bytes do not match the requested manifest"
                )
            return ArtifactStoreResolution(
                ArtifactStoreDecision.REUSED,
                manifest.storage_key,
                len(existing),
                existing_integrity,
            )

        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=target.parent, prefix=f".{target.name}.", delete=False
            ) as temporary:
                temporary_name = temporary.name
                temporary.write(payload)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_name, 0o444)
            try:
                os.link(temporary_name, target)
            except FileExistsError:
                raced = self._read_existing(target, manifest.storage_key)
                if raced is None:
                    raise ArtifactStoreCorruptionError(
                        "artifact target appeared but could not be read"
                    )
                raced_integrity = verify_artifact_payload(manifest, raced)
                if not raced_integrity.verified:
                    raise ArtifactStoreCorruptionError(
                        "concurrent artifact writer published mismatched bytes"
                    )
                return ArtifactStoreResolution(
                    ArtifactStoreDecision.REUSED,
                    manifest.storage_key,
                    len(raced),
                    raced_integrity,
                )
            self._fsync_directory(target.parent)
            published = self._read_existing(target, manifest.storage_key)
            if published is None:
                raise ArtifactStoreCorruptionError("published artifact cannot be read")
            published_integrity = verify_artifact_payload(manifest, published)
            if not published_integrity.verified:
                raise ArtifactStoreCorruptionError("published artifact failed verification")
            return ArtifactStoreResolution(
                ArtifactStoreDecision.WRITTEN,
                manifest.storage_key,
                len(published),
                published_integrity,
            )
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass

    def read(self, storage_key: str) -> bytes:
        """Read and verify raw bytes against their content-addressed key."""

        target = self.path_for(storage_key)
        payload = self._read_existing(target, storage_key)
        if payload is None:
            raise FileNotFoundError(target)
        return payload

    def read_manifest(self, manifest: ArtifactManifest) -> tuple[bytes, ArtifactIntegrityReceipt]:
        """Read one manifest payload and return its complete integrity receipt."""

        if not isinstance(manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        payload = self.read(manifest.storage_key)
        integrity = verify_artifact_payload(manifest, payload)
        if not integrity.verified:
            raise ArtifactStoreCorruptionError("artifact bytes do not match the manifest")
        return payload, integrity

    def collect(
        self,
        manifest: ArtifactManifest,
        retention: ArtifactRetentionResolution,
    ) -> ArtifactByteResolution:
        """Delete bytes only after an explicit, authenticated eligible decision."""

        if not isinstance(manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if not isinstance(retention, ArtifactRetentionResolution):
            raise TypeError("retention must be an ArtifactRetentionResolution")
        manifest_fingerprint = content_digest(manifest)
        if retention.state.manifest_fingerprint != manifest_fingerprint:
            raise ValueError("retention resolution references a different manifest")
        if retention.state.content_digest != manifest.content_digest:
            raise ValueError("retention resolution references different artifact bytes")
        target = self.path_for(manifest.storage_key)
        existing = self._read_existing(target, manifest.storage_key)
        if existing is None:
            return ArtifactByteResolution(
                ArtifactByteDecision.NOT_FOUND,
                manifest.storage_key,
                0,
                retention,
            )
        integrity = verify_artifact_payload(manifest, existing)
        if not integrity.verified:
            raise ArtifactStoreCorruptionError("artifact bytes do not match the manifest")
        if retention.decision not in {
            RetentionDecision.TIER_ELIGIBLE,
            RetentionDecision.EXPIRE_ELIGIBLE,
        }:
            return ArtifactByteResolution(
                ArtifactByteDecision.RETAINED,
                manifest.storage_key,
                len(existing),
                retention,
                integrity,
            )
        try:
            target.unlink()
        except FileNotFoundError:
            return ArtifactByteResolution(
                ArtifactByteDecision.NOT_FOUND,
                manifest.storage_key,
                0,
                retention,
            )
        self._fsync_directory(target.parent)
        return ArtifactByteResolution(
            ArtifactByteDecision.DELETED,
            manifest.storage_key,
            len(existing),
            retention,
            integrity,
        )

    def cleanup_uncommitted(
        self,
        committed_storage_keys: Collection[str],
        *,
        observed_at: datetime,
        minimum_age: timedelta,
    ) -> ArtifactCleanupResolution:
        """Reconcile aged uncommitted bytes and crash-left temp files.

        PostgreSQL commit records are authoritative.  A content file is only
        deleted when its digest is verified, it is absent from that committed
        set, and its explicit filesystem mtime is at least ``minimum_age`` in
        the past.  Temporary publication files are identified by the store's
        private naming pattern and receive the same age guard.  Unknown files
        and directories are never touched.
        """

        if not isinstance(committed_storage_keys, Collection) or isinstance(
            committed_storage_keys, str | bytes
        ):
            raise TypeError("committed_storage_keys must be a collection of digest strings")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if not isinstance(minimum_age, timedelta) or minimum_age.total_seconds() < 0:
            raise ValueError("minimum_age must be a non-negative timedelta")
        committed: set[str] = set()
        for storage_key in committed_storage_keys:
            require_sha256_digest(storage_key, field_name="committed_storage_key")
            committed.add(storage_key)

        records: list[ArtifactCleanupRecord] = []
        for shard in sorted(self._root.iterdir(), key=lambda item: item.name):
            if shard.is_symlink():
                raise ArtifactStoreCorruptionError("artifact shard directory is a symlink")
            if not shard.is_dir() or re.fullmatch(r"[0-9a-f]{2}", shard.name) is None:
                continue
            for entry in sorted(shard.iterdir(), key=lambda item: item.name):
                if entry.is_symlink():
                    raise ArtifactStoreCorruptionError("artifact cleanup target is a symlink")
                if not entry.is_file():
                    continue
                content_match = re.fullmatch(r"[0-9a-f]{64}", entry.name)
                temporary_match = re.fullmatch(r"\.([0-9a-f]{64})\.[^/]+", entry.name)
                if content_match is None and temporary_match is None:
                    continue
                if content_match is not None:
                    digest_hex = content_match.group(0)
                else:
                    if temporary_match is None:  # pragma: no cover - guarded above
                        continue
                    digest_hex = temporary_match.group(1)
                storage_key = f"sha256:{digest_hex}"
                stat_result = entry.stat(follow_symlinks=False)
                modified_at = datetime.fromtimestamp(stat_result.st_mtime, tz=UTC)
                age = observed_at - modified_at
                eligible = age >= minimum_age
                kind = (
                    ArtifactCleanupKind.CONTENT
                    if content_match is not None
                    else ArtifactCleanupKind.TEMPORARY
                )
                if kind is ArtifactCleanupKind.CONTENT:
                    payload = self._read_existing(entry, storage_key)
                    if payload is None:  # pragma: no cover - entry was a regular file
                        continue
                    byte_length = len(payload)
                    if storage_key in committed:
                        decision, reason = ArtifactCleanupDecision.RETAINED, "committed"
                    elif not eligible:
                        decision, reason = ArtifactCleanupDecision.RETAINED, "minimum_age_not_reached"
                    else:
                        decision, reason = self._delete_cleanup_entry(entry, "uncommitted_content")
                else:
                    byte_length = stat_result.st_size
                    if not eligible:
                        decision, reason = ArtifactCleanupDecision.RETAINED, "minimum_age_not_reached"
                    else:
                        decision, reason = self._delete_cleanup_entry(entry, "temporary_publication_file")
                records.append(
                    ArtifactCleanupRecord(
                        kind,
                        storage_key,
                        entry.relative_to(self._root).as_posix(),
                        byte_length if decision is not ArtifactCleanupDecision.NOT_FOUND else 0,
                        modified_at,
                        decision,
                        reason,
                    )
                )
        return ArtifactCleanupResolution(observed_at, minimum_age, tuple(sorted(records, key=lambda item: item.relative_path)))

    @staticmethod
    def _delete_cleanup_entry(
        entry: Path, reason: str
    ) -> tuple[ArtifactCleanupDecision, str]:
        if entry.is_symlink():
            raise ArtifactStoreCorruptionError("artifact cleanup target became a symlink")
        try:
            entry.unlink()
        except FileNotFoundError:
            return ArtifactCleanupDecision.NOT_FOUND, "already_absent"
        LocalArtifactStore._fsync_directory(entry.parent)
        return ArtifactCleanupDecision.DELETED, reason

    @staticmethod
    def _read_existing(target: Path, storage_key: str) -> bytes | None:
        if target.is_symlink():
            raise ArtifactStoreCorruptionError("artifact target is not a regular immutable file")
        if not target.exists():
            return None
        if not target.is_file():
            raise ArtifactStoreCorruptionError("artifact target is not a regular immutable file")
        payload = target.read_bytes()
        if artifact_content_digest(payload) != storage_key:
            raise ArtifactStoreCorruptionError("existing artifact bytes have the wrong digest")
        return payload

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
