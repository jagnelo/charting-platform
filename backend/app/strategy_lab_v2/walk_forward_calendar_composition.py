"""Production composition for authenticated walk-forward calendar reads."""

from __future__ import annotations

from pathlib import Path

from app.strategy_lab_v2.artifact_store import LocalArtifactStore
from app.strategy_lab_v2.event_tape_artifacts import (
    FrozenEventTapeArtifactResolver,
    FrozenSeriesDecoder,
)
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.strategy_package_resolution import StrategyPackageArtifactResolver
from app.strategy_lab_v2.walk_forward_calendar import AuthenticatedWalkForwardCalendarResolver


def create_walk_forward_calendar_resolver(
    persistence: PostgresStrategyLabV2Persistence,
    artifact_root: Path,
    *,
    runtime_abi: str,
    series_decoder: FrozenSeriesDecoder,
) -> AuthenticatedWalkForwardCalendarResolver:
    """Bind PostgreSQL ownership reads and verified artifact decoders locally.

    The provider-platform owns the concrete frozen-series decoder. This factory
    accepts that narrow implementation but owns the content store, strategy
    package verification, event-tape verification, and owner-scoped DB reader.
    Both resolvers share the same artifact-store instance and root.
    """

    if not isinstance(persistence, PostgresStrategyLabV2Persistence):
        raise TypeError("persistence must be a PostgresStrategyLabV2Persistence")
    if not isinstance(artifact_root, Path) or not artifact_root.is_absolute():
        raise ValueError("artifact_root must be an absolute Path")
    if not isinstance(runtime_abi, str) or not runtime_abi.strip():
        raise ValueError("runtime_abi must not be empty")
    if not callable(getattr(series_decoder, "iter_rows", None)):
        raise TypeError("series_decoder must provide iter_rows(series, source)")

    artifact_store = LocalArtifactStore(artifact_root)
    package_resolver = StrategyPackageArtifactResolver(
        artifact_store,
        runtime_abi=runtime_abi,
    )
    tape_resolver = FrozenEventTapeArtifactResolver(artifact_store, series_decoder)
    return AuthenticatedWalkForwardCalendarResolver(
        persistence.resources,
        package_resolver,
        tape_resolver,
    )


__all__ = ["create_walk_forward_calendar_resolver"]
