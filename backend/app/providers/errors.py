"""Typed provider failures shared by adapters and the runtime."""

from __future__ import annotations

import re
from datetime import datetime
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
        self.headers = headers or {}


def raise_for_provider_error_envelope(
    provider_name: str,
    payload: Any,
    status_code: int | None = None,
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
        raise ProviderRateLimitError(provider_name, safe_detail, status_code=status_code)
    raise ProviderResponseError(provider_name, safe_detail, status_code=status_code)
