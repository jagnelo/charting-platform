"""Immutable artifact-lineage records for reproducible Strategy Lab runs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


class LineageRole(StrEnum):
    STRATEGY_SOURCE = "strategy_source"
    DEPENDENCY_LOCK = "dependency_lock"
    DATA_SNAPSHOT = "data_snapshot"
    CAPABILITY_REPORT = "capability_report"
    INPUT_ARTIFACT = "input_artifact"
    OUTPUT_ARTIFACT = "output_artifact"
    METRIC_SET = "metric_set"
    ENGINE_BUILD = "engine_build"
    FORWARD_EVENT_TAPE = "forward_event_tape"


@dataclass(frozen=True, slots=True)
class ArtifactLineageEntry:
    """One immutable owner-to-artifact provenance edge."""

    owner_type: str
    owner_id: str
    artifact_manifest_fingerprint: str
    role: LineageRole
    created_at: datetime
    parent_manifest_fingerprint: str | None = None

    def __post_init__(self) -> None:
        for name in ("owner_type", "owner_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"lineage {name} must not be empty")
        require_sha256_digest(
            self.artifact_manifest_fingerprint, field_name="artifact_manifest_fingerprint"
        )
        if not isinstance(self.role, LineageRole):
            raise TypeError("lineage role must be a LineageRole")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("lineage created_at must be timezone-aware")
        if self.parent_manifest_fingerprint is not None:
            require_sha256_digest(
                self.parent_manifest_fingerprint, field_name="parent_manifest_fingerprint"
            )
            if self.parent_manifest_fingerprint == self.artifact_manifest_fingerprint:
                raise ValueError("lineage entry cannot reference itself as its parent")

    @property
    def semantic_key(self) -> str:
        """Identity for idempotency, excluding recording-time metadata."""

        return content_digest(
            {
                "artifact_manifest_fingerprint": self.artifact_manifest_fingerprint,
                "owner_id": self.owner_id,
                "owner_type": self.owner_type,
                "parent_manifest_fingerprint": self.parent_manifest_fingerprint,
                "role": self.role,
            }
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ArtifactLineageIndex:
    """Deterministically ordered lineage edges for one owner."""

    owner_type: str
    owner_id: str
    entries: tuple[ArtifactLineageEntry, ...] = ()

    def __post_init__(self) -> None:
        for name in ("owner_type", "owner_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"lineage index {name} must not be empty")
        entries = tuple(self.entries)
        if any(not isinstance(item, ArtifactLineageEntry) for item in entries):
            raise TypeError("lineage entries must contain ArtifactLineageEntry values")
        if any(item.owner_type != self.owner_type or item.owner_id != self.owner_id for item in entries):
            raise ValueError("lineage entries must reference the index owner")
        keys = [item.semantic_key for item in entries]
        if len(keys) != len(set(keys)):
            raise ValueError("lineage semantic keys must be unique")
        object.__setattr__(
            self,
            "entries",
            tuple(
                sorted(
                    entries,
                    key=lambda item: (
                        item.role.value,
                        item.artifact_manifest_fingerprint,
                        item.parent_manifest_fingerprint or "",
                    ),
                )
            ),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class LineageDecision(StrEnum):
    APPEND = "append"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class LineageResolution:
    decision: LineageDecision
    index: ArtifactLineageIndex
    entry_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.decision, LineageDecision):
            raise TypeError("lineage decision must be a LineageDecision")
        if not isinstance(self.index, ArtifactLineageIndex):
            raise TypeError("lineage resolution index must be an ArtifactLineageIndex")
        require_sha256_digest(self.entry_fingerprint, field_name="entry_fingerprint")


def append_lineage_entry(
    index: ArtifactLineageIndex, entry: ArtifactLineageEntry
) -> LineageResolution:
    """Resolve an idempotent append without mutating storage."""

    if not isinstance(index, ArtifactLineageIndex):
        raise TypeError("index must be an ArtifactLineageIndex")
    if not isinstance(entry, ArtifactLineageEntry):
        raise TypeError("entry must be an ArtifactLineageEntry")
    if entry.owner_type != index.owner_type or entry.owner_id != index.owner_id:
        raise ValueError("lineage entry must reference the index owner")
    matching = tuple(item for item in index.entries if item.semantic_key == entry.semantic_key)
    if matching:
        decision = (
            LineageDecision.REPLAY_EXISTING
            if matching[0].fingerprint == entry.fingerprint
            else LineageDecision.CONFLICT
        )
        return LineageResolution(decision, index, entry.fingerprint)
    next_index = ArtifactLineageIndex(
        owner_type=index.owner_type,
        owner_id=index.owner_id,
        entries=index.entries + (entry,),
    )
    return LineageResolution(LineageDecision.APPEND, next_index, entry.fingerprint)


def build_lineage_index(
    owner_type: str, owner_id: str, entries: Sequence[ArtifactLineageEntry] = ()
) -> ArtifactLineageIndex:
    """Build a validated deterministic index from adapter-read records."""

    if not isinstance(entries, Sequence) or isinstance(entries, str | bytes):
        raise TypeError("entries must be a sequence")
    return ArtifactLineageIndex(owner_type, owner_id, tuple(entries))
