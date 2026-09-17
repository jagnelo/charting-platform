"""Idempotent resource-creation contracts for the Strategy Lab v2 API."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.strategy_lab_v2.api_resources import ApiResourceType, ResourceDocument
from app.strategy_lab_v2.canonical import content_digest, freeze_json, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class ResourceMutationDecision(StrEnum):
    ACCEPT = "accept"
    REPLAY_EXISTING = "replay_existing"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class ResourceMutationRequest:
    """Client intent for one idempotent resource creation."""

    resource_type: ApiResourceType
    idempotency_key: str
    payload: Mapping[str, Any]
    requested_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.resource_type, ApiResourceType):
            raise TypeError("resource_type must be an ApiResourceType")
        _nonempty(self.idempotency_key, "idempotency_key")
        if len(self.idempotency_key) > 256:
            raise ValueError("idempotency_key must not exceed 256 characters")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        frozen = freeze_json(self.payload)
        if not isinstance(frozen, Mapping):
            raise TypeError("payload must be a mapping")
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")
        object.__setattr__(self, "payload", frozen)
        object.__setattr__(self, "requested_at", self.requested_at.astimezone(UTC))

    @property
    def payload_digest(self) -> str:
        return content_digest(self.payload)

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "idempotency_key": self.idempotency_key,
                "payload_digest": self.payload_digest,
                "resource_type": self.resource_type,
            }
        )


@dataclass(frozen=True, slots=True)
class ResourceMutationReceipt:
    """Durable response identity for an accepted resource creation."""

    request: ResourceMutationRequest
    resource: ResourceDocument
    accepted_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.request, ResourceMutationRequest):
            raise TypeError("receipt request must be a ResourceMutationRequest")
        if not isinstance(self.resource, ResourceDocument):
            raise TypeError("receipt resource must be a ResourceDocument")
        if self.resource.identity.resource_type is not self.request.resource_type:
            raise ValueError("receipt resource type must match the mutation request")
        if self.accepted_at.tzinfo is None or self.accepted_at.utcoffset() is None:
            raise ValueError("receipt accepted_at must be timezone-aware")
        accepted_at = self.accepted_at.astimezone(UTC)
        if accepted_at < self.request.requested_at:
            raise ValueError("receipt accepted_at cannot precede the mutation request")
        object.__setattr__(self, "accepted_at", accepted_at)

    @property
    def mutation_id(self) -> str:
        return self.request.fingerprint

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class ResourceMutationResolution:
    """Pure result of resolving an idempotency key against prior receipts."""

    decision: ResourceMutationDecision
    request_fingerprint: str
    existing_receipt: ResourceMutationReceipt | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, ResourceMutationDecision):
            raise TypeError("decision must be a ResourceMutationDecision")
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        if self.existing_receipt is not None and not isinstance(
            self.existing_receipt, ResourceMutationReceipt
        ):
            raise TypeError("existing_receipt must be a ResourceMutationReceipt")
        if self.decision in {
            ResourceMutationDecision.REPLAY_EXISTING,
            ResourceMutationDecision.IDEMPOTENCY_CONFLICT,
        } and self.existing_receipt is None:
            raise ValueError("replay/conflict resolutions require an existing receipt")
        if self.decision is ResourceMutationDecision.REJECT:
            if self.existing_receipt is not None or not self.rejection_reason:
                raise ValueError("rejected mutations require a reason and no receipt")
        elif self.rejection_reason:
            raise ValueError("accepted mutations cannot contain a rejection reason")

    @property
    def http_status(self) -> int:
        if self.decision is ResourceMutationDecision.IDEMPOTENCY_CONFLICT:
            return 409
        if self.decision is ResourceMutationDecision.REJECT:
            return 422
        return 202


def create_resource_mutation_receipt(
    request: ResourceMutationRequest,
    resource: ResourceDocument,
    *,
    accepted_at: datetime,
) -> ResourceMutationReceipt:
    """Create a 202 resource receipt without persistence or dispatch."""

    if not isinstance(request, ResourceMutationRequest):
        raise TypeError("request must be a ResourceMutationRequest")
    if not isinstance(resource, ResourceDocument):
        raise TypeError("resource must be a ResourceDocument")
    return ResourceMutationReceipt(request, resource, accepted_at)


def resolve_resource_mutation(
    request: ResourceMutationRequest,
    prior_receipts: Sequence[ResourceMutationReceipt] = (),
) -> ResourceMutationResolution:
    """Resolve accept/replay/conflict for one resource mutation.

    Persistence adapters must atomically store the accepted receipt. Conflicting
    historical records fail closed instead of selecting an arbitrary resource.
    """

    if not isinstance(request, ResourceMutationRequest):
        raise TypeError("request must be a ResourceMutationRequest")
    if not isinstance(prior_receipts, Sequence) or isinstance(prior_receipts, str | bytes):
        raise TypeError("prior_receipts must be a sequence")
    previous = tuple(prior_receipts)
    if any(not isinstance(item, ResourceMutationReceipt) for item in previous):
        raise TypeError("prior_receipts must contain ResourceMutationReceipt values")
    matching = tuple(
        item
        for item in previous
        if item.request.idempotency_key == request.idempotency_key
    )
    if not matching:
        return ResourceMutationResolution(
            ResourceMutationDecision.ACCEPT,
            request.fingerprint,
        )
    existing = matching[0]
    if any(item.request.fingerprint != existing.request.fingerprint for item in matching[1:]):
        raise ValueError("prior resource receipts contain conflicting idempotency records")
    decision = (
        ResourceMutationDecision.REPLAY_EXISTING
        if existing.request.fingerprint == request.fingerprint
        else ResourceMutationDecision.IDEMPOTENCY_CONFLICT
    )
    return ResourceMutationResolution(decision, request.fingerprint, existing)


__all__ = [
    "ResourceMutationDecision",
    "ResourceMutationReceipt",
    "ResourceMutationRequest",
    "ResourceMutationResolution",
    "create_resource_mutation_receipt",
    "resolve_resource_mutation",
]
