from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.dispatch import (
    DispatchDecision,
    DispatchRequest,
    build_dispatch_envelope,
    resolve_idempotent_dispatch,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _request(*, key: str = "request-1", payload: str = "payload", queue: str = "backtest") -> DispatchRequest:
    return DispatchRequest(
        idempotency_key=key,
        attempt_id="attempt-1",
        payload_digest=content_digest(payload),
        queue_name=queue,
        created_at=NOW,
    )


def test_dispatch_envelope_is_content_addressed() -> None:
    request = _request()
    envelope = build_dispatch_envelope(request)

    assert envelope.message_id == request.fingerprint
    assert envelope.delivery_count == 0


def test_dispatch_resolution_enqueues_and_replays_identical_requests() -> None:
    request = _request()
    assert resolve_idempotent_dispatch(request, ()).decision is DispatchDecision.ENQUEUE
    replay = resolve_idempotent_dispatch(request, (request,))
    assert replay.decision is DispatchDecision.REPLAY_EXISTING
    assert replay.existing_fingerprint == request.fingerprint


def test_dispatch_resolution_rejects_same_key_with_different_payload_or_queue() -> None:
    existing = _request()
    payload_conflict = _request(payload="different")
    queue_conflict = _request(queue="forward")
    assert (
        resolve_idempotent_dispatch(payload_conflict, (existing,)).decision
        is DispatchDecision.IDEMPOTENCY_CONFLICT
    )
    assert (
        resolve_idempotent_dispatch(queue_conflict, (existing,)).decision
        is DispatchDecision.IDEMPOTENCY_CONFLICT
    )


def test_dispatch_resolution_rejects_conflicting_prior_records() -> None:
    first = _request(payload="first")
    second = _request(payload="second")
    with pytest.raises(ValueError, match="conflicting idempotency"):
        resolve_idempotent_dispatch(first, (first, second))


def test_dispatch_request_rejects_naive_time_and_oversized_key() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        DispatchRequest("key", "attempt", content_digest("payload"), "backtest", datetime(2024, 1, 1))
    with pytest.raises(ValueError, match="256"):
        _request(key="x" * 257)
