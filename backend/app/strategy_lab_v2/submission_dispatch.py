"""Atomic asynchronous-submission and worker-dispatch staging semantics.

The API accepts a request with a durable idempotency receipt while the worker
message is published through the transactional outbox.  This module composes
those two pure contracts so a persistence adapter can commit both states in a
single compare-and-set transaction.  It performs no database or queue I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.dispatch import (
    DispatchDecision,
    DispatchEnvelope,
    DispatchRequest,
    DispatchResolution,
    build_dispatch_envelope,
    resolve_idempotent_dispatch,
)
from app.strategy_lab_v2.submissions import (
    SubmissionDecision,
    SubmissionReceipt,
    SubmissionRequest,
    create_submission_receipt,
    resolve_submission,
)


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SubmissionReceiptLedger:
    """Deterministically ordered accepted submission receipts."""

    receipts: tuple[SubmissionReceipt, ...] = ()

    def __post_init__(self) -> None:
        receipts = tuple(self.receipts)
        if any(not isinstance(item, SubmissionReceipt) for item in receipts):
            raise TypeError("receipts must contain SubmissionReceipt values")
        keys = [item.request.idempotency_key for item in receipts]
        if len(keys) != len(set(keys)):
            raise ValueError("submission idempotency keys must be unique")
        object.__setattr__(
            self,
            "receipts",
            tuple(sorted(receipts, key=lambda item: item.request.idempotency_key)),
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class SubmissionDispatchDecision(StrEnum):
    ENQUEUED = "enqueued"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class SubmissionDispatchResolution:
    """One all-or-nothing receipt and dispatch proposal."""

    decision: SubmissionDispatchDecision
    ledger: SubmissionReceiptLedger
    request_fingerprint: str
    receipt: SubmissionReceipt | None = None
    dispatch_resolution: DispatchResolution | None = None
    envelope: DispatchEnvelope | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, SubmissionDispatchDecision):
            raise TypeError("decision must be a SubmissionDispatchDecision")
        if not isinstance(self.ledger, SubmissionReceiptLedger):
            raise TypeError("ledger must be a SubmissionReceiptLedger")
        require_sha256_digest(self.request_fingerprint, field_name="request_fingerprint")
        if self.receipt is not None and not isinstance(self.receipt, SubmissionReceipt):
            raise TypeError("receipt must be a SubmissionReceipt")
        if self.dispatch_resolution is not None and not isinstance(
            self.dispatch_resolution, DispatchResolution
        ):
            raise TypeError("dispatch_resolution must be a DispatchResolution")
        if self.envelope is not None and not isinstance(self.envelope, DispatchEnvelope):
            raise TypeError("envelope must be a DispatchEnvelope")
        if self.decision in {
            SubmissionDispatchDecision.ENQUEUED,
            SubmissionDispatchDecision.REPLAY_EXISTING,
        }:
            if self.receipt is None or self.dispatch_resolution is None or self.envelope is None:
                raise ValueError("accepted resolutions require receipt and dispatch evidence")
            if self.dispatch_resolution.decision not in {
                DispatchDecision.ENQUEUE,
                DispatchDecision.REPLAY_EXISTING,
            }:
                raise ValueError("accepted resolutions require an accepted dispatch")
        if self.decision in {
            SubmissionDispatchDecision.CONFLICT,
            SubmissionDispatchDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("conflicts and rejections require a reason")
        if self.decision not in {
            SubmissionDispatchDecision.CONFLICT,
            SubmissionDispatchDecision.REJECT,
        } and self.rejection_reason:
            raise ValueError("accepted resolutions cannot contain a rejection reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def resolve_submission_dispatch(
    ledger: SubmissionReceiptLedger,
    request: SubmissionRequest,
    dispatch_request: DispatchRequest,
    *,
    accepted_at: datetime,
    prior_dispatches: Sequence[DispatchRequest] = (),
) -> SubmissionDispatchResolution:
    """Stage one idempotent 202 receipt and its worker dispatch together.

    A submission retry may repair a missing dispatch after a receipt was
    durably written.  The reverse state—an existing dispatch without a
    submission receipt—is rejected to avoid exposing an untracked job.
    """

    if not isinstance(ledger, SubmissionReceiptLedger):
        raise TypeError("ledger must be a SubmissionReceiptLedger")
    if not isinstance(request, SubmissionRequest):
        raise TypeError("request must be a SubmissionRequest")
    if not isinstance(dispatch_request, DispatchRequest):
        raise TypeError("dispatch_request must be a DispatchRequest")
    if not isinstance(prior_dispatches, Sequence) or isinstance(
        prior_dispatches, str | bytes
    ):
        raise TypeError("prior_dispatches must be a sequence")
    _aware(accepted_at, "accepted_at")
    if accepted_at < request.submitted_at:
        return _reject(ledger, request.fingerprint, "acceptance cannot precede submission")
    if dispatch_request.attempt_id != request.attempt_id:
        return _reject(ledger, request.fingerprint, "dispatch references a different attempt")
    if dispatch_request.payload_digest != request.payload_digest:
        return _reject(ledger, request.fingerprint, "dispatch payload differs from submission")
    if dispatch_request.idempotency_key != request.idempotency_key:
        return _reject(ledger, request.fingerprint, "dispatch idempotency key differs from submission")
    if dispatch_request.created_at < request.submitted_at:
        return _reject(ledger, request.fingerprint, "dispatch cannot precede submission")

    submission = resolve_submission(request, ledger.receipts)
    if submission.decision is SubmissionDecision.IDEMPOTENCY_CONFLICT:
        return _reject(
            ledger,
            request.fingerprint,
            "submission idempotency key is bound to different content",
            decision=SubmissionDispatchDecision.CONFLICT,
        )
    receipt = (
        submission.existing_receipt
        if submission.decision is SubmissionDecision.REPLAY_EXISTING
        else create_submission_receipt(request, accepted_at=accepted_at)
    )
    if receipt is None:  # pragma: no cover - guarded by the pure submission contract
        raise AssertionError("accepted submission must include a receipt")

    dispatch = resolve_idempotent_dispatch(dispatch_request, prior_dispatches)
    if dispatch.decision is DispatchDecision.IDEMPOTENCY_CONFLICT:
        return _reject(
            ledger,
            request.fingerprint,
            "dispatch idempotency key is bound to different content",
            decision=SubmissionDispatchDecision.CONFLICT,
        )
    if (
        submission.decision is SubmissionDecision.ACCEPT
        and dispatch.decision is DispatchDecision.REPLAY_EXISTING
    ):
        return _reject(
            ledger,
            request.fingerprint,
            "dispatch exists without a submission receipt",
            decision=SubmissionDispatchDecision.CONFLICT,
        )

    next_ledger = ledger
    if submission.decision is SubmissionDecision.ACCEPT:
        next_ledger = SubmissionReceiptLedger((*ledger.receipts, receipt))
    envelope = build_dispatch_envelope(dispatch_request)
    decision = (
        SubmissionDispatchDecision.REPLAY_EXISTING
        if submission.decision is SubmissionDecision.REPLAY_EXISTING
        and dispatch.decision is DispatchDecision.REPLAY_EXISTING
        else SubmissionDispatchDecision.ENQUEUED
    )
    return SubmissionDispatchResolution(
        decision,
        next_ledger,
        request.fingerprint,
        receipt,
        dispatch,
        envelope,
    )


def _reject(
    ledger: SubmissionReceiptLedger,
    request_fingerprint: str,
    reason: str,
    *,
    decision: SubmissionDispatchDecision = SubmissionDispatchDecision.REJECT,
) -> SubmissionDispatchResolution:
    return SubmissionDispatchResolution(
        decision,
        ledger,
        request_fingerprint,
        rejection_reason=reason,
    )
