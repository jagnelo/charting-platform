"""Resolve frozen snapshot tapes inside one authenticated owner boundary."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, Protocol, cast

from app.strategy_lab_v2.api_resources import ApiResourceType
from app.strategy_lab_v2.canonical import require_sha256_digest
from app.strategy_lab_v2.contracts import DataSnapshot
from app.strategy_lab_v2.event_tape_artifacts import (
    FrozenEventTapeArtifactResolver,
    FrozenEventTapeStreamResolution,
    FrozenEventTapeWindowResolution,
)
from app.strategy_lab_v2.sdk import StrategySdkManifest


class FrozenSnapshotDomainReader(Protocol):
    """Owner-scoped immutable domain reads used by a local simulation worker."""

    async def get_domain_contracts_by_fingerprint(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        fingerprints: Sequence[str],
    ) -> Mapping[str, Any]: ...


def _default_offloader(function: Callable[..., Any], *args: Any) -> Awaitable[Any]:
    return asyncio.to_thread(function, *args)


class AuthenticatedFrozenEventTapeResolver:
    """Resolve a snapshot fingerprint to its verified local event-tape artifact.

    Snapshot metadata is read through the authenticated domain boundary, and
    every series byte is subsequently verified by the existing content-addressed
    artifact resolver. The resolver never queries a provider or substitutes a
    current/unfrozen data source. Expensive local decoding and tape publication
    run off the async worker's event loop.
    """

    def __init__(
        self,
        reader: FrozenSnapshotDomainReader,
        artifact_resolver: FrozenEventTapeArtifactResolver,
        *,
        principal: Any,
        offloader: Callable[..., Any] | None = None,
    ) -> None:
        if not callable(getattr(reader, "get_domain_contracts_by_fingerprint", None)):
            raise TypeError("reader must provide owner-scoped domain fingerprint reads")
        if not isinstance(artifact_resolver, FrozenEventTapeArtifactResolver):
            raise TypeError("artifact_resolver must use FrozenEventTapeArtifactResolver")
        self._reader = reader
        self._artifact_resolver = artifact_resolver
        self._principal = principal
        self._offloader = cast(
            Callable[..., Any],
            _default_offloader if offloader is None else offloader,
        )

    async def resolve(
        self,
        snapshot_fingerprint: str,
        manifest: StrategySdkManifest,
    ) -> FrozenEventTapeStreamResolution:
        """Load exactly one owner's snapshot and verify its required source tape."""

        snapshot = await self._load_snapshot(snapshot_fingerprint, manifest)

        offloaded = self._offloader(
            self._artifact_resolver.resolve,
            snapshot,
            manifest,
        )
        resolution = await offloaded if inspect.isawaitable(offloaded) else offloaded
        if not isinstance(resolution, FrozenEventTapeStreamResolution):
            raise TypeError("frozen tape resolver returned an invalid stream resolution")
        if (
            resolution.snapshot_fingerprint != snapshot_fingerprint
            or resolution.manifest_fingerprint != manifest.fingerprint
        ):
            raise ValueError("verified frozen event tape differs from its requested inputs")
        return resolution

    async def resolve_bounded_window(
        self,
        snapshot_fingerprint: str,
        manifest: StrategySdkManifest,
        *,
        through_event_id: str | None = None,
    ) -> FrozenEventTapeWindowResolution:
        """Resolve one owner's frozen snapshot to its bounded SDK history tail."""

        snapshot = await self._load_snapshot(snapshot_fingerprint, manifest)
        offloaded = self._offloader(
            lambda: self._artifact_resolver.resolve_bounded_window(
                snapshot,
                manifest,
                through_event_id=through_event_id,
            )
        )
        resolution = await offloaded if inspect.isawaitable(offloaded) else offloaded
        if not isinstance(resolution, FrozenEventTapeWindowResolution):
            raise TypeError("frozen tape resolver returned an invalid bounded window")
        if (
            resolution.snapshot_fingerprint != snapshot_fingerprint
            or resolution.manifest_fingerprint != manifest.fingerprint
            or resolution.through_event_id != through_event_id
        ):
            raise ValueError("bounded frozen history differs from its requested inputs")
        return resolution

    async def _load_snapshot(
        self,
        snapshot_fingerprint: str,
        manifest: StrategySdkManifest,
    ) -> DataSnapshot:
        require_sha256_digest(snapshot_fingerprint, field_name="snapshot_fingerprint")
        if not isinstance(manifest, StrategySdkManifest):
            raise TypeError("manifest must use StrategySdkManifest")
        snapshots = await self._reader.get_domain_contracts_by_fingerprint(
            principal=self._principal,
            resource_type=ApiResourceType.SNAPSHOT,
            fingerprints=(snapshot_fingerprint,),
        )
        if not isinstance(snapshots, Mapping):
            raise TypeError("snapshot reader returned an invalid domain mapping")
        if set(snapshots) != {snapshot_fingerprint}:
            raise ValueError("owner-scoped frozen snapshot is unavailable")
        snapshot = snapshots[snapshot_fingerprint]
        if not isinstance(snapshot, DataSnapshot):
            raise TypeError("snapshot reader returned an invalid DataSnapshot")
        if snapshot.fingerprint != snapshot_fingerprint:
            raise ValueError("owner-scoped frozen snapshot fingerprint does not match its key")
        return snapshot


__all__ = ["AuthenticatedFrozenEventTapeResolver", "FrozenSnapshotDomainReader"]
