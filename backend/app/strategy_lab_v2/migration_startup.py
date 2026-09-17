"""Explicit, idempotent Alembic startup migration composition.

The v2 adapters and router remain import-safe and never mutate the database.
This service is the application-owned hook a local Compose/API entrypoint can
call before accepting work.  It runs the configured Alembic target off the
event loop, serializes concurrent callers, and publishes only stable
exception-type evidence on failure.
"""

from __future__ import annotations

import asyncio
import inspect
import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, cast

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


def _safe_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    if any(character in value for character in "\x00\r\n"):
        raise ValueError(f"{field_name} must not contain control characters")


class MigrationDecision(StrEnum):
    APPLIED = "applied"
    REPLAY_EXISTING = "replay_existing"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MigrationResolution:
    """Typed result of one startup migration attempt."""

    request_fingerprint: str
    decision: MigrationDecision
    target_revision: str
    error_digest: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        if not isinstance(self.decision, MigrationDecision):
            raise TypeError("decision must be a MigrationDecision")
        _safe_text(self.target_revision, "target_revision")
        if self.error_digest is not None:
            require_sha256_digest(self.error_digest, field_name="error_digest")
        if self.decision is MigrationDecision.FAILED and self.error_digest is None:
            raise ValueError("failed migration resolutions require an error digest")
        if self.decision is MigrationDecision.APPLIED and self.error_digest is not None:
            raise ValueError("successful migration resolutions cannot contain an error digest")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


MigrationRunner = Any


class StrategyLabV2MigrationService:
    """Run one configured Alembic target at most once per service instance."""

    def __init__(
        self,
        database_url: str,
        *,
        script_location: str | os.PathLike[str],
        target_revision: str = "head",
        runner: MigrationRunner | None = None,
    ) -> None:
        _safe_text(database_url, "database_url")
        if not database_url.startswith(("postgresql://", "postgresql+")):
            raise ValueError("database_url must use a PostgreSQL URL")
        raw_script = os.fspath(script_location)
        _safe_text(raw_script, "script_location")
        script_path = Path(raw_script)
        if not script_path.is_absolute():
            raise ValueError("script_location must be an absolute path")
        _safe_text(target_revision, "target_revision")
        if any(not (character.isalnum() or character in "_.-") for character in target_revision):
            raise ValueError("target_revision contains unsafe characters")
        if runner is not None and not callable(runner):
            raise TypeError("runner must be callable")
        self._database_url = database_url
        self._script_location = str(script_path)
        self._target_revision = target_revision
        self._runner = runner or _run_alembic_upgrade
        self._request_fingerprint = content_digest(
            {
                "database_url": database_url,
                "script_location": self._script_location,
                "target_revision": target_revision,
            }
        )
        self._lock = asyncio.Lock()
        self._resolution: MigrationResolution | None = None

    @property
    def request_fingerprint(self) -> str:
        return self._request_fingerprint

    async def upgrade(self) -> MigrationResolution:
        """Apply the configured target or replay the exact result."""

        async with self._lock:
            if self._resolution is not None:
                return MigrationResolution(
                    self._resolution.request_fingerprint,
                    MigrationDecision.REPLAY_EXISTING,
                    self._resolution.target_revision,
                    self._resolution.error_digest,
                )
            try:
                runner = cast(Callable[[str, str, str], Any], self._runner)
                if inspect.iscoroutinefunction(runner):
                    result = runner(
                        self._database_url,
                        self._script_location,
                        self._target_revision,
                    )
                else:
                    result = await asyncio.to_thread(
                        runner,
                        self._database_url,
                        self._script_location,
                        self._target_revision,
                    )
                if inspect.isawaitable(result):
                    await result
            except Exception as error:  # pragma: no cover - migration boundary
                resolution = MigrationResolution(
                    self._request_fingerprint,
                    MigrationDecision.FAILED,
                    self._target_revision,
                    _error_digest(error),
                )
            else:
                resolution = MigrationResolution(
                    self._request_fingerprint,
                    MigrationDecision.APPLIED,
                    self._target_revision,
                )
            self._resolution = resolution
            return resolution


def create_strategy_lab_v2_migration_service(
    database_url: str,
    *,
    script_location: str | os.PathLike[str],
    target_revision: str = "head",
) -> StrategyLabV2MigrationService:
    """Build the explicit startup migration service without running it."""

    return StrategyLabV2MigrationService(
        database_url,
        script_location=script_location,
        target_revision=target_revision,
    )


def _run_alembic_upgrade(database_url: str, script_location: str, target_revision: str) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", script_location)
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, target_revision)


def _error_digest(error: BaseException) -> str:
    return content_digest(
        {
            "type": f"{type(error).__module__}.{type(error).__qualname__}",
            "version": "strategy-lab.migration-startup.error.v1",
        }
    )


__all__ = [
    "MigrationDecision",
    "MigrationResolution",
    "StrategyLabV2MigrationService",
    "create_strategy_lab_v2_migration_service",
]
