"""Storage-neutral dispatch envelopes and idempotency decisions."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


class DispatchDecision(StrEnum):
    ENQUEUE = "enqueue"
    REPLAY_EXISTING = "replay_existing"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"


@dataclass(frozen=True, slots=True)
class DispatchRequest:
    """Immutable request identity used by a durable outbox/queue adapter."""

    idempotency_key: str
    attempt_id: str
    payload_digest: str
    queue_name: str
    created_at: datetime

    def __post_init__(self) -> None:
        for name in ("idempotency_key", "attempt_id", "queue_name"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"dispatch {name} must not be empty")
        if len(self.idempotency_key) > 256:
            raise ValueError("dispatch idempotency_key must not exceed 256 characters")
        require_sha256_digest(self.payload_digest, field_name="payload_digest")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("dispatch created_at must be timezone-aware")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class DispatchEnvelope:
    """A content-addressed message; publication is owned by the adapter."""

    message_id: str
    request: DispatchRequest
    delivery_count: int = 0

    def __post_init__(self) -> None:
        require_sha256_digest(self.message_id, field_name="message_id")
        if not isinstance(self.request, DispatchRequest):
            raise TypeError("dispatch envelope request must be a DispatchRequest")
        if self.message_id != self.request.fingerprint:
            raise ValueError("dispatch message_id must equal its request fingerprint")
        if not isinstance(self.delivery_count, int) or isinstance(self.delivery_count, bool):
            raise ValueError("dispatch delivery_count must be an integer")
        if self.delivery_count < 0:
            raise ValueError("dispatch delivery_count must not be negative")


@dataclass(frozen=True, slots=True)
class DispatchResolution:
    """Pure result of resolving an idempotency key against prior requests."""

    decision: DispatchDecision
    request_fingerprint: str
    existing_fingerprint: str | None = None

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        if self.existing_fingerprint is not None:
            require_sha256_digest(self.existing_fingerprint, field_name="existing_fingerprint")


def resolve_idempotent_dispatch(
    request: DispatchRequest,
    prior_requests: Sequence[DispatchRequest],
) -> DispatchResolution:
    """Resolve enqueue/replay/conflict without mutating a queue or database."""

    if not isinstance(request, DispatchRequest):
        raise TypeError("request must be a DispatchRequest")
    if not isinstance(prior_requests, Sequence):
        raise TypeError("prior_requests must be a sequence")
    previous = tuple(prior_requests)
    if any(not isinstance(item, DispatchRequest) for item in previous):
        raise TypeError("prior_requests must contain DispatchRequest records")
    matching = tuple(item for item in previous if item.idempotency_key == request.idempotency_key)
    if not matching:
        return DispatchResolution(DispatchDecision.ENQUEUE, request.fingerprint)
    existing = matching[0]
    if any(item.fingerprint != existing.fingerprint for item in matching[1:]):
        raise ValueError("prior dispatch requests contain conflicting idempotency records")
    decision = (
        DispatchDecision.REPLAY_EXISTING
        if existing.fingerprint == request.fingerprint
        else DispatchDecision.IDEMPOTENCY_CONFLICT
    )
    return DispatchResolution(decision, request.fingerprint, existing.fingerprint)


def build_dispatch_envelope(request: DispatchRequest) -> DispatchEnvelope:
    """Build the deterministic message identity for an outbox publication."""

    if not isinstance(request, DispatchRequest):
        raise TypeError("request must be a DispatchRequest")
    return DispatchEnvelope(message_id=request.fingerprint, request=request)
