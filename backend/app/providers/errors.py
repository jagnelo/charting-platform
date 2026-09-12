"""Typed provider failures shared by adapters and the runtime."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from math import isfinite
from typing import Any

_QUERY_SECRET_RE = re.compile(
    r"(?i)([?&](?:api[_-]?(?:key|token|secret)|access[_-]?key|token|client[_-]?secret|secret(?:[_-]?key)?|authorization)=)[^&\s'\"]+"
)
_HEADER_SECRET_RE = re.compile(
    r"(?i)(\b(?:authorization|x-[a-z0-9-]*(?:key|token|secret))\s*[:=]\s*(?:bearer\s+)?)['\"]?[^\s,;]+"
)
_SECRET_SETTING_NAMES = (
    "SECRET_KEY",
    "OPENFIGI_API_KEY",
    "MASSIVE_API_KEY",
    "MARKETDATA_API_KEY",
    "ALPHA_VANTAGE_API_KEY",
    "COINGECKO_API_KEY",
    "FRED_API_KEY",
    "FINRA_CLIENT_ID",
    "FINRA_CLIENT_SECRET",
    "TIINGO_API_KEY",
    "TWELVE_DATA_API_KEY",
    "FINNHUB_API_KEY",
    "MARKETSTACK_API_KEY",
    "EODHD_API_KEY",
    "FMP_API_KEY",
    "TRADIER_API_KEY",
    "MARKETDATA_APP_API_KEY",
    "XSTOCKS_API_KEY",
    "COINBASE_API_KEY",
    "KRAKEN_API_KEY",
    "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY",
    "IBKR_READ_ONLY_SESSION_COOKIE",
)
_CAPACITY_HEADER_NAMES = frozenset(
    {
        "retry-after",
        "api-credits-request",
        "api-credits-used",
        "api-credits-left",
        "x-api-ratelimit-limit",
        "x-api-ratelimit-remaining",
        "x-api-ratelimit-reset",
        "x-api-ratelimit-consumed",
        "x-ratelimit-limit",
        "x-ratelimit-remaining",
        "x-ratelimit-reset",
        "x-ratelimit-allowed",
        "x-ratelimit-used",
        "x-ratelimit-available",
        "x-ratelimit-expiry",
        "x-rate-limit-limit",
        "x-rate-limit-remaining",
        "x-rate-limit-reset",
        "x-mbx-used-weight-1m",
        "x-mbx-order-count-1m",
        "x-bapi-limit",
        "x-bapi-limit-status",
        "x-bapi-limit-reset-timestamp",
        "ratelimit-limit",
        "ratelimit-remaining",
        "ratelimit-reset",
    }
)


def redact_provider_message(message: object) -> str:
    """Remove provider credentials from errors before logging or persistence.

    Providers occasionally echo query credentials in HTTP error URLs or even
    include the configured key in a human-readable quota message.  Error text
    is persisted in provider request/health/capacity rows and is also surfaced
    by live probes, so redaction must happen at the shared typed-error boundary
    rather than relying on each adapter to remember it independently.
    """

    text = str(message)
    try:
        # Import lazily to keep this low-level error module independent from
        # settings initialization and avoid a provider/config import cycle.
        from app.config import settings

        configured_values = {
            str(getattr(settings, name, "") or "").strip()
            for name in _SECRET_SETTING_NAMES
        }
        for value in sorted(
            (value for value in configured_values if len(value) >= 4),
            key=len,
            reverse=True,
        ):
            text = text.replace(value, "<redacted>")
    except Exception:
        # Redaction must never mask the original provider failure. Pattern
        # based URL/header redaction below still protects unknown test values.
        pass
    text = _QUERY_SECRET_RE.sub(r"\1<redacted>", text)
    return _HEADER_SECRET_RE.sub(r"\1<redacted>", text)


def bounded_redact_provider_message(message: object, *, max_length: int = 1000) -> str:
    """Redact provider credentials and cap diagnostic text for storage/logging."""

    if max_length < 0:
        raise ValueError("max_length must be non-negative")
    return redact_provider_message(message)[:max_length]


class ProviderNotConfiguredError(RuntimeError):
    """The adapter needs a credential or endpoint that is not configured."""


class ProviderResponseError(RuntimeError):
    """The provider returned an unusable response or transport failure."""

    def __init__(
        self,
        provider_name: str,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(redact_provider_message(message))
        self.provider_name = provider_name
        self.status_code = status_code


class ProviderRateLimitError(RuntimeError):
    """The provider rejected a request for capacity/quota reasons."""

    def __init__(
        self,
        provider_name: str,
        message: str,
        *,
        retry_at: datetime | None = None,
        status_code: int | None = None,
        scope: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(redact_provider_message(message))
        self.provider_name = provider_name
        self.retry_at = retry_at
        self.status_code = status_code
        self.scope = scope
        # Typed capacity failures may be surfaced directly by adapters before
        # durable runtime persistence gets a chance to filter transport
        # metadata.  Keep only the allow-listed quota/reset headers here so a
        # caller cannot accidentally expose credentials such as
        # Authorization, Cookie, or provider API-key headers.
        self.headers = provider_capacity_headers(headers)


def provider_retry_at_from_headers(
    headers: dict[str, str] | None,
    *,
    now: datetime | None = None,
) -> datetime | None:
    """Return a provider-declared retry time without inventing a delay.

    Providers expose either ``Retry-After`` (seconds or an HTTP date) or one
    of the common reset headers.  A missing, malformed, or non-finite value is
    deliberately treated as unknown; callers can then apply their own
    documented circuit policy instead of silently guessing a reset window.
    """

    if not headers:
        return None
    normalized = {str(key).lower(): str(value).strip() for key, value in headers.items()}
    current = now or datetime.now(UTC)
    retry_after = normalized.get("retry-after")
    if retry_after:
        try:
            seconds = float(retry_after)
            if isfinite(seconds) and seconds >= 0:
                return current + timedelta(seconds=seconds)
        except (TypeError, ValueError, OverflowError):
            pass
        try:
            parsed = parsedate_to_datetime(retry_after)
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
        except (TypeError, ValueError, OverflowError):
            pass
    for name in (
        "x-api-ratelimit-reset",
        "x-ratelimit-reset",
        "x-rate-limit-reset",
        "ratelimit-reset",
    ):
        value = normalized.get(name)
        if not value:
            continue
        try:
            raw = float(value)
            if not isfinite(raw):
                continue
            if raw > 1_000_000_000:
                return datetime.fromtimestamp(raw, tz=UTC)
            return current + timedelta(seconds=max(0, raw))
        except (TypeError, ValueError, OverflowError, OSError):
            continue
    return None


def provider_response_headers(response: Any) -> dict[str, str]:
    """Safely copy only allow-listed capacity headers from a response."""

    raw_headers = getattr(response, "headers", None)
    if isinstance(raw_headers, Mapping):
        return provider_capacity_headers(raw_headers)
    try:
        return provider_capacity_headers(raw_headers.items())
    except (AttributeError, TypeError):
        return {}


def provider_capacity_headers(headers: Any) -> dict[str, str]:
    """Filter a header mapping/iterator to non-sensitive capacity fields."""

    try:
        items = headers.items() if hasattr(headers, "items") else headers
        return {
            str(key): str(value)
            for key, value in items
            if str(key).lower() in _CAPACITY_HEADER_NAMES
        }
    except (AttributeError, TypeError, ValueError):
        return {}


def raise_for_provider_error_envelope(
    provider_name: str,
    payload: Any,
    status_code: int | None = None,
    *,
    headers: dict[str, str] | None = None,
) -> None:
    """Reject explicit provider error envelopes even when HTTP succeeded.

    Providers use different success/error markers: JSON ``status``/``s``,
    FMP's ``Error Message``, Bybit's ``retCode`` (where non-zero is failure),
    Kraken's non-empty ``error`` list, and several ``errmsg``/``errors`` forms.
    Only top-level, unambiguous markers are inspected so ordinary nested data
    fields remain untouched.
    """

    if not isinstance(payload, dict):
        return
    status = str(payload.get("status") or payload.get("s") or "").strip().lower()
    ret_code = payload.get("retCode", payload.get("ret_code"))
    ret_code_error = ret_code not in (None, "", 0, "0")
    error_code = payload.get("error_code")
    error_code_error = error_code not in (None, "", 0, "0", 200, "200")
    raw_error = payload.get("error")
    if isinstance(raw_error, list | tuple):
        error_detail = "; ".join(str(item) for item in raw_error if item not in (None, ""))
    else:
        error_detail = raw_error
    errors = payload.get("errors")
    if error_detail in (None, "") and errors not in (None, "", [], ()):
        if isinstance(errors, list | tuple):
            error_detail = "; ".join(str(item) for item in errors if item not in (None, ""))
        else:
            error_detail = errors
    ret_message = payload.get("retMsg", payload.get("ret_msg"))
    ret_message_detail = ret_message if ret_code_error else None
    error_message_detail = payload.get("error_message") if error_code_error else None
    detail = (
        payload.get("Error Message")
        or error_detail
        or payload.get("errmsg")
        or ret_message_detail
        or error_message_detail
        or (
            payload.get("message") or payload.get("detail")
            if status in {"error", "failed", "failure"}
            else None
        )
    )
    if (
        detail in (None, "")
        and not ret_code_error
        and not error_code_error
        and status not in {"error", "failed", "failure"}
    ):
        return
    if detail in (None, ""):
        detail = f"provider returned status={status or 'error'}"
    safe_detail = redact_provider_message(str(detail).strip())[:500]
    lowered = safe_detail.lower()
    if any(
        marker in lowered
        for marker in (
            "rate limit",
            "rate_limit",
            "too many request",
            "quota",
            "credit limit",
            "api call frequency",
            "throttl",
            "429",
        )
    ):
        safe_headers = provider_capacity_headers(headers)
        raise ProviderRateLimitError(
            provider_name,
            safe_detail,
            retry_at=provider_retry_at_from_headers(safe_headers),
            status_code=status_code,
            headers=safe_headers,
        )
    raise ProviderResponseError(provider_name, safe_detail, status_code=status_code)
