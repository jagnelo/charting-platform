"""Application-owned transactional-outbox relay to Redis Streams."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.strategy_lab_v2.outbox import (
    OutboxAcknowledgeDecision,
    OutboxAcknowledgeResolution,
    OutboxState,
)
from app.strategy_lab_v2.outbox_relay import (
    OutboxRelayDecision,
    OutboxRelayResolution,
    relay_outbox_message,
)
from app.strategy_lab_v2.redis_transport import RedisDispatchTransport


class OutboxPersistence(Protocol):
    """Minimal durable outbox surface required by the relay."""

    async def load_outbox(self) -> OutboxState: ...

    async def acknowledge_outbox(
        self,
        message_id: str,
        *,
        expected_state_fingerprint: str,
    ) -> OutboxAcknowledgeResolution: ...


class OutboxRelayService:
    """Relay available outbox messages and persist publication acknowledgements.

    Redis is treated as an idempotent transport side effect. PostgreSQL remains
    authoritative: a message is only considered published after the adapter
    compare-and-set marks it so. A crash between Redis enqueue and that update
    therefore replays safely on the next cycle.
    """

    def __init__(
        self,
        persistence: OutboxPersistence,
        transport: RedisDispatchTransport,
    ) -> None:
        if not callable(getattr(persistence, "load_outbox", None)) or not callable(
            getattr(persistence, "acknowledge_outbox", None)
        ):
            raise TypeError("persistence must provide load_outbox and acknowledge_outbox")
        if not isinstance(transport, RedisDispatchTransport):
            raise TypeError("transport must be a RedisDispatchTransport")
        self._persistence = persistence
        self._transport = transport

    async def relay_pending(
        self,
        *,
        now: datetime,
        limit: int = 100,
    ) -> tuple[OutboxRelayResolution, ...]:
        """Relay at most ``limit`` currently available pending messages."""

        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")

        state = await self._persistence.load_outbox()
        if not isinstance(state, OutboxState):
            raise TypeError("outbox persistence returned an invalid state")
        results: list[OutboxRelayResolution] = []
        available = tuple(
            message for message in state.pending_messages if message.available_at <= now
        )[:limit]
        for message in available:
            relay = await relay_outbox_message(state, message, self._transport)
            if relay.decision not in {
                OutboxRelayDecision.PUBLISHED,
                OutboxRelayDecision.REPLAY_EXISTING,
            }:
                results.append(relay)
                continue
            acknowledgement = await self._persistence.acknowledge_outbox(
                message.message_id,
                expected_state_fingerprint=state.fingerprint,
            )
            acknowledged = acknowledgement.state
            if acknowledgement.decision not in {
                OutboxAcknowledgeDecision.ACKNOWLEDGED,
                OutboxAcknowledgeDecision.REPLAY_EXISTING,
            } or not isinstance(acknowledged, OutboxState):
                results.append(
                    OutboxRelayResolution(
                        OutboxRelayDecision.CONFLICT,
                        state,
                        message.message_id,
                        relay.envelope,
                        relay.transport,
                        acknowledgement.rejection_reason
                        or "outbox publication acknowledgement was rejected",
                    )
                )
                continue
            state = acknowledged
            results.append(relay)
        return tuple(results)


__all__ = ["OutboxPersistence", "OutboxRelayService"]
