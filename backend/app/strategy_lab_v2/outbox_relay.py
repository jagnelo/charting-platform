"""Outbox-to-Redis relay orchestration.

The outbox state is authoritative and must be persisted by a database adapter.
This module only binds one immutable :class:`OutboxMessage` to the Redis
transport: a message becomes published in the proposed outbox state only after
Redis reports an enqueue or exact replay.  A transport conflict or failure
returns the original state, leaving the message retryable.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.dispatch import DispatchEnvelope, DispatchRequest, build_dispatch_envelope
from app.strategy_lab_v2.outbox import (
    OutboxAcknowledgeDecision,
    OutboxMessage,
    OutboxState,
    acknowledge_outbox_message,
)
from app.strategy_lab_v2.redis_transport import (
    RedisDispatchTransport,
    RedisTransportDecision,
    RedisTransportResolution,
)


class OutboxRelayDecision(StrEnum):
    PUBLISHED = "published"
    REPLAY_EXISTING = "replay_existing"
    CONFLICT = "conflict"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class OutboxRelayResolution:
    """Proposed authoritative outbox state after one relay attempt."""

    decision: OutboxRelayDecision
    state: OutboxState
    outbox_message_id: str
    envelope: DispatchEnvelope | None = None
    transport: RedisTransportResolution | None = None
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision, OutboxRelayDecision):
            raise TypeError("decision must be an OutboxRelayDecision")
        if not isinstance(self.state, OutboxState):
            raise TypeError("state must be an OutboxState")
        require_sha256_digest(self.outbox_message_id, field_name="outbox_message_id")
        if self.envelope is not None and not isinstance(self.envelope, DispatchEnvelope):
            raise TypeError("envelope must be a DispatchEnvelope")
        if self.transport is not None and not isinstance(
            self.transport, RedisTransportResolution
        ):
            raise TypeError("transport must be a RedisTransportResolution")
        if self.decision in {
            OutboxRelayDecision.CONFLICT,
            OutboxRelayDecision.REJECT,
        } and not self.rejection_reason:
            raise ValueError("failed relay resolutions require a reason")
        if self.decision in {
            OutboxRelayDecision.PUBLISHED,
            OutboxRelayDecision.REPLAY_EXISTING,
        } and self.rejection_reason:
            raise ValueError("successful relay resolutions cannot contain a reason")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


def build_outbox_dispatch_envelope(message: OutboxMessage) -> DispatchEnvelope:
    """Build a deterministic transport envelope for one outbox message.

    The outbox semantic identity is used as the Redis idempotency key.  This
    preserves the outbox's same-content deduplication even when two request
    records point at the same event payload.  The original outbox request ID
    remains authoritative metadata and is not replaced by this transport key.
    """

    if not isinstance(message, OutboxMessage):
        raise TypeError("message must be an OutboxMessage")
    request = DispatchRequest(
        idempotency_key=message.message_id,
        attempt_id=message.event_id,
        payload_digest=message.payload_digest,
        queue_name=message.topic,
        created_at=message.created_at,
    )
    return build_dispatch_envelope(request)


async def relay_outbox_message(
    state: OutboxState,
    message: OutboxMessage,
    transport: RedisDispatchTransport,
) -> OutboxRelayResolution:
    """Publish one pending outbox message and propose its acknowledged state.

    This operation is intentionally one-message scoped.  The caller must
    compare-and-set the returned state in the authoritative store; Redis side
    effects are idempotent, so a crash between publication and state commit is
    recovered as an exact transport replay on the next attempt.
    """

    if not isinstance(state, OutboxState):
        raise TypeError("state must be an OutboxState")
    if not isinstance(message, OutboxMessage):
        raise TypeError("message must be an OutboxMessage")
    if not isinstance(transport, RedisDispatchTransport):
        raise TypeError("transport must be a RedisDispatchTransport")
    if message.message_id not in {item.message_id for item in state.messages}:
        return _reject(state, message.message_id, "message is not present in the outbox")
    if message.message_id in state.published_message_ids:
        return OutboxRelayResolution(
            OutboxRelayDecision.REPLAY_EXISTING,
            state,
            message.message_id,
        )

    envelope = build_outbox_dispatch_envelope(message)
    result = await transport.enqueue(envelope)
    if result.decision in {
        RedisTransportDecision.CONFLICT,
        RedisTransportDecision.REJECT,
    }:
        return OutboxRelayResolution(
            OutboxRelayDecision.CONFLICT
            if result.decision is RedisTransportDecision.CONFLICT
            else OutboxRelayDecision.REJECT,
            state,
            message.message_id,
            envelope,
            result,
            result.rejection_reason or "Redis transport rejected the outbox message",
        )

    acknowledged = acknowledge_outbox_message(state, message.message_id)
    if acknowledged.decision is not OutboxAcknowledgeDecision.ACKNOWLEDGED:
        return _reject(
            state,
            message.message_id,
            "outbox publication acknowledgement could not be staged",
            envelope=envelope,
            transport=result,
        )
    return OutboxRelayResolution(
        OutboxRelayDecision.PUBLISHED
        if result.decision is RedisTransportDecision.ENQUEUED
        else OutboxRelayDecision.REPLAY_EXISTING,
        acknowledged.state,
        message.message_id,
        envelope,
        result,
    )


def _reject(
    state: OutboxState,
    message_id: str,
    reason: str,
    *,
    envelope: DispatchEnvelope | None = None,
    transport: RedisTransportResolution | None = None,
) -> OutboxRelayResolution:
    return OutboxRelayResolution(
        OutboxRelayDecision.REJECT,
        state,
        message_id,
        envelope,
        transport,
        reason,
    )
