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
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, TypeVar
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.data_source import DataSource
from app.models.etf_holdings import ETFProfile
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
from app.services.provider_runtime import ProviderExecutionResult, execute_provider_call

T = TypeVar("T")

_ETF_OPERATIONS = frozenset({"fetch_etf_holdings_latest", "fetch_etf_holdings_for_date"})


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
    request_log_ids: list[int]
    request_urls_by_log_id: dict[int, str]


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
        request_log_ids=[],
        request_urls_by_log_id={},
    )
    token = _REQUEST_BINDING.set(binding)
    try:
        yield binding
    finally:
        _REQUEST_BINDING.reset(token)


def etf_holdings_request_is_bound() -> bool:
    return _REQUEST_BINDING.get() is not None


def require_unbound_etf_holdings_context(operation: str) -> None:
    """Prevent a different ETF workflow from borrowing an ambient route binding.

    Discovery and SEC enrichment are not yet reviewed ``ETF_HOLDINGS``
    operations. A surrounding latest/dated refresh context must not silently
    authorize their independent URL, identity, or request purpose.
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
            attempt = _make_loop_local_httpx_attempt(
                method=current_method,
                url=current_url,
                request_kwargs=current_kwargs,
                client_kwargs={**current_client_kwargs, "cookies": self._cookies},
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

    async def execute(self) -> httpx.Response:
        if "follow_redirects" in self.request_kwargs:
            raise ETFHoldingsRouteHeldError(
                "HTTPX attempts must not follow redirects; admit each hop separately"
            )
        if "transport" in self.client_kwargs or "follow_redirects" in self.client_kwargs:
            raise ETFHoldingsRouteHeldError(
                "HTTPX attempts cannot override the per-attempt transport boundary"
            )
        transport = self.transport_factory() if self.transport_factory is not None else None
        async with httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            **self.client_kwargs,
        ) as client:
            response = await client.request(
                self.method,
                self.url,
                follow_redirects=False,
                **self.request_kwargs,
            )
            await response.aread()
            return response


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
) -> tuple[DataSource, ProviderPolicy, str]:
    if operation not in _ETF_OPERATIONS:
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
    if str(profile.adapter_key or "").strip().lower() != adapter_key:
        raise ETFHoldingsRouteHeldError("ETF request adapter does not match its committed profile")
    profile_aliases = profile.provider_aliases if isinstance(profile.provider_aliases, dict) else {}
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

    quota_scope = str(policy.quota_scope or "").strip()
    account_scope_map = settings.PROVIDER_QUOTA_ACCOUNT_SCOPES
    account_scope_key = f"{provider_name}:{quota_scope}" if quota_scope else ""
    if not isinstance(account_scope_map, dict) or not (
        account_scope_key in account_scope_map or provider_name in account_scope_map
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

    async def run_shared_attempt() -> ProviderExecutionResult:
        # The shared attempt gets a narrow transaction of its own. This keeps
        # its request log/settlement durable if a public refresh caller later
        # cancels and rolls back unrelated ETF work in its unit of work.
        runtime_db = AsyncSession(bind=db.bind, expire_on_commit=False)
        try:
            await _review_attempt_context(
                runtime_db,
                provider_name=provider_name,
                profile_id=profile_id,
                instrument_id=instrument_id,
                provider_symbol=provider_symbol,
                adapter_key=adapter_key,
                operation=operation,
                request_url=physical_request_url,
            )
            result = await execute_provider_call(
                runtime_db,
                ProviderCapability.ETF_HOLDINGS,
                operation,
                instrument_id=instrument_id,
                provider_symbol=provider_symbol,
                usage_identity=provider_symbol,
                provider_name=provider_name,
                invoke=invoke,
                etf_holdings_adapters={provider_name: adapter},
                capture_response_payloads=True,
                request_log_id_callback=retain_request_log_id,
            )
        except BaseException:
            if attempt_log_ids:
                await runtime_db.commit()
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
