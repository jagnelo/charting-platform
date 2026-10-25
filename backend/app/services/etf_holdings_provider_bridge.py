"""Per-attempt adapter into the shared Provider runtime.

Callers must invoke this once for each physical HTTP request (including every
redirect, retry, page, and fallback request). It deliberately accepts a
single-attempt transport callable rather than wrapping a logical refresh.
"""

from __future__ import annotations

import asyncio
import contextvars
import hashlib
import inspect
import threading
import time
import zlib
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.etf_holdings import ETFHoldingsBackfillJob, ETFProfile
from app.models.instrument import Instrument
from app.models.provider_recurring_cost import (
    ProviderRecurringCostBudget,
    ProviderRecurringCostCommitment,
)
from app.models.provider_runtime import (
    ProviderCapability,
    ProviderEntitlement,
    ProviderPolicy,
)
from app.providers.telemetry import observe_response
from app.services.provider_quota_coordinator import account_scope_for_provider
from app.services.provider_recurring_costs import provider_recurring_cost_status
from app.services.provider_runtime import (
    ProviderExecutionResult,
    _bind_etf_initial_qualification_authority,
    _ETFInitialQualificationAuthority,
    execute_provider_call,
)

T = TypeVar("T")

_ETF_OPERATIONS = frozenset({"fetch_etf_holdings_latest", "fetch_etf_holdings_for_date"})
_ETF_SEC_OPERATIONS = frozenset(
    {
        "fetch_etf_holdings_sec_submissions",
        "fetch_etf_holdings_sec_submissions_file",
        "fetch_etf_holdings_sec_filing",
    }
)
ETF_SEC_ADAPTER_KEY = "edgar_sec_holdings"
ETF_SEC_MAX_PHYSICAL_ATTEMPTS = 9
ETF_SEC_MAX_REDIRECTS_PER_GET = 2
ETF_SEC_MIN_ATTEMPT_INTERVAL_SECONDS = 1.0
ETF_SEC_ATTEMPT_TIMEOUT_SECONDS = 20.0
ETF_SEC_FUND_DEADLINE_SECONDS = 210.0
ETF_SEC_MAX_SUBMISSIONS_BYTES = 2 * 1024 * 1024
ETF_SEC_MAX_ARCHIVE_PAGE_BYTES = 2 * 1024 * 1024
ETF_SEC_MAX_FILING_BYTES = 16 * 1024 * 1024
ETF_SEC_MAX_AGGREGATE_DECODED_BYTES = 20 * 1024 * 1024
_ETF_SEC_RESPONSE_LIMIT_MARKER = "etf_sec_response_limit_error"
_sec_budget_monotonic = time.monotonic


def _has_explicit_account_scope_mapping(
    provider_name: str,
    quota_scope: str,
    account_scope_map: dict[str, str],
) -> bool:
    provider_name = str(provider_name).strip().lower()
    quota_scope = str(quota_scope).strip().lower()
    account_scope_key = f"{provider_name}:{quota_scope}" if quota_scope else ""
    if provider_name == "edgar" and quota_scope == "ip":
        # EDGAR's public requests share the deployment egress IP. The shared
        # resolver intentionally reads the namespaced key for IP scopes, so a
        # provider-only alias must not masquerade as an explicit binding.
        configured_scope = account_scope_map.get(account_scope_key)
        return isinstance(configured_scope, str) and bool(configured_scope.strip())
    return account_scope_key in account_scope_map or provider_name in account_scope_map


class ETFHoldingsRouteHeldError(PermissionError):
    """The publisher route is unknown or lacks reviewed admission evidence."""


@dataclass(frozen=True)
class ETFHoldingsRequestBinding:
    db: AsyncSession
    adapter: Any
    profile_id: int | None
    instrument_id: int
    provider_symbol: str
    operation: str
    sec_request: bool
    request_log_ids: list[int]
    request_urls_by_log_id: dict[int, str]
    sec_budget: Any | None = None
    initial_qualification_authority: _ETFInitialQualificationAuthority | None = None


@dataclass(frozen=True)
class ETFHoldingsRequestIdentity:
    """Committed ETF identity used to open a separate SEC attempt context."""

    db: AsyncSession
    profile_id: int
    instrument_id: int
    provider_symbol: str


_REQUEST_BINDING: contextvars.ContextVar[ETFHoldingsRequestBinding | None] = contextvars.ContextVar(
    "etf_holdings_request_binding", default=None
)


@contextmanager
def bind_etf_holdings_request_context(
    *,
    db: AsyncSession,
    adapter: Any,
    profile_id: int | None = None,
    instrument_id: int,
    provider_symbol: str,
    operation: str,
):
    """Bind the caller-loop DB session and exact ETF operation during one fetch."""

    if operation not in _ETF_OPERATIONS:
        raise ETFHoldingsRouteHeldError("ETF holdings operation is not in the reviewed contract")
    binding = ETFHoldingsRequestBinding(
        db=db,
        adapter=adapter,
        profile_id=profile_id,
        instrument_id=instrument_id,
        provider_symbol=provider_symbol,
        operation=operation,
        sec_request=False,
        request_log_ids=[],
        request_urls_by_log_id={},
    )
    token = _REQUEST_BINDING.set(binding)
    try:
        yield binding
    finally:
        _REQUEST_BINDING.reset(token)


@contextmanager
def bind_etf_holdings_sec_request_context(
    *,
    db: AsyncSession,
    adapter: Any,
    profile_id: int,
    instrument_id: int,
    provider_symbol: str,
    operation: str,
    sec_budget: Any | None = None,
    initial_qualification_authority: _ETFInitialQualificationAuthority | None = None,
):
    """Bind one distinct EDGAR attempt without inheriting an issuer operation."""

    if operation not in _ETF_SEC_OPERATIONS:
        raise ETFHoldingsRouteHeldError("SEC holdings operation is not in the reviewed contract")
    if (
        str(getattr(adapter, "source_provider", "")).strip().lower() != "edgar"
        or str(getattr(adapter, "adapter_key", "")).strip().lower() != ETF_SEC_ADAPTER_KEY
    ):
        raise ETFHoldingsRouteHeldError("SEC holdings request requires its dedicated EDGAR adapter")
    if profile_id <= 0 or instrument_id <= 0 or not str(provider_symbol).strip():
        raise ETFHoldingsRouteHeldError("SEC holdings request identity is incomplete")
    if initial_qualification_authority is not None and (
        initial_qualification_authority.provider_name != "edgar"
        or initial_qualification_authority.capability != ProviderCapability.ETF_HOLDINGS
        or operation not in initial_qualification_authority.operations
        or initial_qualification_authority.profile_id != profile_id
        or initial_qualification_authority.instrument_id != instrument_id
        or initial_qualification_authority.provider_symbol != provider_symbol.strip().upper()
        or initial_qualification_authority.attempt_id <= 0
    ):
        raise ETFHoldingsRouteHeldError("SEC qualification context does not match this fund")
    binding = ETFHoldingsRequestBinding(
        db=db,
        adapter=adapter,
        profile_id=profile_id,
        instrument_id=instrument_id,
        provider_symbol=provider_symbol,
        operation=operation,
        sec_request=True,
        request_log_ids=[],
        request_urls_by_log_id={},
        sec_budget=sec_budget,
        initial_qualification_authority=initial_qualification_authority,
    )
    token = _REQUEST_BINDING.set(binding)
    try:
        yield binding
    finally:
        _REQUEST_BINDING.reset(token)


def current_etf_holdings_request_identity() -> ETFHoldingsRequestIdentity | None:
    """Return identity only; callers must establish a new operation binding."""

    binding = _REQUEST_BINDING.get()
    if binding is None or binding.profile_id is None:
        return None
    return ETFHoldingsRequestIdentity(
        db=binding.db,
        profile_id=binding.profile_id,
        instrument_id=binding.instrument_id,
        provider_symbol=binding.provider_symbol,
    )


def etf_holdings_request_is_bound() -> bool:
    return _REQUEST_BINDING.get() is not None


def require_unbound_etf_holdings_context(operation: str) -> None:
    """Prevent a different ETF workflow from borrowing an ambient route binding.

    A surrounding latest/dated refresh context must not silently authorize an
    independent URL, identity, or request purpose. SEC requests use the
    separate ``bind_etf_holdings_sec_request_context`` contract instead.
    """

    if _REQUEST_BINDING.get() is not None:
        raise ETFHoldingsRouteHeldError(
            f"{operation} cannot reuse an ambient ETF holdings request binding"
        )


def require_bound_etf_holdings_adapter(adapter: Any) -> ETFHoldingsRequestBinding:
    """Require a request to use the exact adapter authorized by its caller."""

    binding = _REQUEST_BINDING.get()
    if binding is None:
        raise ETFHoldingsRouteHeldError("ETF adapter request has no bound shared-admission context")
    if binding.adapter is not adapter:
        raise ETFHoldingsRouteHeldError(
            "ETF adapter does not match the bound shared-admission context"
        )
    return binding


class ProviderBackedHTTPXClient:
    """HTTPX-compatible GET/POST facade admitting every physical request."""

    _REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})

    def __init__(self, **client_kwargs: Any) -> None:
        if "transport" in client_kwargs:
            raise ETFHoldingsRouteHeldError(
                "production ETF request clients cannot supply an unreviewed transport"
            )
        self._follow_redirects = bool(client_kwargs.pop("follow_redirects", False))
        self._max_redirects = int(client_kwargs.pop("max_redirects", 20))
        if self._max_redirects < 0:
            raise ETFHoldingsRouteHeldError("ETF redirect limit is invalid")
        self._cookies = httpx.Cookies(client_kwargs.pop("cookies", None))
        self._client_kwargs = dict(client_kwargs)

    async def __aenter__(self) -> ProviderBackedHTTPXClient:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", url, **kwargs)

    async def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        binding = _REQUEST_BINDING.get()
        if binding is None:
            raise ETFHoldingsRouteHeldError(
                "ETF HTTPX client was used without a bound shared-admission context"
            )
        follow_redirects = bool(kwargs.pop("follow_redirects", self._follow_redirects))
        max_redirects = int(kwargs.pop("max_redirects", self._max_redirects))
        if max_redirects < 0:
            raise ETFHoldingsRouteHeldError("ETF redirect limit is invalid")
        if binding.sec_request:
            max_redirects = min(max_redirects, ETF_SEC_MAX_REDIRECTS_PER_GET)
        if any(
            inspect.isawaitable(value) or hasattr(value, "__aiter__") for value in kwargs.values()
        ):
            raise ETFHoldingsRouteHeldError(
                "ETF request bodies must not carry caller-loop async state into the Provider worker"
            )
        current_url = str(url)
        current_method = method.upper()
        current_kwargs = dict(kwargs)
        current_client_kwargs = dict(self._client_kwargs)
        sec_budget = binding.sec_budget
        if binding.sec_request:
            if sec_budget is None:
                raise ETFHoldingsRouteHeldError(
                    "SEC request is missing its bounded one-fund execution context"
                )
            sec_budget.begin_logical_request(binding.operation)
        request_params = current_kwargs.pop("params", None)
        client_params = current_client_kwargs.pop("params", None)
        current_url = await _effective_initial_request_url(
            current_method,
            current_url,
            base_url=current_client_kwargs.get("base_url"),
            client_params=client_params,
            request_params=request_params,
        )
        history: list[httpx.Response] = []
        previous_origin = _http_origin(current_url)
        for redirect_count in range(max_redirects + 1):
            if sec_budget is not None:
                await sec_budget.before_attempt()
            attempt = _make_loop_local_httpx_attempt(
                method=current_method,
                url=current_url,
                request_kwargs=current_kwargs,
                client_kwargs={**current_client_kwargs, "cookies": self._cookies},
                sec_budget=sec_budget,
                sec_operation=binding.operation,
            )
            result = await execute_etf_holdings_request_attempt(
                binding.db,
                adapter=binding.adapter,
                instrument_id=binding.instrument_id,
                provider_symbol=binding.provider_symbol,
                operation=binding.operation,
                request_url=current_url,
                single_attempt=attempt,
            )
            response = result.result
            if sec_budget is not None and response.status_code in {403, 429}:
                sec_budget.latch_terminal(f"SEC access limit returned HTTP {response.status_code}")
            if response.extensions.get(_ETF_SEC_RESPONSE_LIMIT_MARKER):
                reason = str(response.extensions[_ETF_SEC_RESPONSE_LIMIT_MARKER])
                if sec_budget is not None:
                    sec_budget.latch_terminal(reason)
                raise ETFHoldingsRouteHeldError(reason)
            response_cookies = httpx.Cookies()
            response_cookies.extract_cookies(response)
            self._cookies.update(response_cookies)
            if not follow_redirects or response.status_code not in self._REDIRECT_STATUSES:
                response.history = history
                return response
            location = response.headers.get("location")
            if not location:
                return response
            if redirect_count >= max_redirects:
                if sec_budget is not None:
                    sec_budget.latch_terminal("SEC logical request exceeded its redirect limit")
                raise httpx.TooManyRedirects(
                    "ETF publisher exceeded the configured redirect limit",
                    request=response.request,
                )
            next_url = urljoin(str(response.url), location)
            if (response.status_code == 303 and current_method != "HEAD") or (
                response.status_code in {301, 302} and current_method == "POST"
            ):
                current_method = "GET"
                current_kwargs.pop("content", None)
                current_kwargs.pop("data", None)
                current_kwargs.pop("json", None)
                current_kwargs.pop("files", None)
                current_kwargs = _without_headers(
                    current_kwargs, {"content-length", "content-type", "transfer-encoding"}
                )
            next_origin = _http_origin(next_url)
            if next_origin != previous_origin:
                current_kwargs = _without_credentials(current_kwargs)
                current_client_kwargs = _without_credentials(current_client_kwargs)
            history.append(response)
            current_url = next_url
            previous_origin = next_origin
        raise AssertionError("unreachable ETF redirect state")


async def _effective_initial_request_url(
    method: str,
    url: str,
    *,
    base_url: str | None,
    client_params: Any,
    request_params: Any,
) -> str:
    """Resolve HTTPX base URL and merged params before Provider admission."""

    builder_kwargs: dict[str, Any] = {}
    if base_url:
        builder_kwargs["base_url"] = base_url
    if client_params is not None:
        builder_kwargs["params"] = client_params
    builder = httpx.AsyncClient(**builder_kwargs)
    try:
        request = builder.build_request(method, url, params=request_params)
        return str(request.url)
    finally:
        await builder.aclose()


def _http_origin(url: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ETFHoldingsRouteHeldError("ETF redirect URL has an invalid port") from exc
    scheme = parsed.scheme.lower()
    if port is None:
        port = 443 if scheme == "https" else 80 if scheme == "http" else None
    return scheme, (parsed.hostname or "").encode("idna").decode("ascii").lower(), port


def _canonical_request_url(url: str) -> str:
    """Canonicalize a complete URL for in-memory attempt equality checks."""

    try:
        canonical_url = str(httpx.URL(url))
        parsed = urlsplit(canonical_url)
    except (TypeError, ValueError) as exc:
        raise ETFHoldingsRouteHeldError("ETF request URL is malformed") from exc
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ETFHoldingsRouteHeldError("ETF request URL contains forbidden URL components")
    return canonical_url


def _make_loop_local_httpx_attempt(**kwargs: Any) -> LoopLocalHTTPXAttempt:
    """Isolated construction seam for offline MockTransport contract tests."""

    return LoopLocalHTTPXAttempt(**kwargs)


def _without_headers(kwargs: dict[str, Any], names: set[str]) -> dict[str, Any]:
    result = dict(kwargs)
    raw_headers = result.get("headers")
    if raw_headers is None:
        return result
    headers = httpx.Headers(raw_headers)
    for name in names:
        if name in headers:
            del headers[name]
    result["headers"] = headers
    return result


def _without_credentials(kwargs: dict[str, Any]) -> dict[str, Any]:
    result = _without_headers(kwargs, {"authorization", "cookie", "proxy-authorization"})
    result.pop("auth", None)
    # A client-level Cookie header is merged into each request separately.
    result["headers"] = httpx.Headers(result.get("headers", {}))
    for name in ("authorization", "cookie", "proxy-authorization"):
        if name in result["headers"]:
            del result["headers"][name]
    return result


@dataclass(frozen=True)
class LoopLocalHTTPXAttempt:
    """One HTTPX request with a fresh client created inside the worker loop.

    Only configuration values are accepted, never a client instance or client
    factory, so a caller-loop AsyncClient cannot be passed into asyncio.run.
    Request arguments must be loop-neutral values, such as bytes rather than
    an async body iterator captured from another event loop. A supplied
    transport factory must create a fresh transport when called in this loop.
    """

    method: str
    url: str
    request_kwargs: dict[str, Any]
    client_kwargs: dict[str, Any]
    transport_factory: Callable[[], httpx.AsyncBaseTransport] | None = None
    sec_budget: Any | None = None
    sec_operation: str | None = None

    async def execute(self) -> httpx.Response:
        if "follow_redirects" in self.request_kwargs:
            raise ETFHoldingsRouteHeldError(
                "HTTPX attempts must not follow redirects; admit each hop separately"
            )
        if "transport" in self.client_kwargs or "follow_redirects" in self.client_kwargs:
            raise ETFHoldingsRouteHeldError(
                "HTTPX attempts cannot override the per-attempt transport boundary"
            )
        if self.sec_budget is not None:
            # Fail early before setup when the fund deadline has already
            # expired. Setup itself may take time, so this is not the send
            # timeout; that is recomputed after request construction below.
            await self.sec_budget.start_attempt()
            self.sec_budget.attempt_timeout_seconds()
        transport = self.transport_factory() if self.transport_factory is not None else None
        async with httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            **self.client_kwargs,
        ) as client:
            request = client.build_request(self.method, self.url, **self.request_kwargs)
            if self.sec_budget is None:
                response = await client.send(request, follow_redirects=False, stream=True)
                try:
                    await response.aread()
                    return response
                finally:
                    await response.aclose()

            response = None
            try:
                # Client/transport construction and request building can be
                # slow. Recompute immediately before the physical send so a
                # setup delay cannot extend the fund-wide deadline.
                attempt_timeout, fund_deadline_selected = (
                    self.sec_budget.attempt_timeout_selection()
                )
                timeout_scope = asyncio.timeout(attempt_timeout)
                async with timeout_scope:
                    response = await client.send(request, follow_redirects=False, stream=True)
                    return await _read_bounded_sec_response(
                        response,
                        budget=self.sec_budget,
                        operation=self.sec_operation or "",
                    )
            except TimeoutError as exc:
                # A fixed per-attempt timeout remains a recoverable attempt
                # failure. If the worker timer reached the shared fund
                # deadline, latch it before Provider settles this failure so
                # no later candidate/redirect can be admitted.
                if timeout_scope.expired() and fund_deadline_selected:
                    self.sec_budget.latch_terminal("SEC one-fund execution deadline exceeded")
                    # Provider persists the invoke exception's type and text.
                    # Keep TimeoutError for classification, but make fund
                    # expiry distinguishable from a generic attempt timeout.
                    raise TimeoutError("SEC one-fund execution deadline exceeded") from exc
                raise
            finally:
                if response is not None:
                    await response.aclose()


class ETFSECExecutionBudget:
    """One finite, in-memory application envelope for a single fund lookup."""

    def __init__(self, initial_qualification_authority=None) -> None:
        self.started_at = _sec_budget_monotonic()
        self.deadline_at = self.started_at + ETF_SEC_FUND_DEADLINE_SECONDS
        self.initial_qualification_authority = initial_qualification_authority
        if initial_qualification_authority is not None:
            authority_remaining = (
                initial_qualification_authority.expires_at - datetime.now(UTC)
            ).total_seconds()
            self.deadline_at = min(
                self.deadline_at,
                self.started_at + max(0.0, authority_remaining),
            )
        self.provider_request_log_ids: list[int] = []
        self.physical_attempts = 0
        self.archived_submissions_pages = 0
        self.aggregate_decoded_bytes = 0
        self.last_attempt_started_at: float | None = None
        self._terminal_failure: str | None = None
        self._lock = threading.Lock()

    def record_request_log_id(self, request_log_id: int) -> None:
        with self._lock:
            if request_log_id not in self.provider_request_log_ids:
                self.provider_request_log_ids.append(request_log_id)

    def latch_terminal(self, reason: str) -> None:
        with self._lock:
            if self._terminal_failure is None:
                self._terminal_failure = reason

    def _raise_if_terminal(self) -> None:
        with self._lock:
            reason = self._terminal_failure
        if reason is not None:
            raise ETFHoldingsRouteHeldError(
                f"SEC one-fund execution stopped after a terminal response: {reason}"
            )

    def _check_deadline(self) -> None:
        if _sec_budget_monotonic() >= self.deadline_at:
            reason = "SEC one-fund execution deadline exceeded"
            self.latch_terminal(reason)
            raise ETFHoldingsRouteHeldError(reason)

    def attempt_timeout_seconds(self) -> float:
        """Return the remaining fund budget capped by the reviewed 20s attempt."""

        return self.attempt_timeout_selection()[0]

    def whole_call_timeout_seconds(self) -> float:
        """Return remaining monotonic time, already clamped to authority expiry."""

        self._raise_if_terminal()
        remaining = self.deadline_at - _sec_budget_monotonic()
        if remaining <= 0:
            reason = "SEC one-fund execution deadline exceeded"
            self.latch_terminal(reason)
            raise ETFHoldingsRouteHeldError(reason)
        return remaining

    def attempt_timeout_selection(self) -> tuple[float, bool]:
        """Return the chosen timeout and whether the fund deadline selects it.

        A tie is fund-bound: both limits expire together, so the terminal
        one-fund boundary must win over a recoverable per-attempt timeout.
        """

        self._raise_if_terminal()
        remaining = self.deadline_at - _sec_budget_monotonic()
        if remaining <= 0:
            reason = "SEC one-fund execution deadline exceeded"
            self.latch_terminal(reason)
            raise ETFHoldingsRouteHeldError(reason)
        fund_deadline_selected = remaining <= ETF_SEC_ATTEMPT_TIMEOUT_SECONDS
        return min(ETF_SEC_ATTEMPT_TIMEOUT_SECONDS, remaining), fund_deadline_selected

    def begin_logical_request(self, operation: str) -> None:
        self._raise_if_terminal()
        self._check_deadline()
        if operation == "fetch_etf_holdings_sec_submissions_file":
            with self._lock:
                if self.archived_submissions_pages >= 1:
                    self._terminal_failure = (
                        "SEC archived-submissions page limit exceeded for one fund"
                    )
                    raise ETFHoldingsRouteHeldError(self._terminal_failure)
                self.archived_submissions_pages += 1

    async def before_attempt(self) -> None:
        self._raise_if_terminal()
        self._check_deadline()
        if self.physical_attempts >= ETF_SEC_MAX_PHYSICAL_ATTEMPTS:
            reason = "SEC one-fund physical request-attempt limit exceeded"
            self.latch_terminal(reason)
            raise ETFHoldingsRouteHeldError(reason)
        while self.last_attempt_started_at is not None:
            delay = ETF_SEC_MIN_ATTEMPT_INTERVAL_SECONDS - (
                _sec_budget_monotonic() - self.last_attempt_started_at
            )
            if delay <= 0:
                break
            if _sec_budget_monotonic() + delay >= self.deadline_at:
                reason = "SEC one-fund execution deadline prevents another attempt"
                self.latch_terminal(reason)
                raise ETFHoldingsRouteHeldError(reason)
            await asyncio.sleep(delay)
        self._check_deadline()

    async def start_attempt(self) -> None:
        # This runs inside the Provider worker immediately before transport.
        self._raise_if_terminal()
        self._check_deadline()
        while True:
            with self._lock:
                if self.physical_attempts >= ETF_SEC_MAX_PHYSICAL_ATTEMPTS:
                    reason = "SEC one-fund physical request-attempt limit exceeded"
                    self._terminal_failure = reason
                    raise ETFHoldingsRouteHeldError(reason)
                now = _sec_budget_monotonic()
                delay = (
                    0.0
                    if self.last_attempt_started_at is None
                    else ETF_SEC_MIN_ATTEMPT_INTERVAL_SECONDS - (now - self.last_attempt_started_at)
                )
                if delay <= 0:
                    self.physical_attempts += 1
                    self.last_attempt_started_at = now
                    return
            if _sec_budget_monotonic() + delay >= self.deadline_at:
                reason = "SEC one-fund execution deadline prevents another attempt"
                self.latch_terminal(reason)
                raise ETFHoldingsRouteHeldError(reason)
            await asyncio.sleep(delay)
            self._check_deadline()

    def response_limit(self, operation: str) -> int:
        if operation == "fetch_etf_holdings_sec_submissions":
            return ETF_SEC_MAX_SUBMISSIONS_BYTES
        if operation == "fetch_etf_holdings_sec_submissions_file":
            return ETF_SEC_MAX_ARCHIVE_PAGE_BYTES
        if operation == "fetch_etf_holdings_sec_filing":
            return ETF_SEC_MAX_FILING_BYTES
        raise ETFHoldingsRouteHeldError("SEC response operation is not in the reviewed contract")

    def max_next_decoded_chunk(self, operation: str, response_bytes: int) -> int:
        response_remaining = self.response_limit(operation) - response_bytes
        with self._lock:
            aggregate_remaining = ETF_SEC_MAX_AGGREGATE_DECODED_BYTES - self.aggregate_decoded_bytes
        return max(1, min(64 * 1024, response_remaining + 1, aggregate_remaining + 1))

    def record_decoded_bytes(self, operation: str, response_bytes: int, count: int) -> str | None:
        response_total = response_bytes + count
        with self._lock:
            self.aggregate_decoded_bytes += count
            aggregate_total = self.aggregate_decoded_bytes
        if response_total > self.response_limit(operation):
            reason = f"SEC decoded {operation} response exceeded its application byte cap"
            self.latch_terminal(reason)
            return reason
        if aggregate_total > ETF_SEC_MAX_AGGREGATE_DECODED_BYTES:
            reason = "SEC one-fund aggregate decoded-response byte cap exceeded"
            self.latch_terminal(reason)
            return reason
        self._check_deadline()
        return None


async def _read_bounded_sec_response(
    response: httpx.Response,
    *,
    budget: ETFSECExecutionBudget,
    operation: str,
) -> httpx.Response:
    """Decode in bounded chunks; never materialize an uncapped SEC body."""

    content_encoding = response.headers.get("content-encoding", "").strip().lower()
    decoder = None
    if content_encoding in {"", "identity"}:
        pass
    elif content_encoding == "gzip":
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    elif content_encoding == "deflate":
        decoder = zlib.decompressobj()
    else:
        marker = f"SEC response used unsupported content encoding: {content_encoding[:32]}"
        budget.latch_terminal(marker)
        return _buffer_httpx_response_with_error(response, b"", marker)

    body = bytearray()
    response_bytes = 0
    body_error: str | None = None
    try:
        async for raw_chunk in response.aiter_raw(chunk_size=64 * 1024):
            pending = raw_chunk
            if decoder is not None and decoder.eof and pending:
                body_error = "SEC compressed response contains trailing or concatenated data"
                break
            while pending:
                max_output = budget.max_next_decoded_chunk(operation, response_bytes)
                if decoder is None:
                    decoded = pending[:max_output]
                    pending = pending[len(decoded) :]
                else:
                    decoded = decoder.decompress(pending, max_length=max_output)
                    pending = decoder.unconsumed_tail
                    if decoder.unused_data:
                        body_error = (
                            "SEC compressed response contains trailing or concatenated data"
                        )
                if decoded:
                    cap_error = budget.record_decoded_bytes(operation, response_bytes, len(decoded))
                    body_error = body_error or cap_error
                    response_bytes += len(decoded)
                    body.extend(decoded)
                    if body_error:
                        break
                if decoder is not None and pending and not decoded:
                    body_error = "SEC compressed response did not advance within byte bounds"
                    break
            if body_error:
                break
        if decoder is not None and not body_error and not decoder.eof:
            body_error = "SEC compressed response ended before a complete decoded body"
    except zlib.error:
        body_error = "SEC response compression stream is invalid"

    if body_error:
        budget.latch_terminal(body_error)

    return _buffer_httpx_response_with_error(response, bytes(body), body_error)


def _buffer_httpx_response_with_error(
    response: httpx.Response, content: bytes, body_error: str | None
) -> httpx.Response:
    extensions = dict(response.extensions)
    if body_error:
        extensions[_ETF_SEC_RESPONSE_LIMIT_MARKER] = body_error
    headers = httpx.Headers(response.headers)
    for header_name in ("content-encoding", "content-length", "transfer-encoding"):
        if header_name in headers:
            del headers[header_name]
    return httpx.Response(
        status_code=response.status_code,
        headers=headers,
        content=content,
        request=response.request,
        extensions=extensions,
    )


def _normalized_host(url: str) -> str:
    parsed = urlsplit(str(url))
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ETFHoldingsRouteHeldError("ETF holdings requests require a reviewed HTTPS host")
    if parsed.username is not None or parsed.password is not None or parsed.fragment:
        raise ETFHoldingsRouteHeldError("ETF holdings request URL is not a valid publisher URL")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise ETFHoldingsRouteHeldError("ETF holdings request URL has an invalid port") from exc
    return parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")


def _sec_request_matches_profile_cik(
    request_url: str, profile_cik: str | None, operation: str
) -> bool:
    """Bind each EDGAR URL path to the CIK stored on its committed ETF profile."""

    raw_cik = str(profile_cik or "").strip()
    if not raw_cik.isdigit() or len(raw_cik) > 10 or operation not in _ETF_SEC_OPERATIONS:
        return False
    normalized_cik = raw_cik.zfill(10)
    archive_cik = str(int(normalized_cik))
    parsed = urlsplit(request_url)
    if (
        parsed.query
        or parsed.fragment
        or parsed.username is not None
        or parsed.password is not None
    ):
        return False
    path = unquote(parsed.path)
    if any(part in {".", ".."} for part in path.split("/")):
        return False

    if operation == "fetch_etf_holdings_sec_submissions":
        return path == f"/submissions/CIK{normalized_cik}.json"
    if operation == "fetch_etf_holdings_sec_submissions_file":
        prefix = f"/submissions/CIK{normalized_cik}-submissions-"
        return path.startswith(prefix) and path.endswith(".json") and path.count("/") == 2

    parts = path.split("/")
    if len(parts) < 7 or parts[:5] != ["", "Archives", "edgar", "data", archive_cik]:
        return False
    accession_path = parts[5]
    return (
        len(accession_path) == 18
        and accession_path.isdigit()
        and bool("/".join(parts[6:]).strip("/"))
    )


async def _review_attempt_context(
    db: AsyncSession,
    *,
    provider_name: str,
    profile_id: int,
    instrument_id: int,
    provider_symbol: str,
    adapter_key: str,
    operation: str,
    request_url: str,
    sec_request: bool = False,
) -> tuple[DataSource, ProviderPolicy, str]:
    if sec_request:
        if operation not in _ETF_SEC_OPERATIONS:
            raise ETFHoldingsRouteHeldError(
                "SEC holdings operation is not in the reviewed contract"
            )
        if provider_name != "edgar" or adapter_key != ETF_SEC_ADAPTER_KEY:
            raise ETFHoldingsRouteHeldError(
                "SEC holdings request requires its dedicated EDGAR adapter"
            )
    elif operation not in _ETF_OPERATIONS:
        raise ETFHoldingsRouteHeldError("ETF holdings operation is not in the reviewed contract")
    request_host = _normalized_host(request_url)
    profile = await db.get(ETFProfile, profile_id)
    instrument = await db.get(Instrument, instrument_id)
    if profile is None or instrument is None or profile.instrument_id != instrument.id:
        raise ETFHoldingsRouteHeldError(
            "ETF request identity must resolve to committed profile and instrument rows"
        )
    if instrument.symbol.strip().upper() != provider_symbol.strip().upper():
        raise ETFHoldingsRouteHeldError(
            "ETF request symbol does not match its committed instrument"
        )
    if sec_request:
        if not _sec_request_matches_profile_cik(request_url, profile.sec_cik, operation):
            raise ETFHoldingsRouteHeldError(
                "SEC request URL does not match the committed ETF CIK identity"
            )
    else:
        if str(profile.adapter_key or "").strip().lower() != adapter_key:
            raise ETFHoldingsRouteHeldError(
                "ETF request adapter does not match its committed profile"
            )
        profile_aliases = (
            profile.provider_aliases if isinstance(profile.provider_aliases, dict) else {}
        )
        profile_provider = (
            str(
                profile_aliases.get("holdings_source_provider")
                or profile_aliases.get("source_provider")
                or ""
            )
            .strip()
            .lower()
        )
        if profile_provider != provider_name:
            raise ETFHoldingsRouteHeldError(
                "ETF request publisher does not match its committed profile route"
            )
    data_source = await db.scalar(select(DataSource).where(DataSource.name == provider_name))
    if data_source is None:
        raise ETFHoldingsRouteHeldError("ETF publisher has no shared Provider source record")
    policy = await db.scalar(
        select(ProviderPolicy).where(
            ProviderPolicy.data_source_id == data_source.id,
            ProviderPolicy.capability == ProviderCapability.ETF_HOLDINGS,
        )
    )
    if policy is None or not policy.is_enabled:
        raise ETFHoldingsRouteHeldError("ETF publisher capability is not explicitly enabled")

    config = data_source.config if isinstance(data_source.config, dict) else {}
    review = config.get("etf_holdings_review")
    if not isinstance(review, dict):
        raise ETFHoldingsRouteHeldError("ETF publisher review evidence is missing")
    hosts = review.get("https_hosts")
    if not isinstance(hosts, list) or request_host not in {
        str(value).strip().lower().rstrip(".") for value in hosts if isinstance(value, str)
    }:
        raise ETFHoldingsRouteHeldError("ETF publisher host is not in the reviewed host allowlist")
    operation_evidence = review.get("operations")
    operation_record = (
        operation_evidence.get(operation) if isinstance(operation_evidence, dict) else None
    )
    if not isinstance(operation_record, dict) or not all(
        isinstance(operation_record.get(field), str) and operation_record[field].strip()
        for field in ("evidence_source", "evidence_version", "reviewed_at")
    ):
        raise ETFHoldingsRouteHeldError("ETF publisher operation review evidence is incomplete")
    entitlement = await db.scalar(
        select(ProviderEntitlement).where(
            ProviderEntitlement.data_source_id == data_source.id,
            ProviderEntitlement.capability == ProviderCapability.ETF_HOLDINGS,
        )
    )
    if entitlement is None:
        raise ETFHoldingsRouteHeldError("ETF publisher entitlement review is missing")

    quota_scope = str(policy.quota_scope or "").strip().lower()
    account_scope_map = settings.PROVIDER_QUOTA_ACCOUNT_SCOPES
    if not isinstance(account_scope_map, dict) or not _has_explicit_account_scope_mapping(
        provider_name, quota_scope, account_scope_map
    ):
        raise ETFHoldingsRouteHeldError(
            "ETF publisher account binding is not explicitly configured"
        )
    try:
        account_scope = account_scope_for_provider(provider_name, quota_scope)
    except Exception as exc:  # noqa: BLE001 - malformed scope remains a closed route.
        raise ETFHoldingsRouteHeldError("ETF publisher account binding is invalid") from exc
    if review.get("account_scope") != account_scope:
        raise ETFHoldingsRouteHeldError(
            "ETF publisher review is bound to a different account scope"
        )

    binding = _REQUEST_BINDING.get()
    authority = binding.initial_qualification_authority if binding is not None else None
    if authority is not None:
        if (
            not sec_request
            or provider_name != authority.provider_name
            or operation not in authority.operations
            or profile_id != authority.profile_id
            or instrument_id != authority.instrument_id
            or provider_symbol.strip().upper() != authority.provider_symbol
            or account_scope != authority.account_scope
            or authority.expires_at <= datetime.now(UTC)
        ):
            raise ETFHoldingsRouteHeldError(
                "SEC request does not match its active initial qualification context"
            )
        if str(entitlement.live_probe_status or "not_run").strip().lower() != "not_run":
            raise ETFHoldingsRouteHeldError(
                "SEC initial qualification requires the exact unprobed entitlement state"
            )

    now = datetime.now(UTC)
    digest = hashlib.sha256(account_scope.strip().encode("utf-8")).hexdigest()

    def recurring_cost_is_admitted(sync_session) -> bool:
        budget_status = provider_recurring_cost_status(sync_session)
        budget = sync_session.get(ProviderRecurringCostBudget, 1)
        commitment = sync_session.scalar(
            select(ProviderRecurringCostCommitment).where(
                ProviderRecurringCostCommitment.data_source_id == data_source.id,
                ProviderRecurringCostCommitment.environment == settings.APP_ENV.strip().lower(),
                ProviderRecurringCostCommitment.billing_account_scope_digest == digest,
            )
        )
        if not budget_status.allowed or budget is None or commitment is None:
            return False
        commitment_is_active = commitment.state == "active" and (
            commitment.ends_at is None or commitment.ends_at > now
        )
        return bool(
            commitment_is_active
            and Decimal(commitment.monthly_equivalent) == Decimal("0")
            and Decimal(commitment.amount) == Decimal("0")
            and commitment.post_trial_amount is None
        )

    if not await db.run_sync(recurring_cost_is_admitted):
        raise ETFHoldingsRouteHeldError(
            "ETF publisher lacks an active verified-free shared recurring-cost commitment"
        )
    return data_source, policy, account_scope


async def execute_etf_holdings_request_attempt(
    db: AsyncSession,
    *,
    adapter: Any,
    instrument_id: int,
    provider_symbol: str,
    operation: str,
    request_url: str,
    single_attempt: Callable[[], Any] | LoopLocalHTTPXAttempt,
) -> ProviderExecutionResult:
    """Run exactly one publisher request under the shared Provider ledger.

    A request is either a synchronous requests-style callable or a
    LoopLocalHTTPXAttempt. The latter creates its AsyncClient inside the
    Provider worker loop and disables automatic redirects, so each hop is
    separately admitted. Raw async closures are rejected before admission.
    The AsyncSession remains on its owning loop. The request runs once only
    after shared policy, entitlement, operation holds, quota, and aggregate
    recurring-cost admission succeed.
    """

    provider_name = str(getattr(adapter, "source_provider", "")).strip().lower()
    if not provider_name:
        raise ETFHoldingsRouteHeldError("ETF adapter has no bound publisher identity")
    binding = _REQUEST_BINDING.get()
    profile_id = binding.profile_id if binding is not None else None
    adapter_key = str(getattr(adapter, "adapter_key", "")).strip().lower()
    sec_request = bool(binding and binding.sec_request)
    if profile_id is None:
        raise ETFHoldingsRouteHeldError(
            "ETF request requires a committed profile identity before admission"
        )
    if isinstance(single_attempt, LoopLocalHTTPXAttempt):
        if "follow_redirects" in single_attempt.request_kwargs:
            raise ETFHoldingsRouteHeldError(
                "HTTPX attempts must not follow redirects; admit each hop separately"
            )
        if _canonical_request_url(single_attempt.url) != _canonical_request_url(request_url):
            raise ETFHoldingsRouteHeldError(
                "HTTPX attempt full URL does not match its reviewed request URL"
            )
    elif inspect.iscoroutinefunction(single_attempt) or inspect.iscoroutinefunction(
        getattr(single_attempt, "__call__", None)
    ):
        raise ETFHoldingsRouteHeldError("async HTTPX attempts must use LoopLocalHTTPXAttempt")
    if instrument_id <= 0 or not str(provider_symbol).strip():
        raise ETFHoldingsRouteHeldError("ETF instrument and publisher symbol binding are required")
    if (operation in _ETF_SEC_OPERATIONS) != sec_request:
        raise ETFHoldingsRouteHeldError("SEC operations require their dedicated request binding")

    invoke = _sync_provider_invoke(single_attempt)
    physical_request_url = (
        single_attempt.url if isinstance(single_attempt, LoopLocalHTTPXAttempt) else request_url
    )
    attempt_log_ids: list[int] = []

    def retain_request_log_id(request_log_id: int) -> None:
        attempt_log_ids.append(request_log_id)
        if binding is not None:
            binding.request_log_ids.append(request_log_id)
            binding.request_urls_by_log_id[request_log_id] = physical_request_url
            if binding.sec_budget is not None:
                binding.sec_budget.record_request_log_id(request_log_id)

    async def retain_qualification_log_ids(runtime_db: AsyncSession) -> None:
        authority = binding.initial_qualification_authority if binding is not None else None
        if authority is None or not attempt_log_ids:
            return
        job = await runtime_db.get(ETFHoldingsBackfillJob, authority.attempt_id)
        if (
            job is None
            or job.job_type != "sec_nport_initial_qualification"
            or job.etf_profile_id != authority.profile_id
            or job.status != "running"
        ):
            raise ETFHoldingsRouteHeldError(
                "SEC initial qualification attempt is missing or no longer active"
            )
        extra_data = dict(job.extra_data or {})
        request_log_ids = list(extra_data.get("provider_request_log_ids") or [])
        for request_log_id in attempt_log_ids:
            if request_log_id not in request_log_ids:
                request_log_ids.append(request_log_id)
        extra_data["provider_request_log_ids"] = request_log_ids
        job.extra_data = extra_data
        await runtime_db.flush()

    async def run_shared_attempt() -> ProviderExecutionResult:
        # The shared attempt gets a narrow transaction of its own. This keeps
        # its request log/settlement durable if a public refresh caller later
        # cancels and rolls back unrelated ETF work in its unit of work.
        runtime_db = AsyncSession(bind=db.bind, expire_on_commit=False)
        try:
            review_result = await _review_attempt_context(
                runtime_db,
                provider_name=provider_name,
                profile_id=profile_id,
                instrument_id=instrument_id,
                provider_symbol=provider_symbol,
                adapter_key=adapter_key,
                operation=operation,
                request_url=physical_request_url,
                sec_request=sec_request,
            )
            authority = binding.initial_qualification_authority if binding is not None else None
            if authority is not None:
                if not isinstance(review_result, tuple) or len(review_result) != 3:
                    raise ETFHoldingsRouteHeldError(
                        "SEC qualification request review did not return its committed scope"
                    )
                _data_source, _policy, account_scope = review_result
                if authority.account_scope != account_scope:
                    raise ETFHoldingsRouteHeldError(
                        "SEC qualification account scope differs from its committed context"
                    )
                qualification_job = await runtime_db.get(
                    ETFHoldingsBackfillJob, authority.attempt_id
                )
                qualification_scope = (
                    qualification_job.extra_data.get("qualification_scope")
                    if qualification_job is not None
                    and isinstance(qualification_job.extra_data, dict)
                    else None
                )
                if (
                    qualification_job is None
                    or qualification_job.job_type != "sec_nport_initial_qualification"
                    or qualification_job.etf_profile_id != authority.profile_id
                    or qualification_job.status != "running"
                    or qualification_scope
                    != {
                        "provider": "edgar",
                        "capability": ProviderCapability.ETF_HOLDINGS.value,
                        "operations": sorted(authority.operations),
                        "profile_id": authority.profile_id,
                        "instrument_id": authority.instrument_id,
                        "account_scope": authority.account_scope,
                    }
                    or authority.expires_at <= datetime.now(UTC)
                ):
                    raise ETFHoldingsRouteHeldError(
                        "SEC initial qualification context is expired or no longer active"
                    )

            async def execute_shared_call() -> ProviderExecutionResult:
                return await execute_provider_call(
                    runtime_db,
                    ProviderCapability.ETF_HOLDINGS,
                    operation,
                    instrument_id=instrument_id,
                    provider_symbol=provider_symbol,
                    profile_id=profile_id,
                    usage_identity=provider_symbol,
                    provider_name=provider_name,
                    invoke=invoke,
                    etf_holdings_adapters={provider_name: adapter},
                    capture_response_payloads=True,
                    request_log_id_callback=retain_request_log_id,
                )

            if authority is None:
                result = await execute_shared_call()
            else:
                with _bind_etf_initial_qualification_authority(authority):
                    result = await execute_shared_call()
            await retain_qualification_log_ids(runtime_db)
        except BaseException:
            if attempt_log_ids:
                try:
                    await retain_qualification_log_ids(runtime_db)
                    await runtime_db.commit()
                except BaseException:
                    # Preserve the original provider/transport exception. If
                    # the audit link itself cannot be committed, leave the
                    # qualification latch unresolved and fail closed.
                    await runtime_db.rollback()
            else:
                await runtime_db.rollback()
            raise
        else:
            await runtime_db.commit()
            return result
        finally:
            await runtime_db.close()

    execution = asyncio.create_task(run_shared_attempt())
    try:
        return await asyncio.shield(execution)
    except asyncio.CancelledError:
        # Provider's executor attempt cannot be safely abandoned once admitted:
        # shield it until its canonical runtime has recorded and settled the
        # one physical request, then preserve caller cancellation.
        while not execution.done():
            try:
                await asyncio.shield(execution)
            except asyncio.CancelledError:
                # Repeated caller cancellation must not orphan the admitted
                # Provider task or close its session before settlement.
                continue
            except Exception:
                break
        if execution.done() and not execution.cancelled():
            # Retrieving the result prevents an unobserved task exception; the
            # original cancellation remains the caller-visible outcome.
            try:
                execution.result()
            except Exception:
                pass
        raise


def _sync_provider_invoke(
    single_attempt: Callable[[], Any] | LoopLocalHTTPXAttempt,
) -> Callable[[Any, str | None], Any]:
    """Adapt one attempt to Provider's sync callback without cross-loop waits."""

    def invoke(_adapter: Any, _symbol: str | None) -> Any:
        if isinstance(single_attempt, LoopLocalHTTPXAttempt):

            async def run_httpx_attempt() -> Any:
                response = await single_attempt.execute()
                observe_response(response)
                if response.status_code >= 400:
                    response.raise_for_status()
                response_limit_error = response.extensions.get(_ETF_SEC_RESPONSE_LIMIT_MARKER)
                if response_limit_error:
                    raise ETFHoldingsRouteHeldError(str(response_limit_error))
                return response

            return asyncio.run(run_httpx_attempt())

        value = single_attempt()
        if inspect.isawaitable(value):
            if inspect.iscoroutine(value):
                value.close()
            raise TypeError(
                "async Provider attempts must use LoopLocalHTTPXAttempt; "
                "the sync callback cannot return an awaitable"
            )
        observe_response(value)
        return value

    return invoke
