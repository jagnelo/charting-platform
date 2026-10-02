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
    # MarketData.app exposes the current credit window and the charge for
    # this response under provider-native names. Keep these separate from
    # the similarly named generic X-RateLimit headers.
    "x-api-ratelimit-limit",
    "x-api-ratelimit-remaining",
    "x-api-ratelimit-reset",
    "x-api-ratelimit-consumed",
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

    capture_response_payloads: bool = False
    http_requests: int = 0
    response_bytes: int = 0
    response_headers: dict[str, str] = field(default_factory=dict)
    response_payloads: list[Any] = field(default_factory=list)

    def observe(
        self,
        response: Any,
        *,
        response_bytes: int | None = None,
        count_request: bool = True,
    ) -> None:
        if count_request:
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
        if headers is not None:
            normalized_headers = {str(key).lower(): value for key, value in headers.items()}
            for name in _OBSERVED_HEADERS:
                value = normalized_headers.get(name)
                if value is not None:
                    self.response_headers[name] = str(value)
        if self.capture_response_payloads:
            try:
                payload = response.json()
            except Exception:  # noqa: BLE001 - telemetry must never mask transport handling.
                # The latest-price persistence path is JSON-first, but a
                # provider may legitimately return text. Keep that body too
                # rather than silently dropping the response. Streaming
                # responses can legitimately reject both accessors until the
                # adapter has consumed the body; telemetry must not turn that
                # transport fact into a provider failure.
                try:
                    payload = getattr(response, "text", None)
                except Exception:  # noqa: BLE001 - see the outer telemetry guard.
                    payload = None
            if payload is not None:
                self.response_payloads.append(payload)

    def as_dict(self) -> dict[str, Any]:
        return {
            "http_requests": self.http_requests,
            "response_bytes": self.response_bytes,
            "response_headers": dict(self.response_headers),
            "response_payloads": list(self.response_payloads),
        }


_current: ContextVar[ProviderTransportMeasurement | None] = ContextVar(
    "provider_transport_measurement", default=None
)


def activate(*, capture_response_payloads: bool = False) -> tuple[ProviderTransportMeasurement, Token]:
    measurement = ProviderTransportMeasurement(
        capture_response_payloads=capture_response_payloads,
    )
    return measurement, _current.set(measurement)


def deactivate(token: Token) -> None:
    _current.reset(token)


def observe_response(
    response: Any,
    *,
    response_bytes: int | None = None,
    count_request: bool = True,
) -> None:
    measurement = _current.get()
    if measurement is not None:
        measurement.observe(
            response,
            response_bytes=response_bytes,
            count_request=count_request,
        )
