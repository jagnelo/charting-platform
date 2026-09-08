"""Per-call provider transport measurements.

The provider runtime executes synchronous adapters in worker threads.  A
context-local measurement lets an adapter report the actual HTTP response
bytes and provider rate-limit headers without changing every provider method's
return type.  It is deliberately observational: it never infers a quota or
turns an unknown provider contract into a routable one.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Any

_OBSERVED_HEADERS = (
    "content-length",
    "retry-after",
    # FINRA Query/DAPI pagination and payload-ceiling evidence.
    "record-total",
    "record-offset",
    "record-limit",
    "record-max-limit",
    "total-records-on-page",
    "response-payload-max-size",
    # Twelve Data exposes credit-pool state with these provider-native names.
    "api-credits-request",
    "api-credits-used",
    "api-credits-left",
    # Tradier exposes a token-window snapshot with these headers.
    "x-ratelimit-allowed",
    "x-ratelimit-used",
    "x-ratelimit-available",
    "x-ratelimit-expiry",
    "x-mbx-used-weight-1m",
    "x-mbx-order-count-1m",
    # Bybit V5 exposes endpoint/UID state with provider-native headers.
    "x-bapi-limit",
    "x-bapi-limit-status",
    "x-bapi-limit-reset-timestamp",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "x-rate-limit-limit",
    "x-rate-limit-remaining",
    "x-rate-limit-reset",
)


@dataclass(slots=True)
class ProviderTransportMeasurement:
    """Transport facts observed during one provider runtime invocation."""

    http_requests: int = 0
    response_bytes: int = 0
    response_headers: dict[str, str] = field(default_factory=dict)

    def observe(self, response: Any, *, response_bytes: int | None = None) -> None:
        self.http_requests += 1
        if response_bytes is None:
            content = getattr(response, "content", b"")
            if isinstance(content, bytes):
                self.response_bytes += len(content)
            elif isinstance(content, bytearray):
                self.response_bytes += len(content)
        else:
            self.response_bytes += max(0, int(response_bytes))
        headers = getattr(response, "headers", None)
        if headers is None:
            return
        normalized_headers = {str(key).lower(): value for key, value in headers.items()}
        for name in _OBSERVED_HEADERS:
            value = normalized_headers.get(name)
            if value is not None:
                self.response_headers[name] = str(value)

    def as_dict(self) -> dict[str, Any]:
        return {
            "http_requests": self.http_requests,
            "response_bytes": self.response_bytes,
            "response_headers": dict(self.response_headers),
        }


_current: ContextVar[ProviderTransportMeasurement | None] = ContextVar(
    "provider_transport_measurement", default=None
)


def activate() -> tuple[ProviderTransportMeasurement, Token]:
    measurement = ProviderTransportMeasurement()
    return measurement, _current.set(measurement)


def deactivate(token: Token) -> None:
    _current.reset(token)


def observe_response(response: Any, *, response_bytes: int | None = None) -> None:
    measurement = _current.get()
    if measurement is not None:
        measurement.observe(response, response_bytes=response_bytes)
