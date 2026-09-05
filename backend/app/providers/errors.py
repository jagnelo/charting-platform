"""Typed provider failures shared by adapters and the runtime."""

from __future__ import annotations

from datetime import datetime


class ProviderNotConfiguredError(RuntimeError):
    """The adapter needs a credential or endpoint that is not configured."""


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
