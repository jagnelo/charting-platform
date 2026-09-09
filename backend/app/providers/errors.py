"""Typed provider failures shared by adapters and the runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any


class ProviderNotConfiguredError(RuntimeError):
    """The adapter needs a credential or endpoint that is not configured."""


class ProviderResponseError(RuntimeError):
    """The provider returned an explicit error envelope with HTTP success."""

    def __init__(
        self,
        provider_name: str,
        message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
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
        super().__init__(message)
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
    FMP's ``Error Message``, Bybit's ``retCode``, Kraken's non-empty ``error``
    list, and several ``errmsg``/``errors`` forms. Only top-level, unambiguous
    markers are inspected so ordinary nested data fields remain untouched.
    """

    if not isinstance(payload, dict):
        return
    status = str(payload.get("status") or payload.get("s") or "").strip().lower()
    ret_code = payload.get("retCode", payload.get("ret_code"))
    ret_code_error = ret_code not in (None, "", 0, "0")
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
    detail = (
        payload.get("Error Message")
        or error_detail
        or payload.get("errmsg")
        or payload.get("retMsg")
        or payload.get("ret_msg")
        or (
            payload.get("message") or payload.get("detail")
            if status in {"error", "failed", "failure"}
            else None
        )
    )
    if detail in (None, "") and not ret_code_error and status not in {"error", "failed", "failure"}:
        return
    if detail in (None, ""):
        detail = f"provider returned status={status or 'error'}"
    safe_detail = str(detail).strip()[:500]
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
