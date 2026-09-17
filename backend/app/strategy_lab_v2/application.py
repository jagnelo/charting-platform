"""Application wiring for the Strategy Lab v2 API.

The package-level router and PostgreSQL adapters deliberately remain
registration-neutral.  This module is the small application-owned seam that
connects them to the existing authenticated user dependency and async session
factory.  It does not run migrations, start workers, or import an execution
engine; those lifecycle concerns remain explicit follow-up gates.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib import import_module
from typing import Any

from app.strategy_lab_v2.api_resources import (
    ApiResourceType,
    ResourceCollection,
    ResourceDocument,
)
from app.strategy_lab_v2.api_router import (
    StrategyLabApiAdapter,
    SubmissionServiceResult,
    create_strategy_lab_router,
)
from app.strategy_lab_v2.commands import ExecutionCommand, ExecutionCommandResolution
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.submissions import SubmissionRequest


@dataclass(frozen=True, slots=True)
class _PrincipalIdentity:
    """String owner identity shared by every v2 persistence adapter."""

    id: str


def _principal_identity(principal: Any) -> _PrincipalIdentity:
    """Convert the existing integer-backed ``User.id`` to the storage key.

    The package contracts use opaque string owner keys.  Keeping this
    conversion at the application boundary avoids leaking ORM identity types
    into the engine-neutral adapters and makes all reads/writes use the same
    representation.
    """

    value = getattr(principal, "id", principal)
    if value is None or isinstance(value, bool) or not isinstance(value, str | int):
        raise ValueError("authenticated principal identity is required")
    identity = str(value).strip()
    if not identity:
        raise ValueError("authenticated principal identity is required")
    return _PrincipalIdentity(identity)


class PostgresStrategyLabV2Adapter(StrategyLabApiAdapter):
    """Compose the v2 API operations over the additive PostgreSQL adapters."""

    def __init__(
        self,
        session_factory: Callable[[], Any],
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._persistence = PostgresStrategyLabV2Persistence.build(session_factory, clock=clock)
        self._resources = self._persistence.resources
        self._submissions = self._persistence.submissions
        self._execution_state = self._persistence.execution_state
        self._commands = self._persistence.commands

    async def list_resources(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        limit: int,
        cursor: Any,
        request_id: str,
    ) -> ResourceCollection:
        return await self._resources.list_resources(
            principal=_principal_identity(principal),
            resource_type=resource_type,
            limit=limit,
            cursor=cursor,
            request_id=request_id,
        )

    async def get_resource(
        self,
        *,
        principal: Any,
        resource_type: ApiResourceType,
        resource_id: str,
    ) -> ResourceDocument | None:
        return await self._resources.get_resource(
            principal=_principal_identity(principal),
            resource_type=resource_type,
            resource_id=resource_id,
        )

    async def submit(
        self,
        *,
        principal: Any,
        request_id: str,
        request: SubmissionRequest,
        payload: Mapping[str, Any],
    ) -> SubmissionServiceResult:
        return await self._submissions.submit(
            principal=_principal_identity(principal),
            request_id=request_id,
            request=request,
            payload=payload,
        )

    async def command(
        self,
        *,
        principal: Any,
        request_id: str,
        idempotency_key: str,
        command: ExecutionCommand,
    ) -> ExecutionCommandResolution:
        return await self._commands.command(
            principal=_principal_identity(principal),
            request_id=request_id,
            idempotency_key=idempotency_key,
            command=command,
        )


_default_adapter: PostgresStrategyLabV2Adapter | None = None


def get_strategy_lab_v2_adapter() -> StrategyLabApiAdapter:
    """FastAPI dependency returning the process-local v2 adapter."""

    global _default_adapter
    if _default_adapter is None:
        # Keep the package import-safe for contract tests and worker tooling;
        # the application graph is resolved only when FastAPI asks for the
        # registered dependency.
        session_factory = getattr(import_module("app.database"), "AsyncSessionLocal")
        _default_adapter = PostgresStrategyLabV2Adapter(session_factory)
    return _default_adapter


def create_registered_strategy_lab_v2_router():
    """Build the authenticated, application-registered v2 router."""

    principal_dependency = getattr(
        import_module("app.auth.dependencies"), "get_current_user"
    )

    return create_strategy_lab_router(
        adapter_dependency=get_strategy_lab_v2_adapter,
        principal_dependency=principal_dependency,
    )


__all__ = [
    "PostgresStrategyLabV2Adapter",
    "create_registered_strategy_lab_v2_router",
    "get_strategy_lab_v2_adapter",
]
