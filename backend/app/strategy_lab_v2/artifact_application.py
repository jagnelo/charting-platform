"""Application composition for immutable Strategy Lab v2 artifacts.

The filesystem store owns only content-addressed bytes and the PostgreSQL
adapter owns only durable commit evidence.  This seam verifies the payload,
publishes it with create-if-absent semantics, and finalizes the matching
metadata record.  A crash between those two operations leaves an immutable
orphan that can be reconciled later; it can never replace a committed digest
with different bytes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.artifact_commit import (
    ArtifactCommitDecision,
    ArtifactCommitLedger,
    ArtifactCommitResolution,
)
from app.strategy_lab_v2.artifact_publication import plan_artifact_publication
from app.strategy_lab_v2.artifact_store import (
    ArtifactStoreDecision,
    ArtifactStoreResolution,
    LocalArtifactStore,
)
from app.strategy_lab_v2.contracts import ArtifactManifest
from app.strategy_lab_v2.postgres_artifact_commit import PostgresArtifactCommitAdapter


class ArtifactCommitter(Protocol):
    async def load_ledger(self) -> ArtifactCommitLedger: ...

    async def finalize(
        self,
        plan: Any,
        *,
        committed_at: datetime,
    ) -> ArtifactCommitResolution: ...


class ArtifactPublicationDecision(StrEnum):
    COMMITTED = "committed"
    REPLAY_EXISTING = "replay_existing"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ArtifactPublicationResolution:
    """Combined byte-publication and durable-commit evidence."""

    decision: ArtifactPublicationDecision
    storage: ArtifactStoreResolution
    commit: ArtifactCommitResolution | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ArtifactPublicationDecision):
            raise TypeError("decision must be an ArtifactPublicationDecision")
        if not isinstance(self.storage, ArtifactStoreResolution):
            raise TypeError("storage must be an ArtifactStoreResolution")
        if self.commit is not None and not isinstance(self.commit, ArtifactCommitResolution):
            raise TypeError("commit must be an ArtifactCommitResolution")
        if self.decision is ArtifactPublicationDecision.REJECT:
            if not self.rejection_reason:
                raise ValueError("rejected publications require a reason")
        elif self.rejection_reason:
            raise ValueError("successful publications cannot contain a rejection reason")
        elif self.commit is None or self.commit.record is None:
            raise ValueError("successful publications require commit evidence")

    @property
    def fingerprint(self) -> str:
        from app.strategy_lab_v2.canonical import content_digest

        return content_digest(self)


class LocalArtifactPublicationService:
    """Coordinate immutable local bytes with PostgreSQL commit evidence."""

    def __init__(self, store: LocalArtifactStore, committer: ArtifactCommitter) -> None:
        if not isinstance(store, LocalArtifactStore):
            raise TypeError("store must be a LocalArtifactStore")
        if not callable(getattr(committer, "load_ledger", None)) or not callable(
            getattr(committer, "finalize", None)
        ):
            raise TypeError("committer must provide load_ledger and finalize methods")
        self._store = store
        self._committer = committer

    @property
    def store(self) -> LocalArtifactStore:
        return self._store

    async def publish(
        self,
        manifest: ArtifactManifest,
        payload: bytes,
        *,
        committed_at: datetime,
    ) -> ArtifactPublicationResolution:
        """Publish verified bytes and finalize their idempotent commit record."""

        if not isinstance(manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        ledger = await self._committer.load_ledger()
        if not isinstance(ledger, ArtifactCommitLedger):
            raise TypeError("committer.load_ledger must return an ArtifactCommitLedger")
        already_committed = any(
            record.storage_key == manifest.storage_key for record in ledger.records
        )
        storage = self._store.publish(manifest, payload)
        if storage.decision is ArtifactStoreDecision.REJECT:
            return ArtifactPublicationResolution(
                ArtifactPublicationDecision.REJECT,
                storage,
                rejection_reason=storage.rejection_reason or "artifact publication was rejected",
            )
        if storage.integrity is None or not storage.integrity.verified:
            raise ValueError("successful artifact storage must include verified integrity")
        plan = plan_artifact_publication(
            manifest,
            storage.integrity,
            already_present=already_committed,
        )
        commit = await self._committer.finalize(plan, committed_at=committed_at)
        if commit.decision is ArtifactCommitDecision.COMMIT:
            return ArtifactPublicationResolution(
                ArtifactPublicationDecision.COMMITTED,
                storage,
                commit,
            )
        if commit.decision is ArtifactCommitDecision.REPLAY_EXISTING:
            return ArtifactPublicationResolution(
                ArtifactPublicationDecision.REPLAY_EXISTING,
                storage,
                commit,
            )
        return ArtifactPublicationResolution(
            ArtifactPublicationDecision.REJECT,
            storage,
            commit,
            rejection_reason=commit.rejection_reason or "artifact commit was rejected",
        )


def create_local_artifact_publication_service(
    root: str | os.PathLike[str],
    session_factory: Any,
) -> LocalArtifactPublicationService:
    """Build the local filesystem/PostgreSQL publication composition.

    The root is deliberately explicit so deployment code can bind it to a
    NAS-mountable volume without adding a global setting or silently choosing a
    host path.  No database connection or filesystem payload is touched until
    the returned service's :meth:`publish` method is called.
    """

    return LocalArtifactPublicationService(
        LocalArtifactStore(root),
        PostgresArtifactCommitAdapter(session_factory),
    )


__all__ = [
    "ArtifactCommitter",
    "ArtifactPublicationDecision",
    "ArtifactPublicationResolution",
    "LocalArtifactPublicationService",
    "create_local_artifact_publication_service",
]
