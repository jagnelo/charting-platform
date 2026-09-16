from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.strategy_lab_v2.canonical import content_digest
from app.strategy_lab_v2.outbox import (
    OutboxAcknowledgeDecision,
    OutboxEnqueueDecision,
    OutboxMessage,
    OutboxState,
    acknowledge_outbox_message,
    resolve_outbox_enqueue,
)

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def _message(
    value: str = "one",
    *,
    request: str = "request",
    created_at: datetime = NOW,
    available_at: datetime | None = None,
) -> OutboxMessage:
    return OutboxMessage(
        content_digest(request),
        "run_attempt",
        "attempt-1",
        content_digest("event-1"),
        "strategy-lab.events",
        content_digest({"value": value}),
        created_at,
        available_at or created_at,
    )


def test_enqueue_orders_messages_and_exact_request_retry_replays() -> None:
    first = _message()
    applied = resolve_outbox_enqueue(OutboxState(), first)
    assert applied.decision is OutboxEnqueueDecision.ENQUEUE
    assert applied.state.messages == (first,)
    replay = resolve_outbox_enqueue(applied.state, _message(created_at=NOW + timedelta(minutes=1)))
    assert replay.decision is OutboxEnqueueDecision.REPLAY_EXISTING
    assert replay.state == applied.state
    assert first.message_id.startswith("sha256:")


def test_changed_payload_with_same_request_conflicts() -> None:
    applied = resolve_outbox_enqueue(OutboxState(), _message()).state
    conflict = resolve_outbox_enqueue(applied, _message("changed"))
    assert conflict.decision is OutboxEnqueueDecision.CONFLICT
    assert conflict.state == applied


def test_same_content_with_new_request_deduplicates() -> None:
    first = _message()
    applied = resolve_outbox_enqueue(OutboxState(), first).state
    duplicate = resolve_outbox_enqueue(applied, _message(request="other"))
    assert duplicate.decision is OutboxEnqueueDecision.REPLAY_EXISTING
    assert duplicate.message_id == first.message_id


def test_publish_acknowledgement_is_idempotent_and_pending_is_ordered() -> None:
    later = _message("later", request="later", available_at=NOW + timedelta(minutes=2))
    earlier = _message("earlier", request="earlier", available_at=NOW + timedelta(minutes=1))
    state = resolve_outbox_enqueue(OutboxState(), later).state
    state = resolve_outbox_enqueue(state, earlier).state
    assert state.pending_messages == (earlier, later)
    acknowledged = acknowledge_outbox_message(state, earlier.message_id)
    assert acknowledged.decision is OutboxAcknowledgeDecision.ACKNOWLEDGED
    assert acknowledged.state.pending_messages == (later,)
    replay = acknowledge_outbox_message(acknowledged.state, earlier.message_id)
    assert replay.decision is OutboxAcknowledgeDecision.REPLAY_EXISTING
    assert replay.state == acknowledged.state


def test_unknown_acknowledgement_is_rejected_without_mutation() -> None:
    state = OutboxState()
    rejected = acknowledge_outbox_message(state, content_digest("unknown"))
    assert rejected.decision is OutboxAcknowledgeDecision.REJECT
    assert rejected.state == state


def test_state_requires_deterministic_identity_and_known_publications() -> None:
    first = _message()
    second = _message("second", request="second")
    with pytest.raises(ValueError, match="deterministically ordered"):
        OutboxState((second, first))
    with pytest.raises(ValueError, match="published messages"):
        OutboxState((first,), frozenset({content_digest("unknown")}))


def test_message_requires_digest_time_order_and_scheduling_identity() -> None:
    with pytest.raises(ValueError, match="request_id"):
        OutboxMessage("bad", "run_attempt", "attempt-1", content_digest("event"), "topic", content_digest("p"), NOW, NOW)
    with pytest.raises(ValueError, match="available_at"):
        _message(available_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="timezone-aware"):
        _message(created_at=datetime(2024, 1, 1))


def test_enqueue_rejects_invalid_prior_message_sequence() -> None:
    with pytest.raises(TypeError, match="prior_messages"):
        resolve_outbox_enqueue(OutboxState(), _message(), "not-messages")  # type: ignore[arg-type]

