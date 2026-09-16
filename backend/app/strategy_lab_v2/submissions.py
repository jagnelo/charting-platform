"""Idempotent asynchronous submission contracts for Strategy Lab v2 routes."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


class SubmissionDecision(StrEnum):
    ACCEPT = "accept"
    REPLAY_EXISTING = "replay_existing"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"


@dataclass(frozen=True, slots=True)
class SubmissionRequest:
    """Client intent for one asynchronous execution operation.

    ``submitted_at`` is operational metadata and is deliberately excluded from
    ``fingerprint`` so a retried request with the same idempotency key and
    payload remains replayable.
    """

    idempotency_key: str
    operation: str
    attempt_id: str
    payload_digest: str
    submitted_at: datetime

    def __post_init__(self) -> None:
        for name in ("idempotency_key", "operation", "attempt_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"submission {name} must not be empty")
        if len(self.idempotency_key) > 256:
            raise ValueError("submission idempotency_key must not exceed 256 characters")
        require_sha256_digest(self.payload_digest, field_name="payload_digest")
        if self.submitted_at.tzinfo is None or self.submitted_at.utcoffset() is None:
            raise ValueError("submission submitted_at must be timezone-aware")

    @property
    def fingerprint(self) -> str:
        return content_digest(
            {
                "attempt_id": self.attempt_id,
                "idempotency_key": self.idempotency_key,
                "operation": self.operation,
                "payload_digest": self.payload_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class SubmissionReceipt:
    """Durable response identity for an accepted asynchronous submission."""

    request: SubmissionRequest
    accepted_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.request, SubmissionRequest):
            raise TypeError("receipt request must be a SubmissionRequest")
        if self.accepted_at.tzinfo is None or self.accepted_at.utcoffset() is None:
            raise ValueError("receipt accepted_at must be timezone-aware")
        if self.accepted_at < self.request.submitted_at:
            raise ValueError("receipt accepted_at cannot precede submission")

    @property
    def submission_id(self) -> str:
        return self.request.fingerprint

    @property
    def http_status(self) -> int:
        return 202

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class SubmissionResolution:
    """Pure result of resolving an idempotency key against prior receipts."""

    decision: SubmissionDecision
    request_fingerprint: str
    existing_receipt: SubmissionReceipt | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, SubmissionDecision):
            raise TypeError("decision must be a SubmissionDecision")
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        if self.existing_receipt is not None and not isinstance(
            self.existing_receipt, SubmissionReceipt
        ):
            raise TypeError("existing_receipt must be a SubmissionReceipt")
        if self.decision is SubmissionDecision.REPLAY_EXISTING and self.existing_receipt is None:
            raise ValueError("replay resolutions require an existing receipt")
        if self.decision is SubmissionDecision.IDEMPOTENCY_CONFLICT and self.existing_receipt is None:
            raise ValueError("conflict resolutions require the existing receipt")

    @property
    def http_status(self) -> int:
        return 409 if self.decision is SubmissionDecision.IDEMPOTENCY_CONFLICT else 202


def create_submission_receipt(
    request: SubmissionRequest, *, accepted_at: datetime
) -> SubmissionReceipt:
    """Create a 202 receipt without persisting or dispatching anything."""

    if not isinstance(request, SubmissionRequest):
        raise TypeError("request must be a SubmissionRequest")
    return SubmissionReceipt(request=request, accepted_at=accepted_at)


def resolve_submission(
    request: SubmissionRequest,
    prior_receipts: Sequence[SubmissionReceipt] = (),
) -> SubmissionResolution:
    """Resolve accept/replay/conflict for an async submission.

    The adapter must atomically persist the accepted receipt after this pure
    decision. Contradictory historical receipts fail closed rather than
    selecting an arbitrary response.
    """

    if not isinstance(request, SubmissionRequest):
        raise TypeError("request must be a SubmissionRequest")
    if not isinstance(prior_receipts, Sequence) or isinstance(prior_receipts, str | bytes):
        raise TypeError("prior_receipts must be a sequence")
    previous = tuple(prior_receipts)
    if any(not isinstance(item, SubmissionReceipt) for item in previous):
        raise TypeError("prior_receipts must contain SubmissionReceipt values")
    matching = tuple(
        item for item in previous if item.request.idempotency_key == request.idempotency_key
    )
    if not matching:
        return SubmissionResolution(SubmissionDecision.ACCEPT, request.fingerprint)
    existing = matching[0]
    if any(item.request.fingerprint != existing.request.fingerprint for item in matching[1:]):
        raise ValueError("prior submission receipts contain conflicting idempotency records")
    decision = (
        SubmissionDecision.REPLAY_EXISTING
        if existing.request.fingerprint == request.fingerprint
        else SubmissionDecision.IDEMPOTENCY_CONFLICT
    )
    return SubmissionResolution(decision, request.fingerprint, existing)
