"""Read exact, operator-pinned Nautilus RC conformance evidence locally.

The evidence file is addressed by the SHA-256 of its raw bytes. This source is
deliberately read-only: an operator-controlled build/probe step creates the
artifact, while API and preparation processes only verify and parse it. No
package discovery, image pull, engine startup, or network access occurs here.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.conformance_fixtures import (
    NautilusRcConformanceResolution,
    resolve_nautilus_rc_conformance,
)
from app.strategy_lab_v2.nautilus_runtime import (
    NautilusRcCompatibilityRuntime,
    NautilusRcFixtureReceipt,
    NautilusRuntimeProbeEvidence,
)

LOCAL_NAUTILUS_RC_EVIDENCE_SCHEMA = "strategy-lab.nautilus-rc-evidence-artifact.v1"
DEFAULT_MAX_ARTIFACT_BYTES = 2 * 1024 * 1024
LOCAL_NAUTILUS_RC_EVIDENCE_ENV = {
    "artifact_directory": "STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_DIRECTORY",
    "artifact_digest": "STRATEGY_LAB_V2_NAUTILUS_RC_EVIDENCE_ARTIFACT_SHA256",
    "source_digest": "STRATEGY_LAB_V2_NAUTILUS_RC_SOURCE_SHA256",
    "runtime_image_digest": "STRATEGY_LAB_V2_NAUTILUS_RC_IMAGE_SHA256",
}


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("local Nautilus evidence artifact contains duplicate JSON keys")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"local Nautilus evidence artifact contains invalid JSON constant {value}")


@dataclass(frozen=True, slots=True)
class PublishedLocalNautilusRcEvidence:
    """Content address and validated typed evidence returned by publication."""

    artifact_digest: str
    source: LocalNautilusRcConformanceEvidenceSource
    resolution: NautilusRcConformanceResolution

    def __post_init__(self) -> None:
        require_sha256_digest(self.artifact_digest, field_name="artifact_digest")
        if not isinstance(self.source, LocalNautilusRcConformanceEvidenceSource):
            raise TypeError("source must be a LocalNautilusRcConformanceEvidenceSource")
        if not isinstance(self.resolution, NautilusRcConformanceResolution):
            raise TypeError("resolution must be a NautilusRcConformanceResolution")
        if self.artifact_digest != self.source.artifact_digest:
            raise ValueError("published evidence digest differs from its source pin")


@dataclass(frozen=True, slots=True)
class LocalNautilusRcConformanceEvidencePublisher:
    """Validate and atomically publish one exact-pinned RC fixture artifact.

    The caller is the trusted local qualification command: it supplies probe
    and fixture output captured from the exact isolated image. This class
    validates those outputs before writing and never contacts a provider or
    starts an engine itself.
    """

    artifact_directory: Path
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_directory, Path):
            raise TypeError("artifact_directory must be a Path")
        if (
            not isinstance(self.max_artifact_bytes, int)
            or isinstance(self.max_artifact_bytes, bool)
            or self.max_artifact_bytes <= 0
        ):
            raise ValueError("max_artifact_bytes must be a positive integer")

    def publish(
        self,
        *,
        runtime: NautilusRcCompatibilityRuntime,
        probe_payload: Mapping[str, Any],
        fixture_payload: Mapping[str, Any],
        build_digest: str,
        tested_at: datetime,
    ) -> PublishedLocalNautilusRcEvidence:
        """Validate observed image output, then store it at its immutable digest path."""

        if not isinstance(runtime, NautilusRcCompatibilityRuntime):
            raise TypeError("runtime must be a NautilusRcCompatibilityRuntime")
        if not isinstance(probe_payload, Mapping) or not isinstance(fixture_payload, Mapping):
            raise TypeError("probe_payload and fixture_payload must be mappings")
        probe = NautilusRuntimeProbeEvidence.from_mapping(probe_payload, runtime)
        receipt = NautilusRcFixtureReceipt.from_mapping(fixture_payload, runtime)
        resolution = resolve_nautilus_rc_conformance(
            runtime,
            probe,
            receipt,
            build_digest=build_digest,
            tested_at=tested_at,
        )
        payload = {
            "artifact_schema": LOCAL_NAUTILUS_RC_EVIDENCE_SCHEMA,
            "build_digest": build_digest,
            "probe": dict(probe_payload),
            "receipt": dict(fixture_payload),
            "runtime": {
                "python_version": runtime.python_version,
                "runtime_image_digest": runtime.runtime_image_digest,
                "rust_version": runtime.rust_version,
                "source_digest": runtime.source_digest,
            },
            "tested_at": tested_at.isoformat(),
        }
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(raw) > self.max_artifact_bytes:
            raise ValueError("local Nautilus evidence artifact exceeds its size limit")
        artifact_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        source = LocalNautilusRcConformanceEvidenceSource(
            artifact_directory=self.artifact_directory,
            artifact_digest=artifact_digest,
            expected_source_digest=runtime.source_digest,
            expected_runtime_image_digest=runtime.runtime_image_digest,
            max_artifact_bytes=self.max_artifact_bytes,
        )
        self._write_once(source, raw)
        persisted = source.load()
        if persisted.fingerprint != resolution.fingerprint:
            raise RuntimeError("published Nautilus evidence changed during artifact round-trip")
        return PublishedLocalNautilusRcEvidence(artifact_digest, source, persisted)

    def _write_once(
        self,
        source: LocalNautilusRcConformanceEvidenceSource,
        raw: bytes,
    ) -> None:
        try:
            directory = self.artifact_directory.resolve(strict=True)
            if not directory.is_dir():
                raise ValueError("local Nautilus evidence directory must be a directory")
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".nautilus-rc-evidence-", dir=directory
            )
        except OSError as exc:
            raise ValueError("local Nautilus evidence directory is unavailable") from exc

        temporary_path = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(
                    temporary_path,
                    directory / source.artifact_path.name,
                    follow_symlinks=False,
                )
            except FileExistsError:
                existing = source._read_pinned_bytes()
                if existing != raw:
                    raise ValueError(
                        "content-addressed Nautilus evidence path has conflicting bytes"
                    )
                source.load()
            directory_fd = os.open(
                directory,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0),
            )
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary_path.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class LocalNautilusRcConformanceEvidenceSource:
    """Load one immutable RC5 fixture artifact from an operator-owned directory.

    ``artifact_digest`` addresses the artifact bytes; the independently pinned
    source and image digests prevent a valid receipt from being relabeled for a
    different checkout or worker image. The image must still match the worker
    runtime profile when the preparation context is constructed.
    """

    artifact_directory: Path
    artifact_digest: str
    expected_source_digest: str
    expected_runtime_image_digest: str
    max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_directory, Path):
            raise TypeError("artifact_directory must be a Path")
        for name in ("artifact_digest", "expected_source_digest", "expected_runtime_image_digest"):
            require_sha256_digest(getattr(self, name), field_name=name)
        if (
            not isinstance(self.max_artifact_bytes, int)
            or isinstance(self.max_artifact_bytes, bool)
            or self.max_artifact_bytes <= 0
        ):
            raise ValueError("max_artifact_bytes must be a positive integer")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
    ) -> LocalNautilusRcConformanceEvidenceSource | None:
        """Load operator-pinned local evidence config without discovering artifacts.

        No configured values means RC-backed compatibility execution stays
        unavailable. Partial configuration is an error instead of silently
        selecting an arbitrary file or runtime image.
        """

        values = os.environ if environment is None else environment
        configured = {
            field: values.get(variable, "").strip()
            for field, variable in LOCAL_NAUTILUS_RC_EVIDENCE_ENV.items()
        }
        if not any(configured.values()):
            return None
        missing = tuple(field for field, value in configured.items() if not value)
        if missing:
            raise ValueError(
                "local Nautilus RC evidence configuration is incomplete: " + ", ".join(missing)
            )
        artifact_directory = Path(configured["artifact_directory"]).expanduser()
        if not artifact_directory.is_absolute():
            raise ValueError("local Nautilus evidence directory must be an absolute path")
        return cls(
            artifact_directory=artifact_directory,
            artifact_digest=configured["artifact_digest"],
            expected_source_digest=configured["source_digest"],
            expected_runtime_image_digest=configured["runtime_image_digest"],
        )

    @property
    def artifact_path(self) -> Path:
        """Return the digest-derived artifact path, never a caller-selected filename."""

        filename = f"{self.artifact_digest.removeprefix('sha256:')}.json"
        return self.artifact_directory / filename

    def load(self) -> NautilusRcConformanceResolution:
        """Verify content address and exact runtime pins before parsing evidence."""

        raw = self._read_pinned_bytes()
        actual_digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
        if actual_digest != self.artifact_digest:
            raise ValueError("local Nautilus evidence artifact digest does not match its pin")
        try:
            payload = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_json_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("local Nautilus evidence artifact is not valid UTF-8 JSON") from exc
        return self._resolve_payload(payload)

    def _read_pinned_bytes(self) -> bytes:
        try:
            directory = self.artifact_directory.resolve(strict=True)
            if not directory.is_dir():
                raise ValueError("local Nautilus evidence directory must be a directory")
            path = directory / self.artifact_path.name
            flags = (
                os.O_RDONLY
                | getattr(os, "O_NONBLOCK", 0)
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(path, flags)
        except OSError as exc:
            raise ValueError("pinned local Nautilus evidence artifact is unavailable") from exc

        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError("pinned local Nautilus evidence artifact must be a regular file")
            with os.fdopen(descriptor, "rb", closefd=False) as stream:
                raw = stream.read(self.max_artifact_bytes + 1)
        finally:
            os.close(descriptor)
        if len(raw) > self.max_artifact_bytes:
            raise ValueError("pinned local Nautilus evidence artifact exceeds its size limit")
        return raw

    def _resolve_payload(self, payload: Any) -> NautilusRcConformanceResolution:
        if not isinstance(payload, dict):
            raise ValueError("local Nautilus evidence artifact must be a JSON object")
        expected_fields = {
            "artifact_schema",
            "build_digest",
            "probe",
            "receipt",
            "runtime",
            "tested_at",
        }
        if set(payload) != expected_fields:
            raise ValueError("local Nautilus evidence artifact fields do not match its schema")
        if payload["artifact_schema"] != LOCAL_NAUTILUS_RC_EVIDENCE_SCHEMA:
            raise ValueError("local Nautilus evidence artifact schema is unsupported")

        runtime_payload = payload["runtime"]
        if not isinstance(runtime_payload, dict) or set(runtime_payload) != {
            "python_version",
            "runtime_image_digest",
            "rust_version",
            "source_digest",
        }:
            raise ValueError("local Nautilus runtime pin fields do not match its schema")
        source_digest = runtime_payload["source_digest"]
        image_digest = runtime_payload["runtime_image_digest"]
        if source_digest != self.expected_source_digest:
            raise ValueError("local Nautilus evidence source digest differs from its operator pin")
        if image_digest != self.expected_runtime_image_digest:
            raise ValueError("local Nautilus evidence image digest differs from its operator pin")
        if not all(
            isinstance(runtime_payload[name], str) for name in ("python_version", "rust_version")
        ):
            raise TypeError("local Nautilus runtime versions must be strings")

        runtime = NautilusRcCompatibilityRuntime(
            source_digest=source_digest,
            runtime_image_digest=image_digest,
            python_version=runtime_payload["python_version"],
            rust_version=runtime_payload["rust_version"],
        )
        probe = NautilusRuntimeProbeEvidence.from_mapping(payload["probe"], runtime)
        receipt = NautilusRcFixtureReceipt.from_mapping(payload["receipt"], runtime)
        tested_at = payload["tested_at"]
        if not isinstance(tested_at, str):
            raise TypeError("local Nautilus evidence tested_at must be an ISO timestamp")
        try:
            timestamp = datetime.fromisoformat(
                tested_at[:-1] + "+00:00" if tested_at.endswith("Z") else tested_at
            )
        except ValueError as exc:
            raise ValueError(
                "local Nautilus evidence tested_at is not a valid ISO timestamp"
            ) from exc
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            raise ValueError("local Nautilus evidence tested_at must include a timezone")

        return resolve_nautilus_rc_conformance(
            runtime,
            probe,
            receipt,
            build_digest=payload["build_digest"],
            tested_at=timestamp,
        )


__all__ = [
    "DEFAULT_MAX_ARTIFACT_BYTES",
    "LOCAL_NAUTILUS_RC_EVIDENCE_ENV",
    "LOCAL_NAUTILUS_RC_EVIDENCE_SCHEMA",
    "LocalNautilusRcConformanceEvidencePublisher",
    "LocalNautilusRcConformanceEvidenceSource",
    "PublishedLocalNautilusRcEvidence",
]
