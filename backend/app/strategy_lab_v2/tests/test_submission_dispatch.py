from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import DispatchDecision, DispatchRequest
from app.strategy_lab_v2.submission_dispatch import (
    SubmissionDispatchDecision,
    SubmissionReceiptLedger,
    resolve_submission_dispatch,
)
from app.strategy_lab_v2.submissions import SubmissionRequest, create_submission_receipt

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _request(*, key: str = "key-1", payload: str = "payload") -> SubmissionRequest:
    return SubmissionRequest(
        idempotency_key=key,
        operation="submit-backtest",
        attempt_id="attempt-1",
        payload_digest=content_digest(payload),
        submitted_at=NOW,
    )


def _dispatch(request: SubmissionRequest, *, queue: str = "backtest") -> DispatchRequest:
    return DispatchRequest(
        idempotency_key=request.idempotency_key,
        attempt_id=request.attempt_id,
        payload_digest=request.payload_digest,
        queue_name=queue,
        created_at=NOW,
    )


def test_submission_and_dispatch_are_staged_together() -> None:
    request = _request()
    resolved = resolve_submission_dispatch(
        SubmissionReceiptLedger(),
        request,
        _dispatch(request),
        accepted_at=NOW + timedelta(seconds=1),
    )

    assert resolved.decision is SubmissionDispatchDecision.ENQUEUED
    assert len(resolved.ledger.receipts) == 1
    assert resolved.receipt == resolved.ledger.receipts[0]
    assert resolved.dispatch_resolution is not None
    assert resolved.dispatch_resolution.decision is DispatchDecision.ENQUEUE
    assert resolved.envelope is not None


def test_exact_retry_replays_both_receipt_and_dispatch() -> None:
    request = _request()
    first = resolve_submission_dispatch(
        SubmissionReceiptLedger(),
        request,
        _dispatch(request),
        accepted_at=NOW + timedelta(seconds=1),
    )
    assert first.receipt is not None
    replay = resolve_submission_dispatch(
        first.ledger,
        request,
        _dispatch(request),
        accepted_at=NOW + timedelta(minutes=1),
        prior_dispatches=(_dispatch(request),),
    )

    assert replay.decision is SubmissionDispatchDecision.REPLAY_EXISTING
    assert replay.ledger == first.ledger
    assert replay.receipt == first.receipt
    assert replay.dispatch_resolution is not None
    assert replay.dispatch_resolution.decision is DispatchDecision.REPLAY_EXISTING


def test_retry_repairs_receipt_that_preceded_a_missing_dispatch() -> None:
    request = _request()
    receipt = create_submission_receipt(request, accepted_at=NOW + timedelta(seconds=1))
    repaired = resolve_submission_dispatch(
        SubmissionReceiptLedger((receipt,)),
        request,
        _dispatch(request),
        accepted_at=NOW + timedelta(seconds=2),
    )

    assert repaired.decision is SubmissionDispatchDecision.ENQUEUED
    assert repaired.ledger.receipts == (receipt,)
    assert repaired.dispatch_resolution is not None
    assert repaired.dispatch_resolution.decision is DispatchDecision.ENQUEUE


def test_existing_dispatch_without_submission_receipt_is_a_conflict() -> None:
    request = _request()
    dispatch = _dispatch(request)
    rejected = resolve_submission_dispatch(
        SubmissionReceiptLedger(),
        request,
        dispatch,
        accepted_at=NOW + timedelta(seconds=1),
        prior_dispatches=(dispatch,),
    )

    assert rejected.decision is SubmissionDispatchDecision.CONFLICT
    assert rejected.ledger == SubmissionReceiptLedger()
    assert rejected.receipt is None
    assert rejected.envelope is None
    assert rejected.rejection_reason == "dispatch exists without a submission receipt"


def test_mismatched_dispatch_identity_preserves_submission_state() -> None:
    request = _request()
    foreign = _dispatch(_request(key="other-key"))
    rejected = resolve_submission_dispatch(
        SubmissionReceiptLedger(),
        request,
        foreign,
        accepted_at=NOW + timedelta(seconds=1),
    )

    assert rejected.decision is SubmissionDispatchDecision.REJECT
    assert rejected.request_fingerprint == request.fingerprint
    assert rejected.ledger == SubmissionReceiptLedger()
    assert rejected.rejection_reason == "dispatch idempotency key differs from submission"
