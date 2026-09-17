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
    ResourceMutationServiceResult,
    StrategyLabApiAdapter,
    SubmissionServiceResult,
    create_strategy_lab_router,
)
from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.commands import ExecutionCommand, ExecutionCommandResolution
from app.strategy_lab_v2.persistence import PostgresStrategyLabV2Persistence
from app.strategy_lab_v2.resource_domains import normalize_resource_attributes
from app.strategy_lab_v2.resource_mutations import (
    ResourceMutationDecision,
    ResourceMutationRequest,
    ResourceMutationResolution,
    create_resource_mutation_receipt,
)
from app.strategy_lab_v2.storage import (
    AggregateKey,
    AggregateMutation,
    StorageTransactionDecision,
    StorageTransactionRequest,
)
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
        self._clock = clock
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

    async def create_resource(
        self,
        *,
        principal: Any,
        request_id: str,
        request: ResourceMutationRequest,
    ) -> ResourceMutationServiceResult:
        """Persist one generic resource envelope through aggregate CAS storage.

        Domain-specific validation remains owned by future command adapters.
        This bridge nevertheless supplies a durable owner-bound create/replay
        boundary for the registration-neutral API resource envelope.
        """

        owner = _principal_identity(principal)
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id must not be empty")
        if not isinstance(request, ResourceMutationRequest):
            raise TypeError("request must be a ResourceMutationRequest")
        attributes = request.payload.get("attributes")
        relationships = request.payload.get("relationships", {})
        meta = request.payload.get("meta", {})
        if not isinstance(attributes, Mapping):
            raise ValueError("resource attributes must be a mapping")
        if not isinstance(relationships, Mapping) or not isinstance(meta, Mapping):
            raise ValueError("resource relationships and meta must be mappings")
        normalized_domain = normalize_resource_attributes(request.resource_type, attributes)
        attributes = normalized_domain.attributes
        state_meta = dict(meta)
        if normalized_domain.domain_fingerprint is not None:
            declared_domain_fingerprint = state_meta.get("domain_fingerprint")
            if (
                declared_domain_fingerprint is not None
                and declared_domain_fingerprint != normalized_domain.domain_fingerprint
            ):
                raise ValueError("resource meta domain_fingerprint does not match its attributes")
            state_meta["domain_fingerprint"] = normalized_domain.domain_fingerprint
        requested_id = attributes.get("resource_id", attributes.get("id"))
        if requested_id is not None and (
            not isinstance(requested_id, str) or not requested_id.strip()
        ):
            raise ValueError("resource_id must be a non-empty string when supplied")
        resource_identity_payload: dict[str, Any] = {
            "resource_type": request.resource_type,
            "attributes": attributes,
        }
        if normalized_domain.domain_fingerprint is None:
            resource_identity_payload.update({"relationships": relationships, "meta": meta})
        resource_id = requested_id or content_digest(resource_identity_payload)
        aggregate_key = AggregateKey(request.resource_type.value, resource_id)
        existing = await self._persistence.aggregate_store.get(aggregate_key)
        existing_state = existing.state if existing is not None else None
        replaying_known_mutation = (
            isinstance(existing_state, Mapping)
            and str(existing_state.get("owner_id")) == owner.id
            and existing_state.get("mutation_fingerprint") == request.fingerprint
        )
        if replaying_known_mutation:
            accepted_at = existing_state.get("mutation_accepted_at")
            if not isinstance(accepted_at, datetime):
                return ResourceMutationServiceResult(
                    ResourceMutationResolution(
                        ResourceMutationDecision.REJECT,
                        request.fingerprint,
                        rejection_reason=(
                            "replayed resource aggregate is missing its accepted timestamp"
                        ),
                    )
                )
            if accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
                return ResourceMutationServiceResult(
                    ResourceMutationResolution(
                        ResourceMutationDecision.REJECT,
                        request.fingerprint,
                        rejection_reason=(
                            "replayed resource aggregate has an invalid accepted timestamp"
                        ),
                    )
                )
            accepted_at = accepted_at.astimezone(UTC)
        else:
            accepted_at = self._clock()
            if not isinstance(accepted_at, datetime):
                raise TypeError("clock must return a datetime")
            if accepted_at.tzinfo is None or accepted_at.utcoffset() is None:
                raise ValueError("clock must return a timezone-aware datetime")
            accepted_at = accepted_at.astimezone(UTC)
            if accepted_at < request.requested_at:
                raise ValueError("clock cannot precede the mutation request")
        state = {
            "owner_id": owner.id,
            "resource_type": request.resource_type.value,
            "resource_id": resource_id,
            "schema_version": 1,
            "sort_value": resource_id,
            "mutation_fingerprint": request.fingerprint,
            "domain_fingerprint": normalized_domain.domain_fingerprint,
            # Keep the response timestamp in the aggregate so a replay can
            # reconstruct the exact durable receipt after a process restart.
            "mutation_accepted_at": accepted_at,
            "attributes": attributes,
            "relationships": relationships,
            "meta": state_meta,
        }
        storage_request_id = content_digest(
            {
                "idempotency_key": request.idempotency_key,
                "resource_type": request.resource_type,
                "owner_id": owner.id,
            }
        )
        storage_request = StorageTransactionRequest(
            storage_request_id,
            (
                AggregateMutation(
                    aggregate_key,
                    state,
                ),
            ),
        )
        resolved = await self._persistence.aggregate_store.apply(storage_request)
        committed = next(
            (
                aggregate
                for aggregate in resolved.aggregates
                if aggregate.key == aggregate_key
            ),
            None,
        )
        if committed is None:
            return ResourceMutationServiceResult(
                ResourceMutationResolution(
                    ResourceMutationDecision.REJECT,
                    request.fingerprint,
                    rejection_reason=resolved.rejection_reason
                    or "resource mutation did not return a committed aggregate",
                )
            )
        aggregate_state = committed.state
        if not isinstance(aggregate_state, Mapping):
            return ResourceMutationServiceResult(
                ResourceMutationResolution(
                    ResourceMutationDecision.REJECT,
                    request.fingerprint,
                    rejection_reason="resource aggregate state is not a mapping",
                )
            )
        if str(aggregate_state.get("owner_id")) != owner.id:
            return ResourceMutationServiceResult(
                ResourceMutationResolution(
                    ResourceMutationDecision.REJECT,
                    request.fingerprint,
                    rejection_reason="resource aggregate is owned by another principal",
                )
            )
        document = self._resources._project(committed, request.resource_type)
        if resolved.decision is StorageTransactionDecision.APPLY:
            receipt = create_resource_mutation_receipt(
                request,
                document,
                accepted_at=accepted_at,
            )
            return ResourceMutationServiceResult(
                ResourceMutationResolution(
                    ResourceMutationDecision.ACCEPT,
                    request.fingerprint,
                ),
                receipt,
            )
        if resolved.decision is StorageTransactionDecision.REPLAY_EXISTING:
            persisted_accepted_at = aggregate_state.get("mutation_accepted_at")
            if not isinstance(persisted_accepted_at, datetime):
                return ResourceMutationServiceResult(
                    ResourceMutationResolution(
                        ResourceMutationDecision.REJECT,
                        request.fingerprint,
                        rejection_reason=(
                            "replayed resource aggregate is missing its accepted timestamp"
                        ),
                    )
                )
            receipt = create_resource_mutation_receipt(
                request,
                document,
                accepted_at=persisted_accepted_at,
            )
            return ResourceMutationServiceResult(
                ResourceMutationResolution(
                    ResourceMutationDecision.REPLAY_EXISTING,
                    request.fingerprint,
                    receipt,
                ),
                receipt,
            )
        return ResourceMutationServiceResult(
            ResourceMutationResolution(
                ResourceMutationDecision.REJECT,
                request.fingerprint,
                rejection_reason=resolved.rejection_reason
                or "resource mutation conflicts with existing state",
            )
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
