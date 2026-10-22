"""Application composition for immutable Strategy Lab v2 artifacts.

The filesystem store owns only content-addressed bytes and the PostgreSQL
adapter owns only durable commit evidence.  This seam verifies byte payloads
or streamed local result files, publishes them with create-if-absent semantics,
and finalizes the matching metadata record.  A crash between those two
operations leaves an immutable orphan that can be reconciled later; it can
never replace a committed digest with different bytes.
"""

from __future__ import annotations

import asyncio
import math
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from app.strategy_lab_v2.artifact_commit import (
    ArtifactCommitDecision,
    ArtifactCommitLedger,
    ArtifactCommitResolution,
)
from app.strategy_lab_v2.artifact_publication import (
    ArtifactPublicationPlan,
    plan_artifact_publication,
)
from app.strategy_lab_v2.artifact_retention import ArtifactRetentionResolution
from app.strategy_lab_v2.artifact_store import (
    ArtifactByteResolution,
    ArtifactCleanupResolution,
    ArtifactStoreDecision,
    ArtifactStoreResolution,
    LocalArtifactStore,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.contracts import ArtifactManifest
from app.strategy_lab_v2.nautilus_equity_trace import (
    MAX_NAUTILUS_ACCOUNT_EQUITY_TRACE_BYTES,
    verify_nautilus_account_equity_trace_file,
)
from app.strategy_lab_v2.nautilus_native_reports import (
    MAX_NAUTILUS_NATIVE_REPORTS_BYTES,
    verify_nautilus_native_reports_file,
)
from app.strategy_lab_v2.nautilus_runner import NautilusRunResult
from app.strategy_lab_v2.nautilus_runtime_bundle import (
    verify_nautilus_invocation_result_stream_file,
)
from app.strategy_lab_v2.postgres_artifact_commit import PostgresArtifactCommitAdapter
from app.strategy_lab_v2.postgres_artifact_retention import PostgresArtifactRetentionAdapter
from app.strategy_lab_v2.sandbox import (
    SandboxCommandPlan,
    sandbox_account_equity_trace_path,
    sandbox_invocation_result_stream_path,
    sandbox_native_reports_path,
    sandbox_output_path,
)
from app.strategy_lab_v2.sandbox_execution import SandboxRunResult, SandboxRunStatus


class ArtifactCommitter(Protocol):
    async def load_ledger(self) -> ArtifactCommitLedger: ...

    async def finalize(
        self,
        plan: Any,
        *,
        committed_at: datetime,
    ) -> ArtifactCommitResolution: ...


class ArtifactRetentionResolver(Protocol):
    async def resolve(
        self, *, manifest_fingerprint: str, observed_at: datetime
    ) -> ArtifactRetentionResolution: ...


class ArtifactCommitLedgerProvider(Protocol):
    async def load_ledger(self) -> ArtifactCommitLedger: ...


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
    artifact_plan: ArtifactPublicationPlan | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ArtifactPublicationDecision):
            raise TypeError("decision must be an ArtifactPublicationDecision")
        if not isinstance(self.storage, ArtifactStoreResolution):
            raise TypeError("storage must be an ArtifactStoreResolution")
        if self.commit is not None and not isinstance(self.commit, ArtifactCommitResolution):
            raise TypeError("commit must be an ArtifactCommitResolution")
        if self.artifact_plan is not None and not isinstance(
            self.artifact_plan, ArtifactPublicationPlan
        ):
            raise TypeError("artifact_plan must be an ArtifactPublicationPlan")
        if self.decision is ArtifactPublicationDecision.REJECT:
            if not self.rejection_reason:
                raise ValueError("rejected publications require a reason")
            if self.artifact_plan is not None:
                raise ValueError("rejected publications cannot contain an artifact plan")
        elif self.rejection_reason:
            raise ValueError("successful publications cannot contain a rejection reason")
        elif self.commit is None or self.commit.record is None or self.artifact_plan is None:
            raise ValueError("successful publications require commit and plan evidence")

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
        return await self._finalize_storage(
            manifest,
            storage,
            already_committed=already_committed,
            committed_at=committed_at,
        )

    async def publish_file(
        self,
        manifest: ArtifactManifest,
        source: str | os.PathLike[str],
        *,
        committed_at: datetime,
    ) -> ArtifactPublicationResolution:
        """Publish a mounted/local result file without loading it in memory."""

        if not isinstance(manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if committed_at.tzinfo is None or committed_at.utcoffset() is None:
            raise ValueError("committed_at must be timezone-aware")
        ledger = await self._committer.load_ledger()
        if not isinstance(ledger, ArtifactCommitLedger):
            raise TypeError("committer.load_ledger must return an ArtifactCommitLedger")
        already_committed = any(
            record.storage_key == manifest.storage_key for record in ledger.records
        )
        storage = self._store.publish_file(manifest, source)
        return await self._finalize_storage(
            manifest,
            storage,
            already_committed=already_committed,
            committed_at=committed_at,
        )

    async def publish_sandbox_result(
        self,
        manifest: ArtifactManifest,
        sandbox_plan: SandboxCommandPlan,
        sandbox_result: SandboxRunResult,
        *,
        committed_at: datetime,
    ) -> ArtifactPublicationResolution:
        """Publish the exact result file identified by one sandbox execution."""

        if not isinstance(manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if not isinstance(sandbox_plan, SandboxCommandPlan):
            raise TypeError("sandbox_plan must be a SandboxCommandPlan")
        if not isinstance(sandbox_result, SandboxRunResult):
            raise TypeError("sandbox_result must be a SandboxRunResult")
        if sandbox_result.plan_fingerprint != sandbox_plan.fingerprint:
            raise ValueError("sandbox result does not match its command plan")
        if sandbox_result.status is not SandboxRunStatus.SUCCEEDED:
            raise ValueError("sandbox result publication requires a successful execution")
        if sandbox_result.result_digest is None or sandbox_result.result_bytes is None:
            raise ValueError("sandbox result is missing mounted result evidence")
        if manifest.content_digest != sandbox_result.result_digest:
            raise ValueError("artifact manifest does not match sandbox result digest")
        if manifest.byte_length != sandbox_result.result_bytes:
            raise ValueError("artifact manifest does not match sandbox result length")
        return await self.publish_file(
            manifest,
            sandbox_output_path(sandbox_plan),
            committed_at=committed_at,
        )

    async def publish_nautilus_invocation_result_stream(
        self,
        manifest: ArtifactManifest,
        sandbox_plan: SandboxCommandPlan,
        run_result: NautilusRunResult,
        *,
        committed_at: datetime,
    ) -> ArtifactPublicationResolution:
        """Publish the verified callback-result sidecar without loading it in memory."""

        if not isinstance(manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if not isinstance(sandbox_plan, SandboxCommandPlan):
            raise TypeError("sandbox_plan must be a SandboxCommandPlan")
        if not isinstance(run_result, NautilusRunResult):
            raise TypeError("run_result must be a NautilusRunResult")
        reference = run_result.invocation_result_stream
        if reference is None:
            raise ValueError("Nautilus run is missing its verified invocation result stream")
        if run_result.sandbox_plan_fingerprint != sandbox_plan.fingerprint:
            raise ValueError("Nautilus run result does not match its sandbox plan")
        if run_result.sandbox_result is None or (
            run_result.sandbox_result.status is not SandboxRunStatus.SUCCEEDED
        ):
            raise ValueError("invocation result stream requires a successful sandbox process")
        if manifest != reference.artifact:
            raise ValueError("artifact manifest does not match the verified result stream")
        path = sandbox_invocation_result_stream_path(sandbox_plan)
        if path is None:
            raise ValueError("sandbox plan has no invocation result stream mount")
        verify_nautilus_invocation_result_stream_file(
            reference,
            path,
            max_result_bytes=sandbox_plan.output_limit_bytes,
        )
        return await self.publish_file(manifest, path, committed_at=committed_at)

    async def publish_nautilus_account_equity_trace(
        self,
        manifest: ArtifactManifest,
        sandbox_plan: SandboxCommandPlan,
        run_result: NautilusRunResult,
        *,
        committed_at: datetime,
    ) -> ArtifactPublicationResolution:
        """Publish the exact native OOS equity trace accepted by the runner."""

        if not isinstance(manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if not isinstance(sandbox_plan, SandboxCommandPlan):
            raise TypeError("sandbox_plan must be a SandboxCommandPlan")
        if not isinstance(run_result, NautilusRunResult):
            raise TypeError("run_result must be a NautilusRunResult")
        reference = run_result.account_equity_trace
        if reference is None:
            raise ValueError("Nautilus run is missing its verified native account-equity trace")
        if run_result.sandbox_plan_fingerprint != sandbox_plan.fingerprint:
            raise ValueError("Nautilus run result does not match its sandbox plan")
        if run_result.sandbox_result is None or (
            run_result.sandbox_result.status is not SandboxRunStatus.SUCCEEDED
        ):
            raise ValueError("account-equity trace publication requires a successful sandbox")
        if manifest != reference.artifact:
            raise ValueError("artifact manifest does not match the verified account-equity trace")
        path = sandbox_account_equity_trace_path(sandbox_plan)
        if path is None:
            raise ValueError("sandbox plan has no account-equity trace mount")
        verify_nautilus_account_equity_trace_file(
            reference,
            path,
            expected_events=None,
            max_stream_bytes=min(
                sandbox_plan.output_limit_bytes,
                MAX_NAUTILUS_ACCOUNT_EQUITY_TRACE_BYTES,
            ),
        )
        return await self.publish_file(manifest, path, committed_at=committed_at)

    async def publish_nautilus_native_reports(
        self,
        manifest: ArtifactManifest,
        sandbox_plan: SandboxCommandPlan,
        run_result: NautilusRunResult,
        *,
        committed_at: datetime,
    ) -> ArtifactPublicationResolution:
        """Publish native account/order/fill/position reports without buffering."""

        if not isinstance(manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if not isinstance(sandbox_plan, SandboxCommandPlan):
            raise TypeError("sandbox_plan must be a SandboxCommandPlan")
        if not isinstance(run_result, NautilusRunResult):
            raise TypeError("run_result must be a NautilusRunResult")
        reference = run_result.native_reports
        if reference is None:
            raise ValueError("Nautilus run is missing its verified native reports")
        if run_result.sandbox_plan_fingerprint != sandbox_plan.fingerprint:
            raise ValueError("Nautilus run result does not match its sandbox plan")
        if run_result.sandbox_result is None or (
            run_result.sandbox_result.status is not SandboxRunStatus.SUCCEEDED
        ):
            raise ValueError("native report publication requires a successful sandbox")
        if manifest != reference.artifact:
            raise ValueError("artifact manifest does not match the verified native reports")
        path = sandbox_native_reports_path(sandbox_plan)
        if path is None:
            raise ValueError("sandbox plan has no native report mount")
        verify_nautilus_native_reports_file(
            reference,
            path,
            max_stream_bytes=min(
                sandbox_plan.output_limit_bytes,
                MAX_NAUTILUS_NATIVE_REPORTS_BYTES,
            ),
        )
        return await self.publish_file(manifest, path, committed_at=committed_at)

    async def _finalize_storage(
        self,
        manifest: ArtifactManifest,
        storage: ArtifactStoreResolution,
        *,
        already_committed: bool,
        committed_at: datetime,
    ) -> ArtifactPublicationResolution:
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
                artifact_plan=plan,
            )
        if commit.decision is ArtifactCommitDecision.REPLAY_EXISTING:
            return ArtifactPublicationResolution(
                ArtifactPublicationDecision.REPLAY_EXISTING,
                storage,
                commit,
                artifact_plan=plan,
            )
        return ArtifactPublicationResolution(
            ArtifactPublicationDecision.REJECT,
            storage,
            commit,
            rejection_reason=commit.rejection_reason or "artifact commit was rejected",
        )


class LocalArtifactRetentionService:
    """Coordinate explicit PostgreSQL retention decisions with byte collection."""

    def __init__(self, store: LocalArtifactStore, resolver: ArtifactRetentionResolver) -> None:
        if not isinstance(store, LocalArtifactStore):
            raise TypeError("store must be a LocalArtifactStore")
        if not callable(getattr(resolver, "resolve", None)):
            raise TypeError("resolver must provide a resolve method")
        self._store = store
        self._resolver = resolver

    @property
    def store(self) -> LocalArtifactStore:
        return self._store

    async def collect(
        self,
        manifest: ArtifactManifest,
        *,
        observed_at: datetime,
    ) -> ArtifactByteResolution:
        """Evaluate retention at an explicit instant, then collect eligible bytes."""

        if not isinstance(manifest, ArtifactManifest):
            raise TypeError("manifest must be an ArtifactManifest")
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        retention = await self._resolver.resolve(
            manifest_fingerprint=content_digest(manifest),
            observed_at=observed_at,
        )
        if not isinstance(retention, ArtifactRetentionResolution):
            raise TypeError("resolver.resolve must return an ArtifactRetentionResolution")
        return self._store.collect(manifest, retention)


class LocalArtifactCleanupService:
    """Reconcile local bytes against the authoritative commit ledger."""

    def __init__(self, store: LocalArtifactStore, committer: ArtifactCommitLedgerProvider) -> None:
        if not isinstance(store, LocalArtifactStore):
            raise TypeError("store must be a LocalArtifactStore")
        if not callable(getattr(committer, "load_ledger", None)):
            raise TypeError("committer must provide load_ledger")
        self._store = store
        self._committer = committer

    @property
    def store(self) -> LocalArtifactStore:
        return self._store

    async def cleanup_uncommitted(
        self,
        *,
        observed_at: datetime,
        minimum_age: timedelta,
    ) -> ArtifactCleanupResolution:
        """Run one bounded reconciliation at an explicit instant."""

        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if not isinstance(minimum_age, timedelta) or minimum_age.total_seconds() < 0:
            raise ValueError("minimum_age must be a non-negative timedelta")
        ledger = await self._committer.load_ledger()
        if not isinstance(ledger, ArtifactCommitLedger):
            raise TypeError("committer.load_ledger must return an ArtifactCommitLedger")
        return self._store.cleanup_uncommitted(
            {record.storage_key for record in ledger.records},
            observed_at=observed_at,
            minimum_age=minimum_age,
        )


class ArtifactCleanupScheduler:
    """Cancellable periodic artifact reconciliation with explicit age policy."""

    def __init__(
        self,
        service: LocalArtifactCleanupService,
        *,
        clock: Callable[[], datetime],
        minimum_age: timedelta,
        interval_seconds: float = 300.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if not callable(getattr(service, "cleanup_uncommitted", None)):
            raise TypeError("service must provide cleanup_uncommitted")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not isinstance(minimum_age, timedelta) or minimum_age.total_seconds() < 0:
            raise ValueError("minimum_age must be a non-negative timedelta")
        if (
            not isinstance(interval_seconds, int | float)
            or isinstance(interval_seconds, bool)
            or not math.isfinite(float(interval_seconds))
            or interval_seconds <= 0
        ):
            raise ValueError("interval_seconds must be a finite positive number")
        if not callable(sleep):
            raise TypeError("sleep must be callable")
        self._service = service
        self._clock = clock
        self._minimum_age = minimum_age
        self._interval_seconds = float(interval_seconds)
        self._sleep = sleep

    async def run_once(self) -> ArtifactCleanupResolution:
        now = self._clock()
        if not isinstance(now, datetime):
            raise TypeError("clock must return a datetime")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return await self._service.cleanup_uncommitted(
            observed_at=now,
            minimum_age=self._minimum_age,
        )

    async def run(
        self, stop_event: Any, *, max_cycles: int | None = None
    ) -> tuple[ArtifactCleanupResolution, ...]:
        if not callable(getattr(stop_event, "is_set", None)):
            raise TypeError("stop_event must provide is_set")
        if max_cycles is not None and (
            not isinstance(max_cycles, int) or isinstance(max_cycles, bool) or max_cycles < 1
        ):
            raise ValueError("max_cycles must be a positive integer when provided")
        results: list[ArtifactCleanupResolution] = []
        while not stop_event.is_set() and (max_cycles is None or len(results) < max_cycles):
            results.append(await self.run_once())
            if not stop_event.is_set() and (max_cycles is None or len(results) < max_cycles):
                await self._sleep(self._interval_seconds)
        return tuple(results)


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


def create_local_artifact_retention_service(
    root: str | os.PathLike[str],
    session_factory: Any,
) -> LocalArtifactRetentionService:
    """Build the local filesystem/PostgreSQL retention composition."""

    return LocalArtifactRetentionService(
        LocalArtifactStore(root),
        PostgresArtifactRetentionAdapter(session_factory),
    )


def create_local_artifact_cleanup_service(
    root: str | os.PathLike[str],
    session_factory: Any,
) -> LocalArtifactCleanupService:
    """Build a local artifact reconciler over the PostgreSQL commit ledger."""

    return LocalArtifactCleanupService(
        LocalArtifactStore(root),
        PostgresArtifactCommitAdapter(session_factory),
    )


__all__ = [
    "ArtifactCommitter",
    "ArtifactCommitLedgerProvider",
    "ArtifactRetentionResolver",
    "ArtifactPublicationDecision",
    "ArtifactPublicationResolution",
    "LocalArtifactPublicationService",
    "LocalArtifactRetentionService",
    "LocalArtifactCleanupService",
    "ArtifactCleanupScheduler",
    "create_local_artifact_publication_service",
    "create_local_artifact_retention_service",
    "create_local_artifact_cleanup_service",
]
