"""Idempotent, storage-neutral finalization of verified artifact publications."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.artifact_publication import (
    ArtifactPublicationAction,
    ArtifactPublicationPlan,
)
from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ArtifactCommitRecord:
    """Durable-style evidence that one immutable publication was finalized."""

    manifest_fingerprint: str
    content_digest: str
    storage_key: str
    byte_length: int
    committed_at: datetime

    def __post_init__(self) -> None:
        require_sha256_digest(self.manifest_fingerprint, field_name="manifest_fingerprint")
        require_sha256_digest(self.content_digest, field_name="content_digest")
        if self.storage_key != self.content_digest:
            raise ValueError("artifact storage_key must equal its content digest")
        if not isinstance(self.byte_length, int) or isinstance(self.byte_length, bool) or self.byte_length < 0:
            raise ValueError("artifact byte_length must be a non-negative integer")
        _aware(self.committed_at, "committed_at")

    @property
    def commit_key(self) -> str:
        """Stable idempotency identity independent of recording time."""

        return content_digest(
            {
                "byte_length": self.byte_length,
                "content_digest": self.content_digest,
                "manifest_fingerprint": self.manifest_fingerprint,
                "storage_key": self.storage_key,
            }
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ArtifactCommitLedger:
    """Deterministically ordered immutable commit records."""

    records: tuple[ArtifactCommitRecord, ...] = ()

    def __post_init__(self) -> None:
        records = tuple(self.records)
        if any(not isinstance(item, ArtifactCommitRecord) for item in records):
            raise TypeError("records must contain ArtifactCommitRecord values")
        keys = [item.commit_key for item in records]
        if len(keys) != len(set(keys)):
            raise ValueError("artifact commit keys must be unique")
        storage_keys = [item.storage_key for item in records]
        if len(storage_keys) != len(set(storage_keys)):
            raise ValueError("artifact storage keys must be unique")
        object.__setattr__(self, "records", tuple(sorted(records, key=lambda item: item.commit_key)))

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class ArtifactCommitDecision(StrEnum):
    COMMIT = "commit"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ArtifactCommitResolution:
    decision: ArtifactCommitDecision
    ledger: ArtifactCommitLedger
    commit_key: str
    record: ArtifactCommitRecord | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ArtifactCommitDecision):
            raise TypeError("decision must be an ArtifactCommitDecision")
        if not isinstance(self.ledger, ArtifactCommitLedger):
            raise TypeError("ledger must be an ArtifactCommitLedger")
        require_sha256_digest(self.commit_key, field_name="commit_key")
        if self.record is not None and not isinstance(self.record, ArtifactCommitRecord):
            raise TypeError("record must be an ArtifactCommitRecord")
        if self.decision in {
            ArtifactCommitDecision.COMMIT,
            ArtifactCommitDecision.REPLAY_EXISTING,
        } and self.record is None:
            raise ValueError("committed resolutions require a record")
        if self.decision in {
            ArtifactCommitDecision.CONFLICT,
            ArtifactCommitDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision not in {
            ArtifactCommitDecision.CONFLICT,
            ArtifactCommitDecision.REJECT,
        } and self.rejection_reason:
            raise ValueError("successful commit resolutions cannot contain a reason")


def finalize_artifact_commit(
    ledger: ArtifactCommitLedger,
    plan: ArtifactPublicationPlan,
    *,
    committed_at: datetime,
) -> ArtifactCommitResolution:
    """Finalize one publication plan without writing bytes or metadata."""

    if not isinstance(ledger, ArtifactCommitLedger):
        raise TypeError("ledger must be an ArtifactCommitLedger")
    if not isinstance(plan, ArtifactPublicationPlan):
        raise TypeError("plan must be an ArtifactPublicationPlan")
    _aware(committed_at, "committed_at")
    if plan.storage_key != plan.content_digest:
        return ArtifactCommitResolution(
            ArtifactCommitDecision.REJECT,
            ledger,
            content_digest(plan),
            rejection_reason="publication storage key must equal content digest",
        )
    commit_key = content_digest(
        {
            "byte_length": plan.byte_length,
            "content_digest": plan.content_digest,
            "manifest_fingerprint": plan.manifest_fingerprint,
            "storage_key": plan.storage_key,
        }
    )
    existing = next((item for item in ledger.records if item.commit_key == commit_key), None)
    if existing is not None:
        return ArtifactCommitResolution(
            ArtifactCommitDecision.REPLAY_EXISTING,
            ledger,
            commit_key,
            existing,
        )
    storage_collision = next(
        (item for item in ledger.records if item.storage_key == plan.storage_key), None
    )
    if storage_collision is not None:
        return ArtifactCommitResolution(
            ArtifactCommitDecision.CONFLICT,
            ledger,
            commit_key,
            rejection_reason="storage key is already committed to different manifest content",
        )
    if plan.action is ArtifactPublicationAction.REUSE_EXISTING:
        return ArtifactCommitResolution(
            ArtifactCommitDecision.REJECT,
            ledger,
            commit_key,
            rejection_reason="reuse-existing publication requires a committed artifact record",
        )
    record = ArtifactCommitRecord(
        manifest_fingerprint=plan.manifest_fingerprint,
        content_digest=plan.content_digest,
        storage_key=plan.storage_key,
        byte_length=plan.byte_length,
        committed_at=committed_at,
    )
    return ArtifactCommitResolution(
        ArtifactCommitDecision.COMMIT,
        ArtifactCommitLedger(ledger.records + (record,)),
        commit_key,
        record,
    )
