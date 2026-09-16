from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.submissions import (
    SubmissionDecision,
    SubmissionRequest,
    create_submission_receipt,
    resolve_submission,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _request(*, payload: str = "same", submitted_at: datetime = NOW) -> SubmissionRequest:
    return SubmissionRequest(
        idempotency_key="key-1",
        operation="submit-backtest",
        attempt_id="attempt-1",
        payload_digest=content_digest({"payload": payload}),
        submitted_at=submitted_at,
    )


def test_submission_acceptance_and_receipt_are_202_and_content_addressed() -> None:
    request = _request()
    resolution = resolve_submission(request)
    assert resolution.decision is SubmissionDecision.ACCEPT
    assert resolution.http_status == 202
    receipt = create_submission_receipt(request, accepted_at=NOW + timedelta(seconds=1))
    assert receipt.http_status == 202
    assert receipt.submission_id == request.fingerprint
    assert receipt.fingerprint.startswith("sha256:")


def test_idempotency_replay_ignores_submission_timestamp() -> None:
    original = _request()
    receipt = create_submission_receipt(original, accepted_at=NOW + timedelta(seconds=1))
    retried = _request(submitted_at=NOW + timedelta(minutes=1))
    assert retried.fingerprint == original.fingerprint
    replay = resolve_submission(retried, (receipt,))
    assert replay.decision is SubmissionDecision.REPLAY_EXISTING
    assert replay.http_status == 202
    assert replay.existing_receipt == receipt


def test_same_key_with_different_payload_is_a_409_conflict() -> None:
    receipt = create_submission_receipt(_request(), accepted_at=NOW + timedelta(seconds=1))
    conflict = resolve_submission(_request(payload="changed"), (receipt,))
    assert conflict.decision is SubmissionDecision.IDEMPOTENCY_CONFLICT
    assert conflict.http_status == 409
    assert conflict.existing_receipt == receipt


def test_contradictory_prior_receipts_fail_closed() -> None:
    first = create_submission_receipt(_request(), accepted_at=NOW + timedelta(seconds=1))
    second = create_submission_receipt(
        _request(payload="changed"), accepted_at=NOW + timedelta(seconds=2)
    )
    with pytest.raises(ValueError, match="conflicting idempotency"):
        resolve_submission(_request(), (first, second))


def test_submission_contract_rejects_stale_receipts_and_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="cannot precede"):
        create_submission_receipt(_request(), accepted_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="payload_digest"):
        SubmissionRequest("key", "operation", "attempt", "bad", NOW)
    with pytest.raises(TypeError, match="prior_receipts"):
        resolve_submission(_request(), "not-receipts")  # type: ignore[arg-type]
