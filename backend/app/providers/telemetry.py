"""Per-call provider transport measurements.

The provider runtime executes synchronous adapters in worker threads.  A
context-local measurement lets an adapter report the actual HTTP response
bytes and provider rate-limit headers without changing every provider method's
return type.  It is deliberately observational: it never infers a quota or
turns an unknown provider contract into a routable one.
"""

from __future__ import annotations

import base64
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any

from app.providers.errors import redact_provider_payload

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
    # Gate stock public endpoints expose provider-native request counts; the
    # reset timestamp is only a quota boundary after exhaustion, so retain it
    # as telemetry without inferring a normal-window reset from it.
    "x-gate-ratelimit-requests-remain",
    "x-gate-ratelimit-limit",
    "x-gate-ratelimit-reset-timestamp",
    # APILayer's account-level quota snapshots include explicit day/month
    # counters when provided. Retain the per-window second/minute/hour forms
    # too: individual APILayer products may expose transport throttles without
    # exposing account-wide billing usage. These observations must not be
    # reinterpreted as a monthly account balance unless the header names that
    # exact dimension.
    "x-ratelimit-limit-second",
    "x-ratelimit-remaining-second",
    "x-ratelimit-reset-second",
    "x-ratelimit-limit-minute",
    "x-ratelimit-remaining-minute",
    "x-ratelimit-reset-minute",
    "x-ratelimit-limit-hour",
    "x-ratelimit-remaining-hour",
    "x-ratelimit-reset-hour",
    "x-ratelimit-limit-day",
    "x-ratelimit-limit-month",
    "x-ratelimit-remaining-day",
    "x-ratelimit-remaining-month",
    "x-ratelimit-reset-day",
    "x-ratelimit-reset-month",
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
    response_metadata: list[dict[str, Any]] = field(default_factory=list)
    response_payloads: list[Any] = field(default_factory=list)

    def observe(
        self,
        response: Any,
        *,
        response_bytes: int | None = None,
        count_request: bool = True,
        capture_response_payload: bool | None = None,
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
        normalized_headers: dict[str, str] = {}
        if headers is not None:
            normalized_headers = {str(key).lower(): value for key, value in headers.items()}
            for name in _OBSERVED_HEADERS:
                value = normalized_headers.get(name)
                if value is not None:
                    self.response_headers[name] = str(value)
        if count_request:
            status_code = getattr(response, "status_code", None)
            self.response_metadata.append(
                {
                    "status_code": (
                        status_code
                        if isinstance(status_code, int) and not isinstance(status_code, bool)
                        else None
                    ),
                    "headers": {
                        name: str(normalized_headers[name])
                        for name in _OBSERVED_HEADERS
                        if name in normalized_headers
                    },
                }
            )
        should_capture_payload = (
            self.capture_response_payloads
            if capture_response_payload is None
            else capture_response_payload
        )
        if should_capture_payload:
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
                self.response_payloads.append(redact_provider_payload(payload))

    def as_dict(self) -> dict[str, Any]:
        return {
            "http_requests": self.http_requests,
            "response_bytes": self.response_bytes,
            "response_headers": dict(self.response_headers),
            "response_metadata": list(self.response_metadata),
            "response_payloads": list(self.response_payloads),
        }


_current: ContextVar[ProviderTransportMeasurement | None] = ContextVar(
    "provider_transport_measurement", default=None
)


def activate(
    *, capture_response_payloads: bool = False
) -> tuple[ProviderTransportMeasurement, Token]:
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
    capture_response_payload: bool | None = None,
) -> None:
    measurement = _current.get()
    if measurement is not None:
        measurement.observe(
            response,
            response_bytes=response_bytes,
            count_request=count_request,
            capture_response_payload=capture_response_payload,
        )


def observe_sanitized_payload(payload: Any) -> None:
    """Attach an adapter-sanitized response body to the current measurement.

    Credential-keyed or otherwise structurally sensitive envelopes can opt
    out of raw-body capture and provide only a verified safe projection after
    parsing. This keeps byte/request observations intact while allowing the
    live evidence archive to retain useful response data without secrets.
    """

    measurement = _current.get()
    if measurement is not None and measurement.capture_response_payloads:
        measurement.response_payloads.append(redact_provider_payload(payload))


def observe_binary_response_payload(kind: str, body: bytes, *, complete: bool) -> None:
    """Retain exact binary response bytes in the ordered response evidence.

    The body is base64-encoded because the request log is JSON-backed. Unlike
    provider text, encoded binary must not pass through text redaction: altering
    even one character would make the archived response unrecoverable.
    """

    measurement = _current.get()
    if measurement is None or not measurement.capture_response_payloads or not body:
        return
    measurement.response_payloads.append(
        {
            "kind": str(kind),
            "encoding": "base64",
            "complete": bool(complete),
            "bytes_received": len(body),
            "sha256": sha256(body).hexdigest(),
            "body_base64": base64.b64encode(body).decode("ascii"),
        }
    )
