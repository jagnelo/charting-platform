"""Transactional-outbox message contracts for execution events.

This module models the record and compare-and-set decisions that a future
PostgreSQL outbox adapter will persist before transport to Redis.  It performs
no database, queue, or network I/O and never claims that a message was sent.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest


def _nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class OutboxMessage:
    """One immutable message staged for eventual transport."""

    request_id: str
    aggregate_type: str
    aggregate_id: str
    event_id: str
    topic: str
    payload_digest: str
    created_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        require_sha256_digest(self.request_id, field_name="request_id")
        require_sha256_digest(self.event_id, field_name="event_id")
        require_sha256_digest(self.payload_digest, field_name="payload_digest")
        _nonempty(self.aggregate_type, "aggregate_type")
        _nonempty(self.aggregate_id, "aggregate_id")
        _nonempty(self.topic, "topic")
        _aware(self.created_at, "created_at")
        _aware(self.available_at, "available_at")
        if self.available_at < self.created_at:
            raise ValueError("available_at must not precede created_at")

    @property
    def message_id(self) -> str:
        """Content identity independent of enqueue scheduling timestamps."""

        return content_digest(
            {
                "aggregate_id": self.aggregate_id,
                "aggregate_type": self.aggregate_type,
                "event_id": self.event_id,
                "payload_digest": self.payload_digest,
                "topic": self.topic,
            }
        )

    @property
    def semantic_fingerprint(self) -> str:
        return self.message_id

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class OutboxState:
    """Validated immutable outbox contents and publish acknowledgements."""

    messages: tuple[OutboxMessage, ...] = ()
    published_message_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.messages, tuple):
            raise TypeError("messages must be a tuple")
        if not isinstance(self.published_message_ids, frozenset):
            raise TypeError("published_message_ids must be a frozenset")
        identities: set[str] = set()
        requests: set[str] = set()
        for message in self.messages:
            if not isinstance(message, OutboxMessage):
                raise TypeError("messages must contain OutboxMessage values")
            if message.message_id in identities:
                raise ValueError("outbox messages must have unique content identities")
            if message.request_id in requests:
                raise ValueError("outbox messages must have unique request identities")
            identities.add(message.message_id)
            requests.add(message.request_id)
        if tuple(sorted(self.messages, key=lambda item: item.message_id)) != self.messages:
            raise ValueError("outbox messages must be deterministically ordered")
        if not self.published_message_ids <= identities:
            raise ValueError("published messages must exist in the outbox")

    @property
    def pending_messages(self) -> tuple[OutboxMessage, ...]:
        return tuple(
            sorted(
                (item for item in self.messages if item.message_id not in self.published_message_ids),
                key=lambda item: (item.available_at, item.message_id),
            )
        )

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


class OutboxEnqueueDecision(StrEnum):
    ENQUEUE = "enqueue"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class OutboxEnqueueResolution:
    decision: OutboxEnqueueDecision
    state: OutboxState
    message_id: str
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, OutboxEnqueueDecision):
            raise TypeError("decision must be an OutboxEnqueueDecision")
        if not isinstance(self.state, OutboxState):
            raise TypeError("state must be an OutboxState")
        require_sha256_digest(self.message_id, field_name="message_id")
        if self.decision is OutboxEnqueueDecision.REJECT and not self.rejection_reason:
            raise ValueError("rejected enqueue resolutions require a reason")
        if self.decision is not OutboxEnqueueDecision.REJECT and self.rejection_reason:
            raise ValueError("successful enqueue resolutions cannot contain a reason")


class OutboxAcknowledgeDecision(StrEnum):
    ACKNOWLEDGED = "acknowledged"
    REPLAY_EXISTING = "replay_existing"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class OutboxAcknowledgeResolution:
    decision: OutboxAcknowledgeDecision
    state: OutboxState
    message_id: str
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, OutboxAcknowledgeDecision):
            raise TypeError("decision must be an OutboxAcknowledgeDecision")
        if not isinstance(self.state, OutboxState):
            raise TypeError("state must be an OutboxState")
        require_sha256_digest(self.message_id, field_name="message_id")
        if self.decision is OutboxAcknowledgeDecision.REJECT and not self.rejection_reason:
            raise ValueError("rejected acknowledgement resolutions require a reason")
        if self.decision is not OutboxAcknowledgeDecision.REJECT and self.rejection_reason:
            raise ValueError("successful acknowledgement resolutions cannot contain a reason")


def resolve_outbox_enqueue(
    state: OutboxState,
    message: OutboxMessage,
    prior_messages: Sequence[OutboxMessage] = (),
) -> OutboxEnqueueResolution:
    """Resolve idempotent staging of one message without mutating storage."""

    if not isinstance(state, OutboxState):
        raise TypeError("state must be an OutboxState")
    if not isinstance(message, OutboxMessage):
        raise TypeError("message must be an OutboxMessage")
    if not isinstance(prior_messages, Sequence) or isinstance(prior_messages, str | bytes):
        raise TypeError("prior_messages must be a sequence")
    prior = tuple(prior_messages)
    if any(not isinstance(item, OutboxMessage) for item in prior):
        raise TypeError("prior_messages must contain OutboxMessage values")
    existing = (*state.messages, *prior)
    by_request = tuple(item for item in existing if item.request_id == message.request_id)
    if by_request:
        if any(item.semantic_fingerprint != message.semantic_fingerprint for item in by_request):
            return OutboxEnqueueResolution(
                OutboxEnqueueDecision.CONFLICT, state, message.message_id
            )
        return OutboxEnqueueResolution(
            OutboxEnqueueDecision.REPLAY_EXISTING, state, by_request[0].message_id
        )
    by_content = tuple(item for item in existing if item.message_id == message.message_id)
    if by_content:
        return OutboxEnqueueResolution(
            OutboxEnqueueDecision.REPLAY_EXISTING, state, by_content[0].message_id
        )
    messages = tuple(sorted((*state.messages, message), key=lambda item: item.message_id))
    return OutboxEnqueueResolution(
        OutboxEnqueueDecision.ENQUEUE,
        OutboxState(messages, state.published_message_ids),
        message.message_id,
    )


def acknowledge_outbox_message(
    state: OutboxState,
    message_id: str,
) -> OutboxAcknowledgeResolution:
    """Resolve a transport acknowledgement without claiming delivery itself."""

    if not isinstance(state, OutboxState):
        raise TypeError("state must be an OutboxState")
    require_sha256_digest(message_id, field_name="message_id")
    known = {item.message_id for item in state.messages}
    if message_id not in known:
        return OutboxAcknowledgeResolution(
            OutboxAcknowledgeDecision.REJECT,
            state,
            message_id,
            "message is not present in the outbox",
        )
    if message_id in state.published_message_ids:
        return OutboxAcknowledgeResolution(
            OutboxAcknowledgeDecision.REPLAY_EXISTING, state, message_id
        )
    next_state = OutboxState(state.messages, state.published_message_ids | {message_id})
    return OutboxAcknowledgeResolution(
        OutboxAcknowledgeDecision.ACKNOWLEDGED, next_state, message_id
    )
