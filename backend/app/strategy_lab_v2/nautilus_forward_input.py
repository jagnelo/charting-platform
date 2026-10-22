"""Pure typed inputs exchanged with an isolated Nautilus forward session."""

from __future__ import annotations

from dataclasses import dataclass

from app.strategy_lab_v2.canonical import content_digest, require_sha256_digest
from app.strategy_lab_v2.lifecycle import CanonicalForwardEvent
from app.strategy_lab_v2.nautilus_event_adapter import (
    NautilusForwardDeliveryBinding,
    NautilusForwardEventTape,
    materialize_nautilus_event,
)
from app.strategy_lab_v2.sdk import MarketEvent


@dataclass(frozen=True, slots=True)
class VerifiedForwardMarketPayload:
    """Canonical and SDK events read from one source-verified artifact."""

    canonical_event: CanonicalForwardEvent
    market_event: MarketEvent
    verified_source_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_event, CanonicalForwardEvent):
            raise TypeError("canonical_event must be a CanonicalForwardEvent")
        if not isinstance(self.market_event, MarketEvent):
            raise TypeError("market_event must be a MarketEvent")
        require_sha256_digest(self.verified_source_digest, field_name="verified_source_digest")
        if self.verified_source_digest != self.canonical_event.source_digest:
            raise ValueError("verified source digest does not match canonical event provenance")
        if self.market_event.event_id != self.canonical_event.event_id:
            raise ValueError("market event id does not match canonical event")
        if self.market_event.sequence != self.canonical_event.sequence:
            raise ValueError("market event sequence does not match canonical event")
        if self.market_event.event_time != self.canonical_event.event_time:
            raise ValueError("market event time does not match canonical event")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)


@dataclass(frozen=True, slots=True)
class NautilusForwardDeliveryInput:
    """One authenticated accepted delivery prepared for a persistent engine."""

    delivery_binding: NautilusForwardDeliveryBinding
    tape: NautilusForwardEventTape
    market_event: MarketEvent
    verified_source_digest: str

    def __post_init__(self) -> None:
        if not isinstance(self.delivery_binding, NautilusForwardDeliveryBinding):
            raise TypeError("delivery_binding must be a NautilusForwardDeliveryBinding")
        if not isinstance(self.tape, NautilusForwardEventTape):
            raise TypeError("tape must be a NautilusForwardEventTape")
        if not isinstance(self.market_event, MarketEvent):
            raise TypeError("market_event must be a MarketEvent")
        require_sha256_digest(self.verified_source_digest, field_name="verified_source_digest")
        if self.delivery_binding.admission_decision != "enqueue":
            raise ValueError("live Nautilus delivery requires an accepted enqueue decision")
        if self.tape.instance_id != self.delivery_binding.instance_id:
            raise ValueError("forward tape instance does not match its delivery binding")
        if len(self.tape.envelopes) != 1 or self.tape.delivery_bindings != (self.delivery_binding,):
            raise ValueError("one-event delivery input must contain its exact persisted binding")
        envelope = self.tape.envelopes[0]
        if content_digest(envelope.canonical_event) != self.delivery_binding.event_fingerprint:
            raise ValueError("forward tape event does not match its delivery binding")
        if envelope.canonical_event.source_digest != self.verified_source_digest:
            raise ValueError("forward tape source digest does not match verified payload")
        if envelope.record != materialize_nautilus_event(
            self.market_event, event_type=envelope.record.event_type
        ):
            raise ValueError("forward tape record differs from its resolved market event")

    @property
    def fingerprint(self) -> str:
        return content_digest(self)

    @property
    def verified_market_payload(self) -> VerifiedForwardMarketPayload:
        """Return the source-bound SDK event carried by this native input."""

        return VerifiedForwardMarketPayload(
            self.tape.envelopes[0].canonical_event,
            self.market_event,
            self.verified_source_digest,
        )


__all__ = ["NautilusForwardDeliveryInput", "VerifiedForwardMarketPayload"]
